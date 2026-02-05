"""
Module 1: Data Ingestion Pipeline (NCERT → Pinecone + MongoDB)

This module implements the Parent-Child RAG strategy:
- Parent Chunk: Large context (~1000 tokens) stored in MongoDB
- Child Chunk: Small embeddings (~200 tokens) stored in Pinecone with parent_id linkage
"""

import asyncio
import fitz  # PyMuPDF
import tiktoken
from typing import List, Dict, Any, Tuple
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pinecone import Pinecone
from openai import AsyncOpenAI
from app.core.config import settings
from fastembed import TextEmbedding
import logging

logger = logging.getLogger(__name__)

class NCERTIngestionPipeline:
    """
    Handles NCERT PDF ingestion with Parent-Child chunking strategy.
    """
    
    def __init__(self, mongo_db: AsyncIOMotorDatabase):
        """
        Initialize the ingestion pipeline.
        
        Args:
            mongo_db: Motor AsyncIOMotorDatabase instance
        """
        self.mongo_db = mongo_db
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.pinecone_client = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        self.parent_docs_collection = mongo_db[settings.MONGO_PARENT_DOCS_COLLECTION]
        self.embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    
    def _extract_text_from_pdf(self, file_path: str) -> str:
        """
        Extract text from PDF file using PyMuPDF.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text from PDF
        """
        try:
            pdf_document = fitz.open(file_path)
            full_text = ""
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                full_text += page.get_text() + "\n"
            pdf_document.close()
            return full_text
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {str(e)}")
            raise
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))
    
    def _create_parent_chunks(self, text: str) -> List[str]:
        """
        Create parent chunks (~1000 tokens each).
        
        Args:
            text: Full document text
            
        Returns:
            List of parent chunks
        """
        sentences = text.split('. ')
        parent_chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            test_chunk = current_chunk + sentence + ". "
            token_count = self._count_tokens(test_chunk)
            
            if token_count > settings.PARENT_CHUNK_SIZE:
                if current_chunk:
                    parent_chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
            else:
                current_chunk = test_chunk
        
        if current_chunk.strip():
            parent_chunks.append(current_chunk.strip())
        
        return parent_chunks
    
    def _create_child_chunks(self, parent_chunk: str) -> List[str]:
        """
        Create child chunks (~200 tokens each) from a parent chunk.
        
        Args:
            parent_chunk: Parent chunk text
            
        Returns:
            List of child chunks
        """
        sentences = parent_chunk.split('. ')
        child_chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            test_chunk = current_chunk + sentence + ". "
            token_count = self._count_tokens(test_chunk)
            
            if token_count > settings.CHILD_CHUNK_SIZE:
                if current_chunk:
                    child_chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
            else:
                current_chunk = test_chunk
        
        if current_chunk.strip():
            child_chunks.append(current_chunk.strip())
        
        return child_chunks
    
    async def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding locally using FastEmbed (Free & Private).
        """
        try:
            # FastEmbed is synchronous (CPU bound). 
            # We run it in a thread executor to avoid blocking the asyncio event loop.
            loop = asyncio.get_running_loop()

            def generate():
                # embed() expects a list of documents and returns a generator
                # We consume the generator with list() and take the first result
                embeddings = list(self.embedding_model.embed([text]))
                return embeddings[0]

            # Run in background thread
            embedding_numpy = await loop.run_in_executor(None, generate)

            # Convert numpy array to standard python List[float]
            return embedding_numpy.tolist()

        except Exception as e:
            logger.error(f"Error getting embedding: {str(e)}")
            raise
    
    async def ingest_textbook(
        self, 
        file_path: str, 
        subject: str, 
        grade: int
    ) -> Dict[str, Any]:
        """
        Main ingestion function: Extract, chunk, embed, and store NCERT content.
        
        Args:
            file_path: Path to NCERT PDF
            subject: Subject name (e.g., 'History', 'Geography')
            grade: Grade level (6-12)
            
        Returns:
            Dictionary with ingestion statistics
        """
        try:
            logger.info(f"Starting ingestion: {subject} Grade {grade}")
            
            # Step 1: Extract text from PDF
            full_text = self._extract_text_from_pdf(file_path)
            logger.info(f"Extracted {len(full_text)} characters from PDF")
            
            # Step 2: Create parent chunks (~1000 tokens)
            parent_chunks = self._create_parent_chunks(full_text)
            logger.info(f"Created {len(parent_chunks)} parent chunks")
            
            # Step 3: For each parent chunk, create child chunks and embeddings
            parent_ids = []
            child_vectors = []
            
            for parent_idx, parent_chunk in enumerate(parent_chunks):
                # Store parent in MongoDB
                parent_doc = {
                    "subject": subject.lower(),
                    "grade": grade,
                    "text": parent_chunk,
                    "token_count": self._count_tokens(parent_chunk),
                    "parent_index": parent_idx,
                    "created_at": asyncio.get_event_loop().time()
                }
                
                result = await self.parent_docs_collection.insert_one(parent_doc)
                parent_id = str(result.inserted_id)
                parent_ids.append(parent_id)
                logger.info(f"Stored parent chunk {parent_idx} with ID: {parent_id}")
                
                # Create child chunks
                child_chunks = self._create_child_chunks(parent_chunk)
                
                for child_idx, child_chunk in enumerate(child_chunks):
                    # Get embedding for child chunk
                    embedding = await self._get_embedding(child_chunk)
                    
                    # Prepare vector for Pinecone
                    vector = {
                        "id": f"{parent_id}_{child_idx}",
                        "values": embedding,
                        "metadata": {
                            "parent_id": parent_id,
                            "grade": grade,
                            "subject": subject.lower(),
                            "child_index": child_idx,
                            "text_preview": child_chunk[:100]  # Store text preview
                        }
                    }
                    child_vectors.append(vector)
            
            # Step 4: Upsert all child vectors to Pinecone
            index_name = settings.PINECONE_INDICES.get(
                subject.lower(), 
                f"{subject.lower()}-index"
            )
            
            index = self.pinecone_client.Index(index_name)
            
            # Batch upsert (Pinecone limits batch size)
            batch_size = 100
            for i in range(0, len(child_vectors), batch_size):
                batch = child_vectors[i:i + batch_size]
                index.upsert(vectors=batch)
                logger.info(f"Upserted batch {i//batch_size + 1} to Pinecone")
            
            logger.info(f"✓ Ingestion completed for {subject} Grade {grade}")
            
            return {
                "status": "success",
                "subject": subject,
                "grade": grade,
                "parent_chunks_created": len(parent_chunks),
                "child_vectors_created": len(child_vectors),
                "parent_ids": parent_ids,
                "pinecone_index": index_name
            }
            
        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def ingest_batch(self, files: List[Tuple[str, str, int]]) -> Dict[str, Any]:
        """
        Ingest multiple NCERT files in parallel.
        
        Args:
            files: List of tuples (file_path, subject, grade)
            
        Returns:
            Aggregated ingestion results
        """
        tasks = [
            self.ingest_textbook(file_path, subject, grade)
            for file_path, subject, grade in files
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = [r for r in results if isinstance(r, dict) and r.get("status") == "success"]
        failed = [r for r in results if isinstance(r, dict) and r.get("status") == "error"]
        
        return {
            "total_files": len(files),
            "successful": len(successful),
            "failed": len(failed),
            "results": results
        }
