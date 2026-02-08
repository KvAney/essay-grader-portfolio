import asyncio
import json
import time
import logging
from aiokafka import AIOKafkaConsumer
from app.core.config import settings
from app.db.mongo import db as mongodb
from app.db.postgres import SessionLocal
from app.db.models import Submission
from app.services.essay_evaluator import EssayEvaluationEngine
from bson import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# ESSAY EVALUATION ENGINE
# ============================================================================
essay_evaluator = EssayEvaluationEngine(mongodb)

async def consume():
    """
    STAGE 3: AI Evaluation Worker
    
    This worker:
    1. Consumes from ai-processing topic (lightweight Kafka messages from OCR worker)
    2. Fetches essay text + question + subject from MongoDB (the "Claim Check" reference)
    3. Runs EssayEvaluationEngine.grade_essay() for multi-agent 3-phase evaluation:
       - Phase 1: Shadow Rubric (LLM-based rubric generation from question/subject)
       - Phase 2: Claim Extraction & Fact-Checking (extract claims, verify against knowledge base)
       - Phase 3: Holistic Scoring (linguistic, structure, content coverage)
    4. Persists evaluation report to MongoDB essay_evaluations collection
    5. Updates original Mongo document with analysis_tasks array
    6. Marks submission as complete in Postgres
    
    KEY: Evaluation engine handles all LLM calls (OpenAI + Pinecone context).
    All heavy computation happens here; Kafka queues distribute work.
    """
    consumer = AIOKafkaConsumer(
        settings.AI_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="ai-group",
        auto_offset_reset='earliest'
    )
    
    await consumer.start()
    logger.info("=" * 70)
    logger.info("AI Evaluation Worker Started")
    logger.info("=" * 70)
    logger.info(f"✓ Engine: EssayEvaluationEngine (3-Phase Multi-Agent)")
    logger.info(f"✓ Phases: Shadow Rubric → Claim Extraction → Holistic Scoring")
    logger.info(f"✓ LLM: OpenAI (gpt-3.5-turbo)")
    logger.info(f"✓ Knowledge Base: Pinecone (subject-indexed embeddings)")
    logger.info("=" * 70)

    try:
        async for msg in consumer:
            try:
                data = json.loads(msg.value.decode('utf-8'))
                mongo_id = data['mongo_id']
                sub_id = data['submission_id']
                question = data.get('question')
                subject = data.get('subject')
                
                logger.info(f"\n[ESSAY #{sub_id}] Starting AI Evaluation")
                logger.info(f"  Question: {question if question else '(not provided)'}")
                logger.info(f"  Subject: {subject if subject else '(not provided)'}")
                
                # 1. Update Postgres status
                with SessionLocal() as session:
                    sub = session.query(Submission).filter(Submission.id == sub_id).first()
                    if sub:
                        sub.status = "ai_processing"
                        session.commit()
                
                # 2. Fetch essay text + metadata from MongoDB
                doc = await mongodb.essayCollection.find_one({"_id": ObjectId(mongo_id)})
                if not doc:
                    logger.error(f"[ESSAY #{sub_id}] ✗ Document not found in MongoDB")
                    continue
                
                essay_text = doc.get('text', '')
                if not essay_text:
                    logger.error(f"[ESSAY #{sub_id}] ✗ No text in document")
                    continue
                
                logger.info(f"[ESSAY #{sub_id}] ✓ Retrieved {len(essay_text)} chars from MongoDB")
                logger.info(f"[ESSAY #{sub_id}] ▶ Running 3-Phase Evaluation Engine...")
                
                # 3. RUN EVALUATION ENGINE
                evaluation_start = time.time()
                evaluation_result = await essay_evaluator.grade_essay(
                    essay_text=essay_text,
                    question=question or "General essay evaluation",
                    subject=subject or "General Knowledge"
                )
                evaluation_duration = time.time() - evaluation_start
                
                logger.info(f"[ESSAY #{sub_id}] ✓ Evaluation completed in {evaluation_duration:.1f}s")
                
                # 4. Persist evaluation report to MongoDB
                # Insert into essay_evaluations collection
                report = {
                    "submission_id": sub_id,
                    "submission_mongo_id": str(mongo_id),
                    "question": question,
                    "subject": subject,
                    "status": "completed",
                    "overall_score": evaluation_result.get("overall_score", 0),
                    "analysis_tasks": evaluation_result.get("analysis_tasks", []),
                    "feedback": evaluation_result.get("feedback", ""),
                    "completion_time": evaluation_duration,
                    "completed_at": str(time.time())
                }
                
                insert_result = await mongodb.essay_evaluations.insert_one(report)
                logger.info(f"[ESSAY #{sub_id}] ✓ Evaluation report saved to MongoDB (ID: {insert_result.inserted_id})")
                
                # 5. Update original Mongo document with analysis_tasks reference
                await mongodb.essayCollection.update_one(
                    {"_id": ObjectId(mongo_id)},
                    {
                        "$set": {
                            "status": "completed",
                            "evaluation_report_id": str(insert_result.inserted_id),
                            "overall_score": evaluation_result.get("overall_score", 0)
                        },
                        "$push": {
                            "analysis_tasks": {
                                "evaluation_id": str(insert_result.inserted_id),
                                "timestamp": str(time.time()),
                                "tasks": evaluation_result.get("analysis_tasks", [])
                            }
                        }
                    }
                )
                logger.info(f"[ESSAY #{sub_id}] ✓ Original document updated with evaluation reference")
                
                # 6. Mark complete in Postgres
                with SessionLocal() as session:
                    sub = session.query(Submission).filter(Submission.id == sub_id).first()
                    if sub:
                        sub.status = "completed"
                        session.commit()
                
                logger.info(f"[ESSAY #{sub_id}] ✓ EVALUATION COMPLETE")
                logger.info(f"[ESSAY #{sub_id}] ✓ Overall Score: {evaluation_result.get('overall_score', 'N/A')}")
                logger.info(f"[ESSAY #{sub_id}] Ready for /evaluation/{sub_id} query\n")
            
            except Exception as e:
                logger.error(f"[AI Worker] Error processing message: {str(e)}")
                logger.exception(e)

    except asyncio.CancelledError:
        logger.info("AI Worker cancelled")
    except Exception as e:
        logger.error(f"[AI Worker] Critical error: {str(e)}")
        logger.exception(e)
    finally:
        await consumer.stop()
        logger.info("AI Worker stopped")

if __name__ == "__main__":
    asyncio.run(consume())
