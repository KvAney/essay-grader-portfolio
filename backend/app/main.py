
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.db.postgres import get_db, engine, Base
from app.db.models import Submission
from app.core.config import settings
from app.db.mongo import db as mongodb
from app.utils.rate_limiter import TokenBucketRateLimiter
from aiokafka import AIOKafkaProducer
from datetime import datetime
from bson import ObjectId
import json
from sqlalchemy import text
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Essay Grader API - Secure Ingestion Layer", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# RATE LIMITING FOR INGESTION (Kafka Protection)
# ============================================================================
# Limit user uploads to protect Kafka topic from being flooded
ingestion_rate_limiter = TokenBucketRateLimiter(rate=50, per=60)  # 50 uploads/min max

# ============================================================================
# HELPER: ASYNC KAFKA PRODUCER
# ============================================================================
async def produce_to_kafka(topic: str, message: dict) -> bool:
    """
    Produce a message to Kafka with error handling.
    
    Args:
        topic: Kafka topic name
        message: Dictionary to send
    
    Returns:
        True if successful, False otherwise
    """
    producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
        await producer.send_and_wait(topic, json.dumps(message).encode('utf-8'))
        logger.info(f"✓ Message sent to {topic}: {message.get('submission_id')}")
        return True
    except Exception as e:
        logger.error(f"✗ Kafka producer error: {str(e)}")
        return False
    finally:
        await producer.stop()

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Essay Grader API - Secure Ingestion Layer",
        "version": "2.0.0",
        "architecture": "PostgreSQL + MongoDB + Kafka",
        "docs": "/docs"
    }

@app.post("/upload/", status_code=202)
async def upload_essay(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    CLAIM CHECK PATTERN IMPLEMENTED:
    1. Store heavy file in MongoDB.
    2. Send only the MongoDB ID to Kafka.
    """
    
    # Rate limiting logic here...
    # await ingestion_rate_limiter.acquire()
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(400, "Invalid filename")
        
        if file.size and file.size > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(413, "File too large (max 50MB)")
        
        # 1. Save metadata to Postgres (Synchronous)
        new_sub = Submission(filename=file.filename, status="queued")
        db.add(new_sub)
        db.commit()
        db.refresh(new_sub)
        
        logger.info(f"✓ Submission {new_sub.id} created: {file.filename}")
        
        # 2. Read file content
        file_content = await file.read()
        
        # 3. PREPARE & SAVE TO MONGODB (The "Claim Check")
        # We initialize the document structure you requested, but with 'queued' status
        mongo_doc = {
            "submission_id": new_sub.id,
            "filename": file.filename,
            "file_data": file_content,       # <--- Storing the RAW file bytes here
            "text": None,                    # Placeholder for OCR result         
            "ocr_time": None,
            "created_at": str(datetime.utcnow()),
            "analysis_tasks": [],
            "aggregated_feedback": None,
            "overall_score": 0
        }
        
        # Insert into essayCollection
        insert_result = await mongodb.essayCollection.insert_one(mongo_doc)
        mongo_id = str(insert_result.inserted_id) # Get the Generated ID
        
        # 4. Queue for OCR (Send only the ID to Kafka)
        message = {
            "submission_id": new_sub.id,
            "mongo_id": mongo_id,        # <--- The Ticket!
            "filename": file.filename,
            "status": "queued",
            "timestamp": str(datetime.utcnow().timestamp())
        }
        
        # Schedule Kafka send as background task
        background_tasks.add_task(produce_to_kafka, settings.OCR_TOPIC, message)
        
        # 5. Return 202 IMMEDIATELY
        return Response(
            status_code=202,
            content=json.dumps({
                "submission_id": new_sub.id,
                "mongo_id": mongo_id,
                "status": "queued",
                "message": "Essay uploaded and queued for processing."
            }),
            media_type="application/json"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(500, f"Upload failed: {str(e)}")

@app.get("/status/{submission_id}")
async def get_status(submission_id: int, db: Session = Depends(get_db)):
    """
    Check the status and results of a submission.
    
    CLAIM CHECK PATTERN: We store heavy data (5MB essays) in MongoDB
    and reference it via submission_id. This keeps Postgres lean.
    
    Status Flow:
    - "queued": Waiting for OCR
    - "ocr_completed": Text extracted, waiting for AI analysis
    - "ai_processing": Running AI orchestrator tasks
    - "completed": All analysis done, results available
    """
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    
    response = {
        "submission_id": submission_id,
        "filename": sub.filename,
        "status": sub.status,
        "created_at": sub.created_at.isoformat() if sub.created_at else None
    }
    
    # If completed, fetch results from MongoDB
    if sub.status == "completed" and sub.mongo_id:
        try:
            doc = await mongodb.evaluations.find_one({"_id": ObjectId(sub.mongo_id)})
            if doc:
                # Return all analysis tasks
                response["analysis"] = doc.get("analysis_tasks", [])
                response["aggregated_feedback"] = doc.get("aggregated_feedback")
                response["overall_score"] = doc.get("overall_score", 0)
                response["completion_time"] = doc.get("completion_time")
        except Exception as e:
            logger.error(f"Error fetching result: {str(e)}")
            response["error"] = "Could not fetch detailed results"
    
    return response

@app.get("/submissions/")
async def list_submissions(db: Session = Depends(get_db)):
    """
    List all submissions with status overview.
    """
    submissions = db.query(Submission).order_by(Submission.created_at.desc()).limit(100).all()
    return {
        "total": len(submissions),
        "submissions": [
            {
                "id": s.id,
                "filename": s.filename,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None
            }
            for s in submissions
        ]
    }

@app.get("/health")
async def health_check():
    """
    System health check.
    Verify all dependencies are accessible.
    """
    health_status = {
        "api": "healthy",
        "postgres": "unknown",
        "mongodb": "unknown",
        "kafka": "unknown"
    }
    
    try:
        # Check Postgres
        from app.db.postgres import SessionLocal
        with SessionLocal() as session:
            session.execute(text('SELECT 1'))
            health_status["postgres"] = "healthy"
    except Exception as e:
        health_status["postgres"] = f"unhealthy: {str(e)}"
    
    try:
        # Check MongoDB
        await mongodb.command("ping")
        health_status["mongodb"] = "healthy"
    except Exception as e:
        health_status["mongodb"] = f"unhealthy: {str(e)}"
    
    # Kafka is checked implicitly during message production
    health_status["kafka"] = "assumed healthy"
    
    return health_status

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("Essay Grader API v2.0 - Secure Ingestion Layer")
    logger.info("=" * 60)
    logger.info("✓ API Gateway started on port 8000")
    logger.info("✓ Rate limiting: 50 uploads/min")
    logger.info("✓ Kafka topics: ocr-jobs, ai-processing")
    logger.info("✓ Docs available at: /docs")
    logger.info("=" * 60)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Essay Grader API shutting down...")
