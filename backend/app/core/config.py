import os

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ppt@localhost:5432/essay_eval_db")
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OCR_TOPIC = "ocr-jobs"
    AI_TOPIC = "ai-processing"

settings = Settings()
