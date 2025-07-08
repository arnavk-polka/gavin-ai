import os
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from config import openai_client, static_path, logger
from analyze.orchestrator import AnalyzeOrchestrator
import time
from utils.utils import add_memory

# Initialize the analyze router
analyze_router = APIRouter(prefix="/analyze")

# Global orchestrator instance
orchestrator = None

class AnalyzeRequest(BaseModel):
    transcript: str
    session_name: Optional[str] = None

class MultiTurnTestRequest(BaseModel):
    messages: List[Dict[str, str]]  # List of {"role": str, "content": str}
    session_name: Optional[str] = None

class ContentAnalysisRequest(BaseModel):
    text: str
    session_name: Optional[str] = None

def get_orchestrator():
    """Get or create the analyze orchestrator instance."""
    global orchestrator
    if orchestrator is None:
        # We need to create a gavin bot handler that matches the existing chat interface
        orchestrator = AnalyzeOrchestrator(
            openai_client=openai_client,
            gavin_bot_handler=create_gavin_bot_handler(),
            use_mt_bench=True  # Enable MT-Bench evaluation
        )
    return orchestrator

def create_gavin_bot_handler():
    """
    Create a handler function that interfaces with the existing GavinBot chat system.
    This mimics the existing chat endpoint behavior.
    """
    
    async def get_openai_response_sync(prompt):
        """Get OpenAI response without streaming for analyzer use."""
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.5,
                top_p=0.9,
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error getting OpenAI response: {e}")
            raise e
    
    async def gavin_bot_handler(handle: str, message: dict):
        """
        Handler that calls the existing chat logic and returns streamed response.
        """
        try:
            # Import here to avoid circular imports
            from routes import get_memories_with_timeout, preprocess_tweet
            from config import mem0_client
            
            user_id = f"gavinwood"
            query_text = preprocess_tweet(message["message"], is_query=True)
            
            # Get memories (with timeout)
            memories = await get_memories_with_timeout(user_id, query_text, limit=4, timeout=2.0)
            memories_with_scores = [(mem["memory"], mem.get("score", 0.0)) for mem in memories]
            
            # Build persona context (matching prompt_builder.py)
            persona = {
                "name": "Gavin Wood",
                "summary": """Gavin Wood is the founder of Polkadot and co-founder of Ethereum, known for his work on blockchain architecture and Web3 infrastructure. He created the Solidity programming language and wrote the Ethereum Yellow Paper. Gavin is focused on building interoperable blockchain networks and advancing Web3 technology."""
            }
            
            # Build persona context
            persona_context_parts = []
            if summary := persona.get("summary"):
                persona_context_parts.append(f"Persona Summary:\n{summary}")
            persona_context = "\n\n".join(persona_context_parts)
            
            # Format conversation history (simplified for stress test)
            conversation_history = ""
            
            # Create the prompt
            from prompt_builder import craft
            prompt = await craft(
                persona=persona,
                memories_with_scores=memories_with_scores,
                history=[f"User: {message['message']}"],
                extra_persona_context=persona_context
            )
            
            # Get response using non-streaming method
            full_response = await get_openai_response_sync(prompt)
            
            # Store only AI response as memory in background
            try:
                import threading
                def store_ai_memory():
                    try:
                        result = add_memory(mem0_client, user_id, f"Assistant: {full_response}", {"role": "assistant"})
                        logger.info(f"Analyze memory storage result: {result}")
                    except Exception as e:
                        logger.warning(f"Failed to store AI memory in analyze: {e}")
                
                threading.Thread(target=store_ai_memory, daemon=True).start()
            except Exception as e:
                logger.warning(f"Failed to start memory storage thread in analyze: {e}")
            
            return full_response
            
        except Exception as e:
            logger.error(f"Error in gavin bot handler: {e}")
            raise e
    
    return gavin_bot_handler

@analyze_router.post("/start")
async def start_analyze(request: AnalyzeRequest):
    """Start a new analyze session."""
    try:
        orchestrator = get_orchestrator()
        
        logger.info(f"Starting analyze with transcript length: {len(request.transcript)} chars")
        
        result = await orchestrator.start_stress_test(
            transcript_text=request.transcript,
            session_name=request.session_name
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error starting analyze: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/status")
async def get_analyze_status():
    """Get current analyze session status."""
    try:
        orchestrator = get_orchestrator()
        status = orchestrator.get_session_status()
        
        if not status:
            raise HTTPException(status_code=404, detail="No active analyze session")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analyze status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/results")
async def get_analyze_results():
    """Get detailed results from completed analyze session."""
    try:
        orchestrator = get_orchestrator()
        results = orchestrator.get_detailed_results()
        
        if not results:
            raise HTTPException(status_code=404, detail="No completed analyze results available")
        
        # Add MT-Bench analysis if available
        if "mt_bench_analysis" in results:
            results["mt_bench_available"] = True
            results["mt_bench_summary"] = {
                "average_overall_score": results["mt_bench_analysis"]["average_overall_score"],
                "pass_rate": results["mt_bench_analysis"]["pass_rate"],
                "total_evaluations": results["mt_bench_analysis"]["total_evaluations"],
                "dimension_averages": {
                    "avg_relevance": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("relevance", {}).get("average_score", 0.0),
                    "avg_accuracy": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("accuracy", {}).get("average_score", 0.0),
                    "avg_clarity": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("clarity", {}).get("average_score", 0.0),
                    "avg_depth": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("depth", {}).get("average_score", 0.0),
                    "avg_helpfulness": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("helpfulness", {}).get("average_score", 0.0)
                },
                "score_distribution": results["mt_bench_analysis"]["score_distribution"],
                "common_strengths": results["mt_bench_analysis"]["common_strengths"],
                "common_weaknesses": results["mt_bench_analysis"]["common_weaknesses"]
            }
            
            # Add individual evaluations for frontend access
            if "individual_evaluations" in results["mt_bench_analysis"]:
                results["evaluated_results"] = []
                for eval_data in results["mt_bench_analysis"]["individual_evaluations"]:
                    results["evaluated_results"].append({
                        "question": eval_data.get("question", ""),
                        "bot_response": eval_data.get("bot_response", ""),
                        "expected_answer": eval_data.get("expected_answer", ""),
                        "evaluation": {
                            "overall_score": eval_data.get("overall_score", 0.0),
                            "mt_bench_scores": eval_data.get("dimension_scores", {}),
                            "confidence": eval_data.get("confidence", 0.0),
                            "reasoning": eval_data.get("reasoning", {}),
                            "evaluation_method": "mt_bench"
                        }
                    })
        else:
            results["mt_bench_available"] = False
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analyze results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.post("/multi-turn/start")
async def start_multi_turn_test(request: MultiTurnTestRequest):
    """Start a new multi-turn test session."""
    try:
        orchestrator = get_orchestrator()
        
        logger.info(f"Starting multi-turn test with {len(request.messages)} messages")
        
        result = await orchestrator.start_multi_turn_test(
            messages=request.messages,
            session_name=request.session_name
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error starting multi-turn test: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/multi-turn/status")
async def get_multi_turn_status():
    """Get current multi-turn test session status."""
    try:
        orchestrator = get_orchestrator()
        status = orchestrator.get_multi_turn_status()
        
        if not status:
            raise HTTPException(status_code=404, detail="No active multi-turn test session")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting multi-turn test status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/multi-turn/results")
async def get_multi_turn_results():
    """Get detailed results from completed multi-turn test session."""
    try:
        orchestrator = get_orchestrator()
        results = orchestrator.get_multi_turn_results()
        
        if not results:
            raise HTTPException(status_code=404, detail="No completed multi-turn test results available")
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting multi-turn test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.post("/content")
async def analyze_content(request: ContentAnalysisRequest):
    """Analyze content for promptability and get GavinBot's response using analyze infrastructure."""
    try:
        content_text = request.text
        if not content_text:
            raise HTTPException(status_code=400, detail="No content provided")

        # First check if the content is promptable
        promptability_check = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a content analyzer. Determine if the given text would make a good prompt for a technical discussion about blockchain, crypto, or technology. Respond with ONLY 'YES' or 'NO'."},
                {"role": "user", "content": content_text}
            ],
            temperature=0.3
        )
        
        is_promptable = "YES" in promptability_check.choices[0].message.content
        
        if not is_promptable:
            return {
                "is_promptable": False,
                "analysis": "NO",
                "response": None,
                "question": content_text
            }

        # Get orchestrator instance
        orchestrator = get_orchestrator()
        
        # Check if content is too long (>50 words) and needs to be broken into questions
        word_count = len(content_text.split())
        
        if word_count > 50:  # Lowered threshold to ensure more content gets processed
            # For long content, use content analysis method
            session_result = await orchestrator.start_content_analysis(
                content_text=content_text,
                session_name=request.session_name or f"Content_Analysis_{int(time.time())}"
            )
            
            return {
                "is_promptable": True,
                "analysis": "YES - Processing as multiple questions",
                "session_id": session_result["session_id"],
                "is_multi_question": True,
                "processing": True
            }
        else:
            # For short content, treat as single question and use analyze infrastructure
            # Create a simple question format
            questions = [content_text]
            
            # Use tester AI to fire single question
            tester_ai = orchestrator.tester_ai
            test_results = await tester_ai.fire_questions_sequentially(
                questions, 
                orchestrator._handle_question_callback
            )
            
            # Get the response
            if test_results and len(test_results) > 0:
                result = test_results[0]
                return {
                    "is_promptable": True,
                    "analysis": "YES",
                    "response": result.get("bot_response", "No response generated"),
                    "question": content_text,
                    "questions_asked": [content_text],
                    "is_multi_question": False
                }
            else:
                return {
                    "is_promptable": True,
                    "analysis": "YES",
                    "response": "Failed to generate response",
                    "question": content_text,
                    "is_multi_question": False
                }

    except Exception as e:
        logger.error(f"Error analyzing content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/content/status/{session_id}")
async def get_content_analysis_status(session_id: int):
    """Get content analysis session status by session ID."""
    try:
        orchestrator = get_orchestrator()
        status = orchestrator.get_session_status()
        
        if not status or status.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Content analysis session not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting content analysis status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/content/results/{session_id}")
async def get_content_analysis_results(session_id: int):
    """Get detailed results from completed content analysis session."""
    try:
        orchestrator = get_orchestrator()
        results = orchestrator.get_detailed_results()
        
        if not results or not results.get("session_info") or results["session_info"].get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="Content analysis results not found")
        
        # Add top-level fields for easier access in frontend
        results["session_id"] = results["session_info"]["session_id"]
        results["questions"] = [pair.get("question", "") for pair in results.get("qa_pairs", [])]
        results["test_results"] = orchestrator.current_session.get("test_results", []) if orchestrator.current_session else []
        
        # Add MT-Bench analysis if available
        if "mt_bench_analysis" in results:
            results["mt_bench_available"] = True
            results["mt_bench_summary"] = {
                "average_overall_score": results["mt_bench_analysis"]["average_overall_score"],
                "pass_rate": results["mt_bench_analysis"]["pass_rate"],
                "total_evaluations": results["mt_bench_analysis"]["total_evaluations"],
                "dimension_averages": {
                    "avg_relevance": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("relevance", {}).get("average_score", 0.0),
                    "avg_accuracy": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("accuracy", {}).get("average_score", 0.0),
                    "avg_clarity": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("clarity", {}).get("average_score", 0.0),
                    "avg_depth": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("depth", {}).get("average_score", 0.0),
                    "avg_helpfulness": results["mt_bench_analysis"].get("dimension_breakdown", {}).get("helpfulness", {}).get("average_score", 0.0)
                },
                "score_distribution": results["mt_bench_analysis"]["score_distribution"],
                "common_strengths": results["mt_bench_analysis"]["common_strengths"],
                "common_weaknesses": results["mt_bench_analysis"]["common_weaknesses"]
            }
            
            # Add individual evaluations for frontend access
            if "individual_evaluations" in results["mt_bench_analysis"]:
                results["evaluated_results"] = []
                for eval_data in results["mt_bench_analysis"]["individual_evaluations"]:
                    results["evaluated_results"].append({
                        "question": eval_data.get("question", ""),
                        "bot_response": eval_data.get("bot_response", ""),
                        "expected_answer": eval_data.get("expected_answer", ""),
                        "evaluation": {
                            "overall_score": eval_data.get("overall_score", 0.0),
                            "mt_bench_scores": eval_data.get("dimension_scores", {}),
                            "confidence": eval_data.get("confidence", 0.0),
                            "reasoning": eval_data.get("reasoning", {}),
                            "evaluation_method": "mt_bench"
                        }
                    })
        else:
            results["mt_bench_available"] = False
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting content analysis results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@analyze_router.get("/health")
async def analyze_health():
    """Health check endpoint for analyze service."""
    try:
        return {
            "status": "healthy",
            "service": "analyze",
            "timestamp": "current"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@analyze_router.get("/")
async def redirect_to_dashboard():
    """Redirect root to dashboard."""
    return RedirectResponse(url="/dashboard") 