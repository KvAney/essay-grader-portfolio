# utils/ai_orchestrator.py
import asyncio
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from app.core.config import settings
from app.utils.rate_limiter import TokenBucketRateLimiter

class AIOrchestrator:
    """
    AI Orchestrator that runs multiple parallel AI analysis tasks.
    
    Fan-Out Pattern:
    1. Grammar Analysis
    2. Structure Analysis
    3. Logic & Reasoning Check
    4. Content Analysis
    
    All tasks run concurrently and results are aggregated.
    """
    
    def __init__(self, rate_limiter: TokenBucketRateLimiter = None):
        """
        Initialize the AI Orchestrator.
        
        Args:
            rate_limiter: TokenBucketRateLimiter instance for Groq API calls
        """
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(rate=20, per=60)
        self.llm = ChatGroq(
            temperature=0,
            groq_api_key=settings.GROQ_API_KEY,
            model_name="llama3-70b-8192"
        )
    
    async def _call_groq(self, prompt: str, task_name: str) -> str:
        """
        Call Groq API with rate limiting.
        
        Args:
            prompt: The prompt to send to Groq
            task_name: Name of the task (for logging)
        
        Returns:
            Response from Groq
        """
        await self.rate_limiter.acquire()
        print(f"[{task_name}] Calling Groq API...")
        try:
            response = await self.llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            return f"Error in {task_name}: {str(e)}"
    
    async def analyze_grammar(self, text: str) -> Dict[str, Any]:
        """
        Analyze essay grammar and writing quality.
        """
        prompt = f"""Analyze the following essay for grammar, spelling, and writing quality.
        
Essay:
{text}

Provide a detailed analysis with:
1. Grammar Score (0-100)
2. Identified errors with explanations
3. Suggestions for improvement
"""
        result = await self._call_groq(prompt, "Grammar Analysis")
        return {
            "task": "Grammar Analysis",
            "result": result
        }
    
    async def analyze_structure(self, text: str) -> Dict[str, Any]:
        """
        Analyze essay structure, organization, and flow.
        """
        prompt = f"""Analyze the structure and organization of the following essay.

Essay:
{text}

Evaluate:
1. Structure Score (0-100)
2. Introduction effectiveness
3. Paragraph organization and transitions
4. Conclusion quality
5. Overall flow and coherence
6. Recommendations for restructuring
"""
        result = await self._call_groq(prompt, "Structure Analysis")
        return {
            "task": "Structure Analysis",
            "result": result
        }
    
    async def analyze_logic(self, text: str) -> Dict[str, Any]:
        """
        Analyze logical reasoning and argumentation.
        """
        prompt = f"""Analyze the logical reasoning and argumentation in the following essay.

Essay:
{text}

Assess:
1. Logic Score (0-100)
2. Validity of arguments
3. Quality of evidence provided
4. Logical fallacies (if any)
5. Strength of reasoning
6. Suggestions for stronger argumentation
"""
        result = await self._call_groq(prompt, "Logic Analysis")
        return {
            "task": "Logic Analysis",
            "result": result
        }
    
    async def analyze_content(self, text: str) -> Dict[str, Any]:
        """
        Analyze content quality, relevance, and depth.
        """
        prompt = f"""Analyze the content quality and depth of the following essay.

Essay:
{text}

Evaluate:
1. Content Score (0-100)
2. Relevance to the topic
3. Depth of analysis
4. Key points covered
5. Missing elements or gaps
6. Overall informativeness
"""
        result = await self._call_groq(prompt, "Content Analysis")
        return {
            "task": "Content Analysis",
            "result": result
        }
    
    async def orchestrate(self, text: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Run all analysis tasks in parallel and aggregate results.
        
        Args:
            text: Essay text to analyze
            timeout: Maximum time to wait for all tasks (seconds)
        
        Returns:
            Dictionary containing all analysis results and aggregated score
        """
        try:
            # Run all 4 tasks concurrently
            tasks = [
                # changes= prompting divide
                self.analyze_grammar(text),
                self.analyze_structure(text),
                self.analyze_logic(text),
                self.analyze_content(text),
            ]
            
            # Wait for all tasks with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results
            analysis_results = {
                "tasks": [],
                "aggregated_feedback": None,
                "overall_score": 0
            }
            
            # Collect all task results
            scores = []
            for result in results:
                if isinstance(result, Exception):
                    print(f"Task failed: {result}")
                    analysis_results["tasks"].append({
                        "task": "Unknown",
                        "error": str(result)
                    })
                else:
                    analysis_results["tasks"].append(result)
                    # Try to extract score from result
                    if "Score" in result.get("result", ""):
                        try:
                            # Simple heuristic: look for "Score: XX" pattern
                            import re
                            match = re.search(r'Score[:\s]+(\d+)', result["result"])
                            if match:
                                scores.append(int(match.group(1)))
                        except:
                            pass
            
            # Calculate average score
            if scores:
                analysis_results["overall_score"] = sum(scores) / len(scores)
            
            # Create aggregated feedback
            analysis_results["aggregated_feedback"] = self._aggregate_feedback(
                analysis_results["tasks"]
            )
            
            return analysis_results
        
        except asyncio.TimeoutError:
            return {
                "error": "Analysis timed out",
                "timeout": timeout,
                "message": "Some or all analysis tasks took too long to complete"
            }
        except Exception as e:
            return {
                "error": str(e),
                "message": "Orchestration failed"
            }
    
    def _aggregate_feedback(self, tasks: List[Dict[str, Any]]) -> str:
        """
        Aggregate all task feedback into a summary.
        """
        summary = "=== COMPREHENSIVE ESSAY EVALUATION ===\n\n"
        
        for task in tasks:
            if "error" in task:
                summary += f"❌ {task.get('task', 'Unknown')}: {task['error']}\n"
            else:
                summary += f"✓ {task.get('task', 'Unknown')}:\n"
                summary += f"{task.get('result', 'No result')[:500]}...\n\n"
        
        summary += "\n=== RECOMMENDATIONS ===\n"
        summary += "1. Review all feedback above\n"
        summary += "2. Focus on the lowest scoring areas\n"
        summary += "3. Revise and resubmit for additional feedback\n"
        
        return summary
