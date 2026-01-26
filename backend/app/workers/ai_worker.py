import asyncio
import json
import time
import logging
from aiokafka import AIOKafkaConsumer
from app.core.config import settings
from app.db.mongo import db as mongodb
from app.db.postgres import SessionLocal
from app.db.models import Submission
from app.utils.rate_limiter import TokenBucketRateLimiter
from app.utils.ai_orchestrator import AIOrchestrator
from bson import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# RATE LIMITER (Groq API Protection)
# ============================================================================
# Groq Free Tier: 20-30 RPM. We use 20 to be safe with margin.
# Each essay gets 4 parallel calls (Grammar, Structure, Logic, Content)
# So: 20 RPM / 4 = 5 essays/min = 1 essay every 12 seconds
groq_rate_limiter = TokenBucketRateLimiter(rate=20, per=60)

# ============================================================================
# AI ORCHESTRATOR
# ============================================================================
ai_orchestrator = AIOrchestrator(rate_limiter=groq_rate_limiter)

async def consume():
    """
    STAGE 3: AI Orchestration Worker
    
    This worker:
    1. Pulls from ai-processing topic (lightweight messages from OCR worker)
    2. Fetches essay text from MongoDB (the "Claim Check" reference)
    3. Runs 4 parallel AI analysis tasks concurrently
    4. Aggregates all results
    5. Updates MongoDB with final evaluation
    6. Marks as complete in Postgres
    
    KEY: Rate limiting ensures we never exceed Groq's 20 RPM limit.
    If messages arrive faster than we can process, Kafka queues them.
    """
    consumer = AIOKafkaConsumer(
        settings.AI_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="ai-group",
        auto_offset_reset='earliest'
    )
    
    await consumer.start()
    logger.info("=" * 70)
    logger.info("AI Worker Started - AI Orchestration Layer")
    logger.info("=" * 70)
    logger.info(f"✓ Groq Rate Limit: 20 requests/min (safe margin)")
    logger.info(f"✓ Fan-out: 4 parallel AI tasks per essay")
    logger.info(f"✓ Processing capacity: ~5 essays/min")
    logger.info("=" * 70)

    try:
        async for msg in consumer:
            try:
                data = json.loads(msg.value.decode('utf-8'))
                mongo_id = data['mongo_id']
                sub_id = data['submission_id']
                
                logger.info(f"\n[ESSAY #{sub_id}] Starting AI Analysis")
                logger.info(f"  Status: ai_processing")
                
                # 1. Update Postgres status
                with SessionLocal() as session:
                    sub = session.query(Submission).filter(Submission.id == sub_id).first()
                    if sub:
                        sub.status = "ai_processing"
                        session.commit()
                
                # 2. Fetch essay text from MongoDB
                doc = await mongodb.essayCollection.find_one({"_id": ObjectId(mongo_id)})
                if not doc:
                    logger.error(f"[ESSAY #{sub_id}] ✗ Document not found in MongoDB")
                    continue
                
                text = doc.get('text', '')
                if not text:
                    logger.error(f"[ESSAY #{sub_id}] ✗ No text in document")
                    continue
                
                logger.info(f"[ESSAY #{sub_id}] ✓ Retrieved {len(text)} chars from MongoDB")
                logger.info(f"[ESSAY #{sub_id}] ▶ Spawning 4 parallel AI tasks...")
                
                # 3. RUN ORCHESTRATOR: Fan-out to 4 parallel tasks
                analysis_start = time.time()
                analysis_result = await ai_orchestrator.orchestrate(text, timeout=300)
                analysis_duration = time.time() - analysis_start
                
                logger.info(f"[ESSAY #{sub_id}] ✓ All tasks completed in {analysis_duration:.1f}s")
                
                # 4. Update MongoDB with results
                # 1. Prepare the data (Include the original ID so you can link it back later!)
                insert_data = {
                    "submission_mongo_id": str(mongo_id),  # Link to the original upload
                    "status": "completed",
                    "analysis_tasks": analysis_result.get("tasks", []),
                    "aggregated_feedback": analysis_result.get("aggregated_feedback"),
                    "overall_score": analysis_result.get("overall_score", 0),
                    "completion_time": analysis_duration,
                    "completed_at": str(time.time())
                }

                # 2. Insert into a NEW collection (e.g., 'analysis_results')
                # Note: MongoDB creates the collection automatically if it doesn't exist.
                await mongodb.evaluations.insert_one(insert_data)
                logger.info(f"[ESSAY #{sub_id}] ✓ Results saved to MongoDB")
                
                # 5. Mark complete in Postgres
                with SessionLocal() as session:
                    sub = session.query(Submission).filter(Submission.id == sub_id).first()
                    if sub:
                        sub.status = "completed"
                        session.commit()
                
                logger.info(f"[ESSAY #{sub_id}] ✓ ANALYSIS COMPLETE")
                logger.info(f"[ESSAY #{sub_id}] ✓ Overall Score: {analysis_result.get('overall_score', 'N/A')}")
                logger.info(f"[ESSAY #{sub_id}] Ready for /status/{sub_id} query\n")
            
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
