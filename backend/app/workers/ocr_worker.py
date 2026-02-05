import asyncio
import json
import time
import logging
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from app.core.config import settings
from app.db.mongo import db as mongodb
from app.db.postgres import SessionLocal
from app.db.models import Submission
from app.services.ocr import mock_ocr
from bson import ObjectId  # Make sure you have this import!

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def produce_to_ai_queue(message: dict) -> bool:
    """
    Produce a message to the AI processing queue.
    
    Args:
        message: Dictionary with submission_id and mongo_id
    
    Returns:
        True if successful, False otherwise
    """
    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
        await producer.send_and_wait(settings.AI_TOPIC, json.dumps(message).encode('utf-8'))
        return True
    except Exception as e:
        logger.error(f"Error producing to AI queue: {str(e)}")
        return False
    finally:
        await producer.stop()



async def consume():
    """
    STAGE 2: OCR Worker (Claim Check Pattern - UPDATED)
    
    Flow:
    1. Receive `mongo_id` from Kafka.
    2. FETCH heavy file content from MongoDB (Claiming the check).
    3. Perform OCR.
    4. UPDATE the existing MongoDB document with extracted text.
    5. Signal AI Worker to start.
    """
    consumer = AIOKafkaConsumer(
        settings.OCR_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="ocr-group",
        auto_offset_reset='earliest'
    )
    
    await consumer.start()
    logger.info("=" * 70)
    logger.info("OCR Worker Started - Claim Check Mode")
    logger.info("=" * 70)

    try:
        async for msg in consumer:
            try:
                data = json.loads(msg.value)
                sub_id = data['submission_id']
                mongo_id = data['mongo_id']     # <--- The Key Reference
                filename = data.get('filename', 'unknown')
                
                logger.info(f"\n[ESSAY #{sub_id}] OCR Job Received (Mongo ID: {mongo_id})")

                # ---------------------------------------------------------
                # STEP 1: CLAIM THE DATA (Fetch from MongoDB)
                # ---------------------------------------------------------
                document = await mongodb.essayCollection.find_one({"_id": ObjectId(mongo_id)})
                
                if not document:
                    logger.error(f"[ESSAY #{sub_id}] ✗ Error: Document not found in MongoDB!")
                    continue

                # Retrieve the heavy binary data
                file_bytes = document.get('file_data')
                if not file_bytes:
                    logger.error(f"[ESSAY #{sub_id}] ✗ Error: No file data in document!")
                    continue

                logger.info(f"[ESSAY #{sub_id}] ✓ Retrieved {len(file_bytes)} bytes from DB")

                # ---------------------------------------------------------
                # STEP 2: PERFORM OCR
                # ---------------------------------------------------------
                ocr_start = time.time()
                
                # Run your OCR function on the bytes
                extracted_text = mock_ocr(file_bytes, filename)
                
                ocr_duration = time.time() - ocr_start
                logger.info(f"[ESSAY #{sub_id}] ✓ OCR completed in {ocr_duration:.2f}s")

                # ---------------------------------------------------------
                # STEP 3: UPDATE MONGODB (Add Text)
                # ---------------------------------------------------------
                update_data = {
                    "text": extracted_text,
                    "status": "ocr_completed",
                    "ocr_time": ocr_duration,
                    "updated_at": str(time.time())
                }

                await mongodb.essayCollection.update_one(
                    {"_id": ObjectId(mongo_id)},
                    {"$set": update_data}
                )
                logger.info(f"[ESSAY #{sub_id}] ✓ MongoDB Updated with extracted text")

                # ---------------------------------------------------------
                # STEP 4: UPDATE POSTGRES STATUS
                # ---------------------------------------------------------
                with SessionLocal() as session:
                    sub = session.query(Submission).filter(Submission.id == sub_id).first()
                    if sub:
                        sub.status = "ocr_completed"
                        sub.mongo_id = mongo_id # Ensure this is linked
                        session.commit()

                # ---------------------------------------------------------
                # STEP 5: NOTIFY AI WORKER
                # ---------------------------------------------------------
                ai_message = {
                    "submission_id": sub_id,
                    "mongo_id": mongo_id,   # Pass the same ID forward
                    "filename": filename
                }
                # Attach optional context if present in Mongo document or incoming message
                question = document.get("question") or data.get("question")
                subject = document.get("subject") or data.get("subject")
                if question:
                    ai_message["question"] = question
                if subject:
                    ai_message["subject"] = subject

                success = await produce_to_ai_queue(ai_message)
                if success:
                    logger.info(f"[ESSAY #{sub_id}] → Handoff to AI Worker successful\n")
                else:
                    logger.error(f"[ESSAY #{sub_id}] ✗ Failed to queue for AI")
            
            except Exception as e:
                logger.error(f"[OCR Worker] Error processing message: {str(e)}")
                # logger.exception(e) # Uncomment for full trace

    except asyncio.CancelledError:
        logger.info("OCR Worker cancelled")
    except Exception as e:
        logger.error(f"[OCR Worker] Critical error: {str(e)}")
    finally:
        await consumer.stop()
        logger.info("OCR Worker stopped")

if __name__ == "__main__":
    asyncio.run(consume())
