"""
Module 2: Essay Evaluation Engine (3-Phase Flow with Multi-Agent System)

Three phases:
1. Shadow Rubric: Generate answer key from RAG system
2. Extraction & Parsing: Extract claims and discourse markers
3. Parallel Agent Execution: Fact-checking, content coverage, linguistic analysis
"""

import asyncio
import numpy as np
from typing import List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pinecone import Pinecone
from openai import AsyncOpenAI
from sklearn.metrics.pairwise import cosine_similarity
from app.core.config import settings
import logging
import re

logger = logging.getLogger(__name__)

class EssayEvaluationEngine:
    """
    Multi-agent essay grading system using shadow rubric and claim verification.
    """
    
    def __init__(self, mongo_db: AsyncIOMotorDatabase):
        """
        Initialize the evaluation engine.
        
        Args:
            mongo_db: Motor AsyncIOMotorDatabase instance
        """
        self.mongo_db = mongo_db
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.pinecone_client = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.parent_docs_collection = mongo_db[settings.MONGO_PARENT_DOCS_COLLECTION]
        self.shadow_graphs_collection = mongo_db[settings.MONGO_SHADOW_GRAPHS_COLLECTION]
        self.evaluations_collection = mongo_db[settings.MONGO_ESSAY_EVALUATIONS_COLLECTION]
    
    # ========================================================================
    # PHASE 0: SHADOW RUBRIC (Dynamic Benchmarking)
    # ========================================================================
    
    async def _query_pinecone(
        self, 
        query_text: str, 
        subject: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query Pinecone index for similar content.
        
        Args:
            query_text: Query text
            subject: Subject name
            top_k: Number of top results to retrieve
            
        Returns:
            List of retrieved documents with parent content
        """
        try:
            # Get embedding for query
            response = await self.openai_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=query_text
            )
            query_embedding = response.data[0].embedding
            
            # Query Pinecone
            index_name = settings.PINECONE_INDICES.get(subject.lower(), f"{subject.lower()}-index")
            index = self.pinecone_client.Index(index_name)
            
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True
            )
            
            # Fetch parent documents from MongoDB
            retrieved_docs = []
            for match in results.get("matches", []):
                parent_id = match["metadata"].get("parent_id")
                if parent_id:
                    parent_doc = await self.parent_docs_collection.find_one(
                        {"_id": parent_id}
                    )
                    if parent_doc:
                        retrieved_docs.append({
                            "parent_id": parent_id,
                            "text": parent_doc.get("text", ""),
                            "grade": parent_doc.get("grade"),
                            "topic": match["metadata"].get("topic", ""),
                            "score": match.get("score", 0)
                        })
            
            return retrieved_docs
            
        except Exception as e:
            logger.error(f"Error querying Pinecone: {str(e)}")
            return []
    
    async def _extract_concepts(self, text: str) -> List[str]:
        """
        Extract key concepts from text using LLM.
        
        Args:
            text: Text to extract concepts from
            
        Returns:
            List of key concepts
        """
        prompt = f"""Extract the top 15 most important concepts, keywords, or facts from this text.
Return them as a comma-separated list.

Text:
{text}

Concepts:"""
        
        response = await self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        
        concepts_text = response.choices[0].message.content.strip()
        concepts = [c.strip() for c in concepts_text.split(",")]
        return concepts[:15]  # Limit to 15
    
    async def create_shadow_rubric(
        self, 
        question: str, 
        subject: str
    ) -> Dict[str, Any]:
        """
        Create shadow rubric (answer key) from retrieved NCERT content.
        
        Phase 0 of evaluation.
        
        Args:
            question: User's essay question
            subject: Subject domain
            
        Returns:
            Shadow rubric with must-have concepts
        """
        try:
            logger.info(f"Creating shadow rubric for: {question[:50]}...")
            
            # Query RAG system with the question
            retrieved_docs = await self._query_pinecone(question, subject, top_k=5)
            
            if not retrieved_docs:
                logger.warning("No documents retrieved for shadow rubric")
                return {
                    "status": "warning",
                    "concepts": [],
                    "retrieved_docs": []
                }
            
            # Combine retrieved texts
            combined_text = " ".join([doc["text"] for doc in retrieved_docs])
            
            # Extract concepts
            concepts = await self._extract_concepts(combined_text)
            
            shadow_rubric = {
                "question": question,
                "subject": subject.lower(),
                "concepts": concepts,
                "retrieved_docs": retrieved_docs,
                "created_at": asyncio.get_event_loop().time()
            }
            
            # Store in MongoDB for reference
            await self.shadow_graphs_collection.insert_one(shadow_rubric)
            
            logger.info(f"✓ Shadow rubric created with {len(concepts)} concepts")
            
            return {
                "status": "success",
                "concepts": concepts,
                "concept_count": len(concepts),
                "retrieved_docs": retrieved_docs
            }
            
        except Exception as e:
            logger.error(f"Error creating shadow rubric: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    # ========================================================================
    # PHASE 1: EXTRACTION & PARSING
    # ========================================================================
    
    async def extract_atomic_claims(self, essay_text: str) -> List[str]:
        """
        Extract atomic claims from essay using LLM.
        
        Args:
            essay_text: Student's essay
            
        Returns:
            List of atomic claims
        """
        prompt = f"""Extract 5-10 atomic claims (factual statements) from this essay.
Each claim should be a single, specific factual assertion.
Return them as a numbered list.

Essay:
{essay_text}

Atomic Claims:"""
        
        response = await self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        
        claims_text = response.choices[0].message.content.strip()
        # Parse numbered list
        claims = re.findall(r'\d+\.\s*(.+?)(?=\n\d+\.|\Z)', claims_text, re.DOTALL)
        claims = [c.strip() for c in claims if c.strip()]
        return claims
    
    async def extract_discourse_markers(self, essay_text: str) -> Dict[str, int]:
        """
        Extract discourse markers to measure logical flow.
        
        Args:
            essay_text: Student's essay
            
        Returns:
            Count of discourse markers by type
        """
        discourse_patterns = {
            "causative": r'\b(because|since|as|caused|due to|resulted in)\b',
            "contrastive": r'\b(however|but|yet|although|though|whereas|unlike|despite)\b',
            "additive": r'\b(moreover|furthermore|additionally|also|and|besides)\b',
            "conclusive": r'\b(therefore|thus|hence|consequently|as a result|in conclusion)\b',
            "sequential": r'\b(then|next|first|second|finally|subsequently)\b'
        }
        
        markers_count = {}
        for marker_type, pattern in discourse_patterns.items():
            count = len(re.findall(pattern, essay_text, re.IGNORECASE))
            markers_count[marker_type] = count
        
        return markers_count
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split essay into paragraphs."""
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        return paragraphs
    
    # ========================================================================
    # PHASE 2: PARALLEL AGENT EXECUTION
    # ========================================================================
    
    async def fact_checker_agent(
        self, 
        claims: List[str],
        subject: str
    ) -> Dict[str, Any]:
        """
        Agent 1: Verify factual claims against NCERT content.
        
        Args:
            claims: List of atomic claims
            subject: Subject domain
            
        Returns:
            Fact accuracy score and detailed findings
        """
        logger.info(f"Fact Checker Agent: Processing {len(claims)} claims")
        
        verified_claims = []
        contradiction_count = 0
        
        for claim in claims:
            try:
                # Query Pinecone for relevant content
                retrieved = await self._query_pinecone(claim, subject, top_k=3)
                
                if not retrieved:
                    # No supporting document found
                    verified_claims.append({
                        "claim": claim,
                        "status": "unverified",
                        "confidence": 0.0
                    })
                    continue
                
                # Use LLM to verify claim against retrieved content
                combined_text = " ".join([doc["text"] for doc in retrieved])
                
                verification_prompt = f"""Does the following retrieved content support, contradict, or is neutral to the claim?

Claim: {claim}

Retrieved Content:
{combined_text}

Answer with ONLY one word: SUPPORTED, CONTRADICTED, or NEUTRAL"""
                
                response = await self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": verification_prompt}],
                    temperature=0,
                    max_tokens=10
                )
                
                status = response.choices[0].message.content.strip().upper()
                
                if status == "CONTRADICTED":
                    contradiction_count += 1
                    verified_claims.append({
                        "claim": claim,
                        "status": "contradicted",
                        "confidence": 1.0
                    })
                elif status == "SUPPORTED":
                    verified_claims.append({
                        "claim": claim,
                        "status": "supported",
                        "confidence": 0.9
                    })
                else:
                    verified_claims.append({
                        "claim": claim,
                        "status": "neutral",
                        "confidence": 0.5
                    })
                    
            except Exception as e:
                logger.error(f"Error verifying claim '{claim}': {str(e)}")
                verified_claims.append({
                    "claim": claim,
                    "status": "error",
                    "confidence": 0.0
                })
        
        # Calculate accuracy score
        supported_count = sum(1 for c in verified_claims if c["status"] == "supported")
        accuracy_score = (supported_count / len(verified_claims) * 100) if verified_claims else 0
        
        return {
            "agent": "fact_checker",
            "verified_claims": verified_claims,
            "accuracy_score": accuracy_score,
            "contradiction_count": contradiction_count,
            "supported_count": supported_count,
            "total_claims": len(verified_claims)
        }
    
    async def content_coverage_agent(
        self, 
        essay_text: str,
        shadow_concepts: List[str]
    ) -> Dict[str, Any]:
        """
        Agent 2: Check how many must-have concepts are covered in the essay.
        
        Args:
            essay_text: Student's essay
            shadow_concepts: Must-have concepts from shadow rubric
            
        Returns:
            Coverage score and concept details
        """
        logger.info(f"Content Coverage Agent: Checking {len(shadow_concepts)} concepts")
        
        covered_concepts = []
        
        for concept in shadow_concepts:
            # Case-insensitive search
            if re.search(rf'\b{re.escape(concept)}\b', essay_text, re.IGNORECASE):
                covered_concepts.append({
                    "concept": concept,
                    "covered": True
                })
            else:
                covered_concepts.append({
                    "concept": concept,
                    "covered": False
                })
        
        coverage_score = (len([c for c in covered_concepts if c["covered"]]) / len(covered_concepts) * 100) if covered_concepts else 0
        
        return {
            "agent": "content_coverage",
            "covered_concepts": covered_concepts,
            "coverage_score": coverage_score,
            "concepts_covered": len([c for c in covered_concepts if c["covered"]]),
            "total_concepts": len(covered_concepts)
        }
    
    async def linguistic_agent(self, essay_text: str) -> Dict[str, Any]:
        """
        Agent 3: Analyze grammar, vocabulary, and UPSC-suitable tone.
        
        Args:
            essay_text: Student's essay
            
        Returns:
            Language score and feedback
        """
        logger.info("Linguistic Agent: Analyzing essay quality")
        
        analysis_prompt = f"""Analyze this essay for UPSC standards. Provide:
1. Grammar Quality (0-100)
2. Vocabulary Level (0-100)
3. Tone/Formality Appropriateness (0-100)
4. Overall Writing Quality (0-100)

Return ONLY JSON format with these exact keys: grammar_score, vocabulary_score, tone_score, overall_score

Essay (first 500 words):
{essay_text[:500]}

JSON:"""
        
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0,
                max_tokens=200
            )
            
            # Parse response (try to extract JSON)
            import json
            response_text = response.choices[0].message.content.strip()
            
            # Try to find JSON in response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                scores = json.loads(json_match.group())
            else:
                # Default scores if parsing fails
                scores = {
                    "grammar_score": 70,
                    "vocabulary_score": 70,
                    "tone_score": 70,
                    "overall_score": 70
                }
            
            language_score = (
                scores.get("grammar_score", 0) * 0.3 +
                scores.get("vocabulary_score", 0) * 0.4 +
                scores.get("tone_score", 0) * 0.3
            )
            
            return {
                "agent": "linguistic",
                "grammar_score": scores.get("grammar_score", 0),
                "vocabulary_score": scores.get("vocabulary_score", 0),
                "tone_score": scores.get("tone_score", 0),
                "language_score": language_score,
                "overall_score": scores.get("overall_score", 0)
            }
            
        except Exception as e:
            logger.error(f"Error in linguistic analysis: {str(e)}")
            return {
                "agent": "linguistic",
                "grammar_score": 50,
                "vocabulary_score": 50,
                "tone_score": 50,
                "language_score": 50,
                "overall_score": 50
            }
    
    # ========================================================================
    # PHASE 3: HOLISTIC SCORER
    # ========================================================================
    
    async def calculate_logical_flow(self, essay_text: str) -> float:
        """
        Calculate logical flow via paragraph-to-paragraph vector similarity.
        
        Args:
            essay_text: Student's essay
            
        Returns:
            Logical flow score (0-100)
        """
        paragraphs = self._split_into_paragraphs(essay_text)
        
        if len(paragraphs) < 2:
            return 50.0  # Default for single paragraph
        
        try:
            # Get embeddings for all paragraphs
            responses = await asyncio.gather(*[
                self.openai_client.embeddings.create(
                    model=settings.EMBEDDING_MODEL,
                    input=p
                )
                for p in paragraphs
            ])
            
            embeddings = [r.data[0].embedding for r in responses]
            
            # Calculate cosine similarity between consecutive paragraphs
            similarities = []
            for i in range(len(embeddings) - 1):
                sim = cosine_similarity(
                    [embeddings[i]], 
                    [embeddings[i + 1]]
                )[0][0]
                similarities.append(sim)
            
            # Average similarity as logical flow
            logical_flow = (np.mean(similarities) * 100) if similarities else 50.0
            return min(100.0, max(0.0, logical_flow))
            
        except Exception as e:
            logger.error(f"Error calculating logical flow: {str(e)}")
            return 50.0
    
    async def grade_essay(
        self,
        essay_text: str,
        question: str,
        subject: str = "general-studies"
    ) -> Dict[str, Any]:
        """
        Complete essay grading pipeline (Phases 0-3).
        
        Args:
            essay_text: Student's essay
            question: Essay question
            subject: Subject domain
            
        Returns:
            Complete grading report with final score
        """
        evaluation_id = str(asyncio.get_event_loop().time())
        
        try:
            logger.info(f"Starting essay evaluation: {evaluation_id}")
            
            # PHASE 0: Create shadow rubric
            shadow_result = await self.create_shadow_rubric(question, subject)
            shadow_concepts = shadow_result.get("concepts", [])
            
            # PHASE 1: Extract claims and discourse markers
            claims = await self.extract_atomic_claims(essay_text)
            discourse_markers = await self.extract_discourse_markers(essay_text)
            
            # PHASE 2: Run three agents in parallel
            agent_results = await asyncio.gather(
                self.fact_checker_agent(claims, subject),
                self.content_coverage_agent(essay_text, shadow_concepts),
                self.linguistic_agent(essay_text)
            )
            
            fact_checker_result = agent_results[0]
            content_coverage_result = agent_results[1]
            linguistic_result = agent_results[2]
            
            # Calculate logical flow
            logical_flow = await self.calculate_logical_flow(essay_text)
            
            # PHASE 3: Holistic scoring
            fact_accuracy_score = fact_checker_result.get("accuracy_score", 0)
            coverage_score = content_coverage_result.get("coverage_score", 0)
            language_score = linguistic_result.get("language_score", 0)
            
            # Content Score = average of fact accuracy and coverage
            content_score = (fact_accuracy_score + coverage_score) / 2
            
            # Raw Score calculation
            raw_score = (
                (0.5 * content_score) +
                (0.3 * logical_flow) +
                (0.2 * language_score)
            )
            
            # Apply penalty for contradictions (-15 points each)
            contradiction_penalty = fact_checker_result.get("contradiction_count", 0) * 15
            final_score = max(0, raw_score - contradiction_penalty)
            
            # Normalize to 0-1600 range
            normalized_score = (final_score / 100) * 1600
            
            # Build comprehensive report
            evaluation_report = {
                "evaluation_id": evaluation_id,
                "question": question,
                "subject": subject,
                "essay_preview": essay_text[:200],
                
                # Phase results
                "phase_0_shadow_rubric": {
                    "concepts": shadow_concepts,
                    "concept_count": len(shadow_concepts)
                },
                "phase_1_extraction": {
                    "claims": claims,
                    "claim_count": len(claims),
                    "discourse_markers": discourse_markers
                },
                "phase_2_agents": {
                    "fact_checker": fact_checker_result,
                    "content_coverage": content_coverage_result,
                    "linguistic": linguistic_result
                },
                
                # Scoring breakdown
                "scoring": {
                    "fact_accuracy_score": fact_accuracy_score,
                    "coverage_score": coverage_score,
                    "content_score": content_score,
                    "logical_flow": logical_flow,
                    "language_score": language_score,
                    "raw_score": raw_score,
                    "contradiction_penalty": contradiction_penalty,
                    "final_score": final_score,
                    "normalized_score_0_1600": normalized_score
                },
                
                # Grade assignment
                "grade": self._assign_grade(normalized_score),
                "feedback": self._generate_feedback(fact_checker_result, content_coverage_result, linguistic_result)
            }
            
            # Store evaluation in MongoDB
            await self.evaluations_collection.insert_one(evaluation_report)
            
            logger.info(f"✓ Essay evaluation completed: {evaluation_id}")
            
            return evaluation_report
            
        except Exception as e:
            logger.error(f"Error grading essay: {str(e)}")
            return {
                "status": "error",
                "evaluation_id": evaluation_id,
                "message": str(e)
            }
    
    def _assign_grade(self, score: float) -> str:
        """Assign letter grade based on normalized score."""
        if score >= 1440:
            return "A+"
        elif score >= 1280:
            return "A"
        elif score >= 1120:
            return "B+"
        elif score >= 960:
            return "B"
        elif score >= 800:
            return "C+"
        elif score >= 640:
            return "C"
        elif score >= 480:
            return "D"
        else:
            return "F"
    
    def _generate_feedback(
        self, 
        fact_checker: Dict,
        content_coverage: Dict,
        linguistic: Dict
    ) -> str:
        """Generate personalized feedback based on agent results."""
        feedback_points = []
        
        # Fact-checking feedback
        if fact_checker.get("accuracy_score", 0) < 60:
            feedback_points.append("⚠️ Low factual accuracy. Review claims against reference material.")
        else:
            feedback_points.append("✓ Good factual accuracy demonstrated.")
        
        # Coverage feedback
        if content_coverage.get("coverage_score", 0) < 60:
            feedback_points.append("⚠️ Missing key concepts. Include more required concepts.")
        else:
            feedback_points.append("✓ Good coverage of required concepts.")
        
        # Language feedback
        if linguistic.get("language_score", 0) < 60:
            feedback_points.append("⚠️ Improve grammar and vocabulary for UPSC standards.")
        else:
            feedback_points.append("✓ Good writing quality and language use.")
        
        return " ".join(feedback_points)
