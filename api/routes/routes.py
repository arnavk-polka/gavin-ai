import json
import os
import asyncio
import traceback
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from config import app, logger, openai_client, static_path, mem0_client
from utils.utils import preprocess_tweet, add_memory, get_relevant_memories
from prompt_builder import craft
from .memory_routes import memory_router
from .analyze_routes import analyze_router
from preprocess.preprocess_routes import deep_debug_router
from response_generation import tone_bleurt_gate, enhance_query_context, format_context_enhancement
import time
from utils.route_helpers import (
    stream_openai_response,
    get_memories_with_timeout,
    should_search_web,
    test_serper_connection,
    search_serper,
    store_memories_async
)

router = APIRouter()





@router.get("/debug")
async def debug_redirect():
    """Redirect to /debug/ for consistency"""
    return RedirectResponse(url="/debug/")

@router.get("/debug/")
async def debug_page():
    """Serve the chat interface with debug panel enabled."""
    logger.info("Serving debug page")
    index_path = os.path.join(static_path, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    else:
        return HTMLResponse(
            content="<h1>Chat Interface Not Found</h1><p>Please ensure index.html is available in the static directory.</p>",
            status_code=404
        )

@router.get("/")
async def read_root():
    """Serve the chat interface from static/index.html."""
    logger.info("Serving index.html")
    index_path = os.path.join(static_path, "index.html")
    logger.info(f"Checking for index.html at: {index_path}")
    if os.path.isfile(index_path):
        logger.info(f"Found index.html at {index_path}")
        return FileResponse(index_path)
    else:
        logger.error(f"index.html not found at {index_path}")
        return HTMLResponse(
            content="<h1>Chat Interface Not Found</h1><p>Please ensure index.html is available in the static directory.</p>",
            status_code=404
        )

@router.get("/health")
async def health_check():
    """Health check endpoint for deployment monitoring."""
    try:
        # Test OpenAI connection with a minimal request
        test_response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1
        )
        
        return {
            "status": "healthy",
            "openai": "connected",
            "mem0": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@router.post("/chat/{handle}")
async def chat(handle: str, message: dict, request: Request, background_tasks: BackgroundTasks):
    """Chat endpoint that returns a streaming response."""
    logger.info(f"Chat request for handle: {handle}, message: {message.get('message', '')[:50]}...")
    try:
        client_host = request.client.host
        user_agent = request.headers.get("user-agent", "")
        logger.info(f"Request from client: {client_host}, User-Agent: {user_agent}")
        
        user_message = message["message"]
        
        # Step 1: Analyze user query to determine which row prompt to use
        logger.info("=== STEP 1: ANALYZING USER QUERY FOR PROMPT SELECTION ===")
        try:
            from preprocess.preprocess_routes import analyze_input
            analysis_response = await analyze_input({"message": user_message})
            
            # Extract analysis data from JSONResponse
            if hasattr(analysis_response, 'body'):
                import json
                analysis_json = json.loads(analysis_response.body.decode())
            else:
                analysis_json = analysis_response
            
            # Store preprocessing response for debug panel
            from utils.route_helpers import last_preprocessing_response
            import utils.route_helpers as debug_vars
            debug_vars.last_preprocessing_response = json.dumps({
                "row_number": analysis_json.get("row_number", 1),
                "analysis_data": analysis_json.get("analysis_data", {}),
                "search_query": analysis_json.get("search_query", ""),
                "memory_query": analysis_json.get("memory_query", ""),
                "raw_openai_response": analysis_json.get("analysis_data", {}).get("raw_response", ""),
                "timestamp": time.time()
            }, indent=2)
            
            row_number = analysis_json.get("row_number", 1)
            analysis_memories = analysis_json.get("memory_results", [])
            analysis_serper = analysis_json.get("serper_results", "")
            
            logger.info(f"Analysis complete - Selected row: {row_number}")
            logger.info(f"Memory results: {len(analysis_memories)} items")
            logger.info(f"SERPER results: {len(analysis_serper)} chars")
            
        except Exception as analysis_error:
            logger.error(f"Error in query analysis: {analysis_error}")
            logger.error(f"Falling back to row 1 and standard flow")
            row_number = 1
            analysis_memories = []
            analysis_serper = ""
            
            # Store error info for debug panel
            import utils.route_helpers as debug_vars
            debug_vars.last_preprocessing_response = json.dumps({
                "error": str(analysis_error),
                "fallback_row": 1,
                "timestamp": time.time()
            }, indent=2)
        
        # Step 2: Use centralized prompt builder with dynamic template loading
        logger.info(f"=== STEP 2: USING CENTRALIZED PROMPT BUILDER WITH ROW {row_number} ===")
        from prompt_builder import craft as row_craft
        logger.info(f"Using centralized prompt builder with row {row_number} template")
        
        # Embedded Gavin Wood persona
        persona = {
            "name": "Gavin Wood",
            "summary": """You are Gavin Wood, founder of Polkadot and co-founder of Ethereum. You're highly technical, precise, and focused on blockchain architecture. You created the Solidity programming language and wrote the Ethereum Yellow Paper. You're known for your academic approach to blockchain design and Web3 infrastructure. You focus on technical accuracy, cross-chain interoperability, and advancing blockchain technology."""
        }
        logger.info(f"Using embedded persona: {persona.get('name', 'unknown')}")
        
        user_id = f"gavinwood"  # Unique user ID for Mem0
        query_text = preprocess_tweet(user_message, is_query=True)
        logger.info(f"Original message: '{user_message}'")
        logger.info(f"Processed query for Mem0: '{query_text}'")
        
        # Use analysis memories if available, otherwise get fresh memories
        if analysis_memories:
            logger.info("Using memories from analysis")
            memories_with_scores = []
            for mem in analysis_memories:
                if isinstance(mem, dict) and "memory" in mem:
                    memories_with_scores.append((mem["memory"], mem.get("score", 0.0)))
                elif isinstance(mem, str):
                    memories_with_scores.append((mem, 0.5))
        else:
            logger.info("Getting fresh memories")
            memories = await get_memories_with_timeout(user_id, query_text, limit=4, timeout=5.0)
            memories_with_scores = [(mem["memory"], mem.get("score", 0.0)) for mem in memories]
        
        # If scores are too low or no memories found, don't use memories
        if not memories_with_scores or max(score for _, score in memories_with_scores) < 0.3:
            memories_with_scores = []  # Clear memories if they're not relevant enough
        
        # Extract insights from the user query using spaCy
        logger.info("🔍 Extracting query insights with spaCy...")
        query_insights = enhance_query_context(user_message)
        context_enhancement = format_context_enhancement(query_insights)
        
        # Build persona context with query insights
        persona_context_parts = []
        if context_enhancement:
            logger.info(f"📝 Adding query insights to context:\n{context_enhancement}")
            persona_context_parts.append(f"QUERY ANALYSIS:\n{context_enhancement}")
        
        persona_context = "\n\n".join(persona_context_parts) if persona_context_parts else ""
        logger.info(f"Built persona context with {len(persona_context_parts)} sections")
        
        # Format conversation history
        history = message.get("history", [])
        formatted_history = []
        if history:
            if all(isinstance(msg, dict) and "role" in msg and "content" in msg for msg in history):
                formatted_history = [f"{msg['role'].capitalize()}: {msg['content']}" for msg in history]
            elif all(isinstance(msg, str) for msg in history):
                formatted_history = []
                for i, msg in enumerate(history):
                    role = "User" if i % 2 == 0 else "Assistant"
                    formatted_history.append(f"{role}: {msg}")
            else:
                logger.warning(f"Unexpected history format: {history}")
        
        if "message" in message and message["message"]:
            formatted_history.append(f"User: {message['message']}")
        
        logger.info(f"Formatted history: {formatted_history}")
        
        # Create search functions that use analysis results if available
        async def should_search_web_enhanced(query: str) -> bool:
            if analysis_serper:
                return True
            return await should_search_web(query)
        
        async def search_serper_enhanced(query: str, num_results: int = 3) -> str:
            if analysis_serper:
                return analysis_serper
            return await search_serper(query, num_results)
        
        # Build the prompt using the selected row's prompt builder
        logger.info(f"=== STEP 3: BUILDING PROMPT WITH ROW {row_number} ===")
        prompt = await row_craft(
            persona, 
            memories_with_scores, 
            formatted_history, 
            extra_persona_context=persona_context, 
            should_search_web_func=should_search_web_enhanced, 
            search_serper_func=search_serper_enhanced,
            row_number=row_number
        )
        logger.info(f"Built prompt using row {row_number}: {prompt[:100]}...")
        
        # Update debug information for debug panel
        from utils.route_helpers import last_prompt, last_first_draft, last_revised_response
        import utils.route_helpers as debug_vars
        
        # Store the analysis data as first draft 
        debug_vars.last_first_draft = json.dumps({
            "analysis_step": "preprocess_analysis",
            "row_selected": row_number,
            "analysis_data": analysis_json if 'analysis_json' in locals() else {},
            "memories_count": len(analysis_memories),
            "serper_length": len(analysis_serper)
        }, indent=2)
        
        # Store the final prompt
        debug_vars.last_prompt = prompt
        
        # Stream the response
        async def response_stream():
            logger.info(f"=== STEP 4: GENERATING RESPONSE WITH ROW {row_number} ===")
            
            # Generate response with GPT-4o
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=1.2,  # Increased for more personality
                top_p=0.5,  # Reduced for more focused responses
                presence_penalty=0.6,
                frequency_penalty=0.3,
                stream=True
            )
            
            logger.info(f"Generating response using row {row_number} prompt...")
            full_response = ""
            
            # Stream the response
            async for chunk in response:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                
                # Stream each chunk
                yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
                
                # When streaming is complete
                if chunk.choices[0].finish_reason == "stop":
                    logger.info(f"Response generation complete using row {row_number}: {len(full_response)} characters")
                    
                    # Update debug information with final response
                    debug_vars.last_revised_response = json.dumps({
                        "final_response": full_response,
                        "response_length": len(full_response),
                        "row_used": row_number,
                        "timestamp": time.time()
                    }, indent=2)
                    
                    # Add final stop token
                    yield f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    
                    # Store memories in background
                    background_tasks.add_task(store_memories_async, user_id, user_message, full_response)

        return StreamingResponse(
            response_stream(),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


    
    
@router.get("/dashboard")
async def serve_dashboard():
    """Serve the analyze dashboard."""
    dashboard_path = os.path.join(static_path, "dashboard.html")
    if os.path.isfile(dashboard_path):
        return FileResponse(dashboard_path)
    else:
        return HTMLResponse(
            content="<h1>Dashboard Not Found</h1><p>dashboard.html not found in static directory.</p>",
            status_code=404
        )

@router.get("/dashboard/")
async def serve_dashboard_slash():
    """Serve the analyze dashboard with trailing slash."""
    return await serve_dashboard()
    
    
@router.get("/multi-turn")
async def serve_multi_turn():
    """Serve the multi-turn test interface."""
    multi_turn_path = os.path.join(static_path, "multi-turn.html")
    if os.path.isfile(multi_turn_path):
        return FileResponse(multi_turn_path)
    else:
        return HTMLResponse(
            content="<h1>Multi-Turn Test Interface Not Found</h1><p>multi-turn.html not found in static directory.</p>",
            status_code=404
        )

@router.get("/content-analysis")
async def serve_content_analysis():
    """Serve the content analysis page."""
    content_analysis_path = os.path.join(static_path, "content-analysis.html")
    if os.path.isfile(content_analysis_path):
        return FileResponse(content_analysis_path)
    else:
        return HTMLResponse(
            content="<h1>Content Analysis Page Not Found</h1><p>content-analysis.html not found in static directory.</p>",
            status_code=404
        )

@router.get("/content-analysis/")
async def serve_content_analysis_slash():
    """Serve the content analysis page with trailing slash."""
    return await serve_content_analysis()


@router.post("/debug/analyze-prompt")
async def debug_analyze_prompt(request_data: dict):
    """Debug endpoint to show both preprocess analysis and final prompt."""
    try:
        user_message = request_data.get("message", "")
        if not user_message:
            raise HTTPException(status_code=400, detail="No message provided")
        
        logger.info(f"=== DEBUG: ANALYZING PROMPT FOR MESSAGE: {user_message} ===")
        
        # Step 1: Get preprocess analysis
        try:
            from preprocess.preprocess_routes import analyze_input
            analysis_response = await analyze_input({"message": user_message})
            
            # Extract analysis data from JSONResponse
            if hasattr(analysis_response, 'body'):
                import json
                analysis_json = json.loads(analysis_response.body.decode())
            else:
                analysis_json = analysis_response
            
            preprocess_analysis = analysis_json
            row_number = analysis_json.get("row_number", 1)
            analysis_memories = analysis_json.get("memory_results", [])
            analysis_serper = analysis_json.get("serper_results", "")
            
        except Exception as analysis_error:
            logger.error(f"Error in preprocess analysis: {analysis_error}")
            preprocess_analysis = {"error": str(analysis_error)}
            row_number = 1
            analysis_memories = []
            analysis_serper = ""
        
        # Step 2: Use centralized prompt builder with dynamic template loading
        from prompt_builder import craft as row_craft
        row_prompt_info = f"prompt_builder.py with row{row_number} template"
        
        # Step 3: Build the normal prompt components
        persona = {
            "name": "Gavin Wood",
            "summary": """You are Gavin Wood, founder of Polkadot and co-founder of Ethereum. You're highly technical, precise, and focused on blockchain architecture. You created the Solidity programming language and wrote the Ethereum Yellow Paper. You're known for your academic approach to blockchain design and Web3 infrastructure. You focus on technical accuracy, cross-chain interoperability, and advancing blockchain technology."""
        }
        
        user_id = "gavinwood"
        query_text = preprocess_tweet(user_message, is_query=True)
        
        # Use analysis memories if available, otherwise get fresh memories
        if analysis_memories:
            memories_with_scores = []
            for mem in analysis_memories:
                if isinstance(mem, dict) and "memory" in mem:
                    memories_with_scores.append((mem["memory"], mem.get("score", 0.0)))
                elif isinstance(mem, str):
                    memories_with_scores.append((mem, 0.5))
        else:
            memories = await get_memories_with_timeout(user_id, query_text, limit=4, timeout=5.0)
            memories_with_scores = [(mem["memory"], mem.get("score", 0.0)) for mem in memories]
        
        # If scores are too low, clear memories
        if not memories_with_scores or max(score for _, score in memories_with_scores) < 0.3:
            memories_with_scores = []
        
        # Extract query insights
        query_insights = enhance_query_context(user_message)
        context_enhancement = format_context_enhancement(query_insights)
        
        persona_context_parts = []
        if context_enhancement:
            persona_context_parts.append(f"QUERY ANALYSIS:\n{context_enhancement}")
        
        persona_context = "\n\n".join(persona_context_parts) if persona_context_parts else ""
        
        # Format minimal history for debug
        formatted_history = [f"User: {user_message}"]
        
        # Create search functions that use analysis results if available
        async def should_search_web_enhanced(query: str) -> bool:
            if analysis_serper:
                return True
            return await should_search_web(query)
        
        async def search_serper_enhanced(query: str, num_results: int = 3) -> str:
            if analysis_serper:
                return analysis_serper
            return await search_serper(query, num_results)
        
        # Step 4: Build the final prompt
        try:
            final_prompt = await row_craft(
                persona, 
                memories_with_scores, 
                formatted_history, 
                extra_persona_context=persona_context, 
                should_search_web_func=should_search_web_enhanced, 
                search_serper_func=search_serper_enhanced,
                row_number=row_number
            )
        except Exception as prompt_error:
            final_prompt = f"Error building prompt: {str(prompt_error)}"
        
        # Step 5: Return comprehensive debug info
        return JSONResponse({
            "status": "success",
            "user_message": user_message,
            "debug_info": {
                "preprocess_analysis": preprocess_analysis,
                "selected_row": row_number,
                "row_prompt_file": row_prompt_info,
                "memories_count": len(memories_with_scores),
                "memories_used": [{"memory": mem[0][:100] + "...", "score": mem[1]} for mem in memories_with_scores[:3]],
                "serper_results_length": len(analysis_serper),
                "query_insights": context_enhancement,
                "final_prompt_length": len(final_prompt),
                "final_prompt_preview": final_prompt[:500] + "..." if len(final_prompt) > 500 else final_prompt
            },
            "complete_flows": {
                "preprocess_analysis": preprocess_analysis,
                "final_prompt": final_prompt
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in debug analyze prompt: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/info")
async def debug_info():
    """Debug endpoint to provide information for the debug panel."""
    from utils.route_helpers import last_prompt, last_first_draft, last_revised_response, last_preprocessing_response
    
    # Parse JSON data if available for better display
    analysis_data = {}
    response_data = {}
    preprocessing_data = {}
    
    try:
        if last_first_draft:
            analysis_data = json.loads(last_first_draft)
    except:
        pass
        
    try:
        if last_revised_response:
            response_data = json.loads(last_revised_response)
    except:
        pass
        
    try:
        if last_preprocessing_response:
            preprocessing_data = json.loads(last_preprocessing_response)
    except:
        pass
    
    return JSONResponse({
        "last_prompt": last_prompt,
        "last_first_draft": last_first_draft,
        "last_revised_response": last_revised_response,
        "preprocessing_response": preprocessing_data,
        "analysis_summary": {
            "row_selected": analysis_data.get("row_selected", "N/A"),
            "memories_count": analysis_data.get("memories_count", 0),
            "serper_results": analysis_data.get("serper_length", 0) > 0,
            "has_analysis": bool(analysis_data.get("analysis_data"))
        },
        "response_summary": {
            "response_length": response_data.get("response_length", 0),
            "row_used": response_data.get("row_used", "N/A"),
            "completed": bool(response_data.get("final_response"))
        },
        "preprocessing_summary": {
            "row_selected": preprocessing_data.get("row_number", "N/A"),
            "has_analysis": bool(preprocessing_data.get("analysis_data")),
            "search_query": preprocessing_data.get("search_query", ""),
            "memory_query": preprocessing_data.get("memory_query", ""),
            "has_error": "error" in preprocessing_data
        },
        "timestamp": time.time(),
        "status": "active" if last_prompt else "no_data"
    })

@router.get("/debug/test-serper")
async def test_serper_endpoint():
    """Test SERPER API connection."""
    try:
        result = await test_serper_connection()
        return JSONResponse({
            "serper_test": "success" if result else "failed",
            "serper_api_key_set": os.getenv("SERPER_API_KEY") is not None,
            "message": "Check logs for detailed information"
        })
    except Exception as e:
        return JSONResponse({
            "serper_test": "error",
            "error": str(e),
            "serper_api_key_set": os.getenv("SERPER_API_KEY") is not None
        })

@router.get("/debug/network")
async def test_network_connectivity():
    """Test network connectivity from within the container."""
    results = {}
    
    try:
        # Test 1: Basic HTTP connectivity
        timeout = httpx.Timeout(10.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                start_time = time.time()
                response = await client.get("https://httpbin.org/ip")
                results["httpbin_test"] = {
                    "status": "success",
                    "status_code": response.status_code,
                    "response_time": f"{time.time() - start_time:.2f}s",
                    "ip": response.json().get("origin", "unknown")
                }
            except Exception as e:
                results["httpbin_test"] = {"status": "failed", "error": str(e)}
            
            # Test 2: Google connectivity
            try:
                start_time = time.time()
                response = await client.get("https://google.com")
                results["google_test"] = {
                    "status": "success",
                    "status_code": response.status_code,
                    "response_time": f"{time.time() - start_time:.2f}s"
                }
            except Exception as e:
                results["google_test"] = {"status": "failed", "error": str(e)}
            
            # Test 3: SERPER API connectivity (without API key)
            try:
                start_time = time.time()
                response = await client.get("https://google.serper.dev")
                results["serper_domain_test"] = {
                    "status": "success",
                    "status_code": response.status_code,
                    "response_time": f"{time.time() - start_time:.2f}s"
                }
            except Exception as e:
                results["serper_domain_test"] = {"status": "failed", "error": str(e)}
                
            # Test 4: DNS resolution
            try:
                import socket
                start_time = time.time()
                ip = socket.gethostbyname("google.serper.dev")
                results["dns_test"] = {
                    "status": "success",
                    "serper_ip": ip,
                    "response_time": f"{time.time() - start_time:.2f}s"
                }
            except Exception as e:
                results["dns_test"] = {"status": "failed", "error": str(e)}
    
    except Exception as e:
        results["overall_error"] = str(e)
    
    return JSONResponse({
        "network_diagnostics": results,
        "container_env": {
            "serper_key_set": os.getenv("SERPER_API_KEY") is not None,
            "openai_key_set": os.getenv("OPENAI_API_KEY") is not None
        },
        "recommendations": [
            "If all tests fail: Check Docker network configuration",
            "If only SERPER fails: Check firewall rules for google.serper.dev",
            "If DNS fails: Check container DNS settings",
            "If timeouts: Consider increasing timeout values or checking network speed"
        ]
    })

app.include_router(router)
app.include_router(memory_router)
app.include_router(analyze_router)
app.include_router(deep_debug_router)