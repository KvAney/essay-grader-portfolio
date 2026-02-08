"""
Test suite for Groq API integration in EssayEvaluationEngine
Run: pytest backend/tests/test_groq_integration.py -v -s
"""

import pytest
import asyncio
from app.services.essay_evaluator import EssayEvaluationEngine
from app.db.mongo import db


def test_groq_extract_concepts():
    """Test Groq concept extraction"""
    async def run_test():
        engine = EssayEvaluationEngine(db)
        
        sample_text = """
        Democracy is a system of government where power is vested in the people.
        Citizens participate in decision-making through voting and representation.
        Key concepts include separation of powers, rule of law, and individual rights.
        Checks and balances ensure no single branch becomes too powerful.
        """
        
        concepts = await engine._extract_concepts(sample_text)
        
        print(f"\n✓ Extracted {len(concepts)} concepts:")
        for i, concept in enumerate(concepts, 1):
            print(f"  {i}. {concept}")
        
        assert isinstance(concepts, list)
        assert len(concepts) > 0
        assert len(concepts) <= 15
        assert all(isinstance(c, str) for c in concepts)
    
    asyncio.run(run_test())


def test_groq_extract_atomic_claims():
    """Test Groq atomic claim extraction"""
    async def run_test():
        engine = EssayEvaluationEngine(db)
        
        essay = """
        The Indian Constitution was adopted on January 26, 1950.
        Dr. Ambedkar chaired the Drafting Committee that created it.
        It guarantees fundamental rights to all citizens.
        The Preamble outlines the nation's objectives and ideals.
        The Constitution is the longest written constitution in the world.
        """
        
        claims = await engine.extract_atomic_claims(essay)
        
        print(f"\n✓ Extracted {len(claims)} atomic claims:")
        for i, claim in enumerate(claims, 1):
            print(f"  {i}. {claim}")
        
        assert isinstance(claims, list)
        assert len(claims) > 0
        assert all(isinstance(c, str) for c in claims)
    
    asyncio.run(run_test())


def test_groq_discourse_markers():
    """Test discourse marker extraction (does not use Groq, local regex)"""
    async def run_test():
        engine = EssayEvaluationEngine(db)
        
        essay = """
        First, democracy began in ancient Greece. However, modern democracy is different.
        Furthermore, it requires active citizen participation. Therefore, voting is crucial.
        Moreover, the branches of government check each other's power.
        """
        
        markers = await engine.extract_discourse_markers(essay)
        
        print(f"\n✓ Discourse markers detected:")
        for marker_type, count in markers.items():
            print(f"  {marker_type}: {count}")
        
        assert isinstance(markers, dict)
        assert "causative" in markers
        assert markers["additive"] > 0  # Should find "Furthermore", "Moreover"
    
    asyncio.run(run_test())


def test_groq_linguistic_agent():
    """Test Groq linguistic analysis"""
    async def run_test():
        engine = EssayEvaluationEngine(db)
        
        essay = """
        The Indian Constitution represents a remarkable achievement in democratic governance.
        It meticulously delineates the fundamental rights and duties of citizens.
        Furthermore, the constitutional framework establishes a robust system of checks and balances
        among the executive, legislative, and judicial branches of government.
        The preamble encapsulates the aspirational ideals of the nation.
        """
        
        result = await engine.linguistic_agent(essay)
        
        print(f"\n✓ Linguistic Analysis Results:")
        print(f"  Grammar Score: {result['grammar_score']}")
        print(f"  Vocabulary Score: {result['vocabulary_score']}")
        print(f"  Tone Score: {result['tone_score']}")
        print(f"  Language Score: {result['language_score']:.2f}")
        
        assert result["agent"] == "linguistic"
        assert "language_score" in result
        assert 0 <= result["language_score"] <= 100
    
    asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
