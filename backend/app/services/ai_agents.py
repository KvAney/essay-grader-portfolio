# services/ai_agents.py
"""
AI Agents Service - Deprecated in v2.0

NOTE: This module is deprecated. Use AIOrchestrator from app.utils.ai_orchestrator instead.

The old single-call approach has been replaced with the Orchestrator pattern
that runs 4 parallel AI analysis tasks concurrently with proper rate limiting.

Legacy function kept for reference only.
"""

from langchain_groq import ChatGroq
from app.core.config import settings

# Setup Groq (Free Tier)
llm = ChatGroq(
    temperature=0,
    groq_api_key=settings.GROQ_API_KEY,
    model_name="llama3-70b-8192"
)

async def grade_essay(text):
    """
    DEPRECATED: Use AIOrchestrator.orchestrate() instead.
    
    This was the v1.0 approach - single AI call.
    Now we run 4 parallel calls for comprehensive analysis.
    """
    try:
        prompt = f"Grade this essay on grammar and logic (0-100): {text}"
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        return f"AI Error: {str(e)}"

