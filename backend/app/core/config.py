import os

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:ppt@localhost:5432/essay_eval_db")
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OCR_TOPIC = "ocr-jobs"
    AI_TOPIC = "ai-processing"
    
    # ============= NEW: Pinecone & OpenAI Configuration =============
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "us-east-1-aws")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536
    
    # Subject-wise Pinecone indices (per subject, not per grade)
    PINECONE_INDICES = {
        "history": "history-index",
        "geography": "geography-index",
        "political-science": "political-science-index",
        "economics": "economics-index",
        "general-studies": "general-studies-index"
    }
    
    # MongoDB collections for parent documents
    MONGO_PARENT_DOCS_COLLECTION = "parent_docs"
    MONGO_SHADOW_GRAPHS_COLLECTION = "shadow_graphs"
    MONGO_ESSAY_EVALUATIONS_COLLECTION = "essay_evaluations"
    
    # Chunking parameters
    PARENT_CHUNK_SIZE = 1000  # tokens
    CHILD_CHUNK_SIZE = 200    # tokens
    CHUNK_OVERLAP = 50        # tokens

settings = Settings()

