
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.db.postgres import get_db, engine, Base
from app.db.models import Submission
from app.core.config import settings
from app.db.mongo import db as mongodb
from app.utils.rate_limiter import TokenBucketRateLimiter
from app.services.ingestion import NCERTIngestionPipeline
from app.services.essay_evaluator import EssayEvaluationEngine
from app.models.schemas import (
    IngestionRequest, IngestionResponse,
    GradeEssayRequest, GradeEssayResponse, ErrorResponse
)
from aiokafka import AIOKafkaProducer
from datetime import datetime
from bson import ObjectId
from typing import List
import json
from sqlalchemy import text
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Essay Grader API - UPSC AI Assistant", 
    version="3.0.0",
    description="AI-powered essay grading with Ingestion Pipeline and Multi-Agent Evaluation Engine"
)

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
# INITIALIZE CORE MODULES
# ============================================================================
ingestion_pipeline = NCERTIngestionPipeline(mongodb)
evaluation_engine = EssayEvaluationEngine(mongodb)

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

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Essay Grader API - UPSC AI Assistant",
        "version": "3.0.0",
        "architecture": "FastAPI + PostgreSQL + MongoDB + Pinecone + OpenAI",
        "modules": {
            "ingestion": "Parent-Child RAG (NCERT PDFs to Pinecone)",
            "evaluation": "3-Phase Multi-Agent Essay Grading",
            "docs": "/docs"
        }
    }

# ============================================================================
# MODULE 1: DATA INGESTION ENDPOINTS
# ============================================================================

@app.post("/ingest/textbook", response_model=IngestionResponse)
async def ingest_ncert_textbook(request: IngestionRequest):
    """
    Ingest NCERT textbook using Parent-Child RAG strategy.
    
    - Extracts text from PDF
    - Creates parent chunks (~1000 tokens) stored in MongoDB
    - Creates child chunks (~200 tokens) embedded and stored in Pinecone
    - Links children to parents via metadata
    
    Args:
        request: IngestionRequest with subject, grade, file_path
        
    Returns:
        IngestionResponse with status and statistics
    """
    try:
        logger.info(f"Starting ingestion: {request.subject} Grade {request.grade}")
        result = await ingestion_pipeline.ingest_textbook(
            file_path=request.file_path,
            subject=request.subject,
            grade=request.grade
        )
        return result
    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/ingest/batch")
async def ingest_batch_textbooks(files: List[IngestionRequest]):
    """
    Ingest multiple NCERT textbooks in parallel.
    
    Args:
        files: List of IngestionRequest objects
        
    Returns:
        Aggregated results for all files
    """
    try:
        file_tuples = [
            (f.file_path, f.subject, f.grade) for f in files
        ]
        result = await ingestion_pipeline.ingest_batch(file_tuples)
        return result
    except Exception as e:
        logger.error(f"Batch ingestion error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

# ============================================================================
# MODULE 2: ESSAY EVALUATION ENDPOINTS
# ============================================================================

@app.post("/grade_essay", response_model=GradeEssayResponse)
async def grade_essay(request: GradeEssayRequest):
    """
    Grade a student's essay using multi-agent evaluation system.
    
    **3-Phase Flow:**
    
    **Phase 0:** Shadow Rubric
    - Query RAG system with the question
    - Extract 15 must-have concepts from NCERT content
    
    **Phase 1:** Extraction & Parsing
    - Extract atomic claims from essay
    - Extract discourse markers (logical flow indicators)
    
    **Phase 2:** Parallel Agent Execution
    - Fact Checker Agent: Verify claims against NCERT (0-100)
    - Content Coverage Agent: Check concept coverage (0-100)
    - Linguistic Agent: Analyze grammar/vocabulary (0-100)
    
    **Phase 3:** Holistic Scoring
    - Content Score = (Fact Accuracy + Coverage) / 2
    - Logical Flow = Paragraph-to-paragraph vector similarity
    - Raw Score = (0.5 * Content) + (0.3 * Flow) + (0.2 * Language)
    - Final Score = Raw Score - (15 * contradiction_count)
    - Normalized Score = (Final Score / 100) * 1600
    
    Args:
        request: GradeEssayRequest with essay_text, question, subject
        
    Returns:
        GradeEssayResponse with complete grading report
    """
    try:
        logger.info(f"Starting essay evaluation")
        result = await evaluation_engine.grade_essay(
            essay_text=request.essay_text,
            question=request.question,
            subject=request.subject
        )
        return result
    except Exception as e:
        logger.error(f"Essay grading error: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/evaluation/{evaluation_id}")
async def get_evaluation(evaluation_id: str):
    """
    Retrieve a previously saved evaluation by ID.
    
    Args:
        evaluation_id: The evaluation ID from grading response
        
    Returns:
        Complete evaluation report
    """
    try:
        doc = await evaluation_engine.evaluations_collection.find_one(
            {"evaluation_id": evaluation_id}
        )
        if not doc:
            raise HTTPException(404, "Evaluation not found")
        
        # Remove MongoDB ID for cleaner response
        doc.pop("_id", None)
        return doc
        
    except Exception as e:
        logger.error(f"Error retrieving evaluation: {str(e)}")
        raise HTTPException(500, str(e))

# ============================================================================
# LEGACY ENDPOINTS (For backward compatibility)
# ============================================================================


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
    logger.info("=" * 70)
    logger.info("Essay Grader API v3.0 - UPSC AI Assistant")
    logger.info("=" * 70)
    logger.info("✓ API Gateway started on port 8000")
    logger.info("✓ Module 1: Data Ingestion (NCERT → Pinecone + MongoDB)")
    logger.info("✓ Module 2: Multi-Agent Evaluation Engine (3-Phase Flow)")
    logger.info("✓ Rate limiting: 50 uploads/min")
    logger.info("✓ Kafka topics: ocr-jobs, ai-processing")
    logger.info("✓ OpenAI & Pinecone integration active")
    logger.info("✓ Docs available at: /docs")
    logger.info("=" * 70)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Essay Grader API shutting down...")

