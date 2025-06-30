import json
import os
import asyncio
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from config import app, logger, openai_client, static_path, mem0_client
from utils import preprocess_tweet, add_memory, get_relevant_memories
from prompt_builder import craft
from memory_routes import memory_router
from analyze_routes import analyze_router
from response_generation import tone_bleurt_gate, enhance_query_context, format_context_enhancement
import time

router = APIRouter()

# Global variable to store the last prompt for debugging
last_prompt = ""
# Simple in-memory cache for recent memory searches (optional optimization)
memory_cache = {}

async def stream_openai_response(prompt):
    logger.info("Starting to stream OpenAI response")
    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.5,
        top_p=0.9,
        stream=True
    )
    async for chunk in response:
        content = chunk.choices[0].delta.content or ""
        logger.info(f"Streaming chunk: {content[:50]}...")
        yield content

async def get_memories_with_timeout(user_id: str, query_text: str, limit: int = 4, timeout: float = 3.0):
    """Get memories with timeout to prevent blocking."""
    try:
        # Check cache first (optional optimization)
        cache_key = f"{user_id}:{query_text}"
        if cache_key in memory_cache:
            return memory_cache[cache_key]
        
        # Run memory search with timeout
        memories = await asyncio.wait_for(
            asyncio.to_thread(get_relevant_memories, mem0_client, user_id, query_text, limit),
            timeout=timeout
        )
        
        # Cache the result
        memory_cache[cache_key] = memories
        # Keep cache small - remove old entries if it gets too big
        if len(memory_cache) > 100:
            memory_cache.clear()
            
        return memories
    except asyncio.TimeoutError:
        logger.warning(f"Memory search timed out after {timeout}s for query: {query_text[:50]}")
        return []
    except Exception as e:
        logger.error(f"Error in memory search: {e}")
        return []

async def should_search_web(user_query: str) -> bool:
    """
    Check with OpenAI if the user query would benefit from web search.
    Returns True if web search would be helpful, False otherwise.
    """
    logger.info(f"=== SHOULD_SEARCH_WEB CALLED ===")
    logger.info(f"Query: '{user_query}'")
    try:
        openai_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_TOKEN")
        if not openai_api_key:
            logger.error("OpenAI API key not found")
            return False
            
        client = AsyncOpenAI(api_key=openai_api_key)
        
        search_check_prompt = f"""Does this query benefit from current market/trend data? "{user_query}"

Answer: yes or no"""

        logger.info(f"Sending search check prompt to OpenAI: '{search_check_prompt}'")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": search_check_prompt}],
            max_tokens=10,
            temperature=0
        )
        
        result = response.choices[0].message.content.strip().lower()
        logger.info(f"OpenAI response: '{result}'")
        logger.info(f"Search check result for query '{user_query}': {result}")
        # Handle variations like "yes.", "yes,", "YES", etc.
        decision = result.startswith("yes")
        logger.info(f"Final decision: {decision}")
        return decision
        
    except Exception as e:
        logger.error(f"Error checking if search needed: {e}")
        return False

async def test_serper_connection() -> bool:
    """Test SERPER API connection with exact example from their website"""
    try:
        serper_api_key = os.getenv("SERPER_API_KEY")
        if not serper_api_key:
            logger.error("SERPER_API_KEY not found for test")
            return False
            
        url = "https://google.serper.dev/search"
        
        # Exact pattern from SERPER website
        data = json.dumps({"q": "apple inc"})
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        
        logger.info("Testing SERPER connection with official example...")
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Use data parameter instead of json parameter to match their example
            response = await client.post(url, headers=headers, data=data)
            
        logger.info(f"SERPER test response status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            logger.info(f"SERPER test successful. Response keys: {list(result.keys())}")
            return True
        else:
            logger.error(f"SERPER test failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"SERPER test connection failed: {e}")
        logger.exception("Full test traceback:")
        return False



async def search_serper(query: str, num_results: int = 3) -> str:
    """
    Search Google using SERPER API and return formatted results.
    """
    logger.info(f"=== SEARCH_SERPER CALLED ===")
    logger.info(f"Query: '{query}', num_results: {num_results}")
    try:
        serper_api_key = os.getenv("SERPER_API_KEY")
        logger.info(f"SERPER_API_KEY found: {serper_api_key is not None}")
        if not serper_api_key:
            logger.error("SERPER_API_KEY not found in environment")
            return ""
            
        url = "https://google.serper.dev/search"
        
        # Use exact pattern from SERPER example - keep it simple like the test
        payload = {
            "q": query,
            "num": num_results
        }
        data = json.dumps(payload)
        
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Making request to SERPER API with payload: {payload}")
        # Configure timeout and retry settings for better reliability
        timeout = httpx.Timeout(2.0, connect=1.0)  # Very fast timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # Use data parameter instead of json parameter to match SERPER example
                response = await client.post(url, headers=headers, data=data)
            except httpx.ConnectTimeout:
                logger.warning("SERPER API connection timeout - continuing without search results")
                return ""
            except httpx.TimeoutException:
                logger.warning("SERPER API request timeout - continuing without search results")
                return ""
            except Exception as e:
                logger.warning(f"SERPER API error: {e} - continuing without search results")
                return ""
        
        logger.info(f"SERPER API response status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"SERPER API error: {response.status_code} - {response.text}")
            return ""
            
        data = response.json()
        logger.info(f"SERPER response data keys: {list(data.keys())}")
        
        # Format the search results for better prompt integration
        search_results = []
        
        # Add regular search results (3 results max)
        if 'organic' in data:
            logger.info(f"Found {len(data['organic'])} organic results")
            for i, result in enumerate(data['organic'][:num_results], 1):
                title = result.get('title', 'No title')
                snippet = result.get('snippet', 'No description')
                
                # Try to get more complete content from multiple sources
                content_sources = []
                
                # 1. Check for longer description in rich snippets
                rich_snippet = result.get('richSnippet', {})
                if rich_snippet:
                    if 'description' in rich_snippet:
                        content_sources.append(rich_snippet['description'])
                    if 'top' in rich_snippet and 'description' in rich_snippet['top']:
                        content_sources.append(rich_snippet['top']['description'])
                
                # 2. Check for sitelinks with descriptions
                sitelinks = result.get('sitelinks', [])
                for sitelink in sitelinks[:2]:  # Use first 2 sitelinks if available
                    if 'snippet' in sitelink:
                        content_sources.append(sitelink['snippet'])
                
                # 3. Check for FAQ or other structured data
                if 'answerBox' in result:
                    answer_box = result['answerBox']
                    if 'answer' in answer_box:
                        content_sources.append(answer_box['answer'])
                    if 'snippet' in answer_box:
                        content_sources.append(answer_box['snippet'])
                
                # Use the longest, most complete content available
                if content_sources:
                    # Sort by length and pick the longest one
                    best_content = max(content_sources, key=len)
                    if len(best_content) > len(snippet):
                        snippet = best_content
                
                # Clean and format the content for better prompt integration
                if title.lower() in snippet.lower():
                    content = snippet
                else:
                    content = f"{title}: {snippet}"
                
                # Clean up the content and handle truncation
                content = content.replace("...", "").strip()
                
                # Add ellipsis if content appears to be cut off
                if content and not content.endswith(('.', '!', '?', ':', ';')):
                    words = content.split()
                    if len(words) > 5:
                        content += "..."
                
                search_results.append(f"• {content}")
        else:
            logger.warning("No 'organic' key found in SERPER response")
        
        if search_results:
            formatted_results = "RECENT MARKET INSIGHTS:\n" + "\n\n".join(search_results)
            logger.info(f"Retrieved {len(search_results)} search results for query: {query}")
            logger.info(f"Formatted results preview: {formatted_results[:200]}...")
            return formatted_results
        else:
            logger.warning("No organic results found in SERPER response")
            return ""
            
    except Exception as e:
        logger.error(f"Error searching with SERPER: {e}")
        logger.exception("Full traceback:")
        return ""

async def store_memories_async(user_id: str, user_message: str, ai_response: str):
    """Store memories asynchronously without blocking the main response"""
    try:
        logger.info(f"Storing AI response as memory for user {user_id} - Response: {ai_response[:50]}...")
        
        # Only store the AI response as memory
        ai_result = await asyncio.to_thread(
            add_memory, 
            mem0_client, 
            user_id, 
            f"Assistant: {ai_response}", 
            {"role": "assistant"}
        )
        
        logger.info(f"AI response memory storage result: {ai_result}")
        
    except Exception as e:
        logger.error(f"Error storing memories: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

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
    global last_prompt
    logger.info(f"Chat request for handle: {handle}, message: {message.get('message', '')[:50]}...")
    try:
        client_host = request.client.host
        user_agent = request.headers.get("user-agent", "")
        logger.info(f"Request from client: {client_host}, User-Agent: {user_agent}")
        
        # Embedded Gavin Wood persona instead of loading from file
        persona = {
            "name": "Gavin Wood",
            "summary": """You are Gavin Wood, founder of Polkadot and co-founder of Ethereum. You're highly technical, precise, and focused on blockchain architecture. You created the Solidity programming language and wrote the Ethereum Yellow Paper. You're known for your academic approach to blockchain design and Web3 infrastructure. You focus on technical accuracy, cross-chain interoperability, and advancing blockchain technology."""
        }
        logger.info(f"Using embedded persona: {persona.get('name', 'unknown')}")
        
        user_id = f"gavinwood"  # Unique user ID for Mem0
        query_text = preprocess_tweet(message["message"], is_query=True)
        logger.info(f"Original message: '{message['message']}'")
        logger.info(f"Processed query for Mem0: '{query_text}'")
        
        # Extract insights from the user query using spaCy
        logger.info("🔍 Extracting query insights with spaCy...")
        query_insights = enhance_query_context(message["message"])
        context_enhancement = format_context_enhancement(query_insights)
        
        # Retrieve relevant memories with timeout to prevent blocking
        memories = await get_memories_with_timeout(user_id, query_text, limit=4, timeout=5.0)
        memories_with_scores = [(mem["memory"], mem.get("score", 0.0)) for mem in memories]
        
        # If scores are too low or no memories found, don't use memories
        if not memories_with_scores or max(score for _, score in memories_with_scores) < 0.3:
            memories_with_scores = []  # Clear memories if they're not relevant enough
        
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
        
        # Build the prompt
        prompt = await craft(persona, memories_with_scores, formatted_history, extra_persona_context=persona_context, should_search_web_func=should_search_web, search_serper_func=search_serper)
        logger.info(f"Built prompt: {prompt[:100]}...")
        
        # Store the prompt for debugging
        last_prompt = prompt
        
        # Stream the response
        async def response_stream():
            # Extract just the user's question from the formatted history
            user_question = message['message']
            
            # Create system prompt without the user question
            system_prompt = prompt.split('CURRENT USER QUERY: "')[0]

            # Log what's being sent to OpenAI
            # logger.info(f"=== OpenAI Request ===")
            # logger.info(f"Full prompt length: {len(prompt)} characters")
            # logger.info(f"System prompt length: {len(system_prompt)} characters")
            # logger.info(f"User question: {user_question}")
            # logger.info(f"System prompt content:\n{system_prompt}")
            # logger.info(f"=== End OpenAI Request ===")
            
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_question}
                ],
                temperature=1.2,  # Increased for more personality
                top_p=0.5,  # Reduced for more focused responses
                presence_penalty=0.6,
                frequency_penalty=0.3,
                stream=True
            )
            full_response = ""
            chunks_buffer = []
            
            # Collect full response first for quality validation
            async for chunk in response:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                chunks_buffer.append(content)
                
                # When streaming is complete, validate and then stream
                if chunk.choices[0].finish_reason == "stop":
                    # Run quality gate (now non-blocking)
                    passed_gate = tone_bleurt_gate(full_response)
                    logger.info(f"Response tone gate: {'PASSED' if passed_gate else 'FAILED'}")
                    
                    # Stream the buffered response
                    for buffered_content in chunks_buffer:
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': buffered_content}}]})}\n\n"
                    
                    # Add final stop token
                    yield f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    
                    # Store memories in background
                    background_tasks.add_task(store_memories_async, user_id, message['message'], full_response)
        
        return StreamingResponse(
            response_stream(),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/info")
async def get_debug_info():
    """Debug endpoint that returns the last prompt and other debug information."""
    global last_prompt
    return JSONResponse({
        "last_prompt": last_prompt,
        "status": "debug_active",
        "timestamp": "current",
        "openai_connected": bool(openai_client),
        "mem0_connected": bool(mem0_client),
        "static_path": static_path,
        "debug_info": {
            "message": "To see prompts, send a chat message first",
            "hint": "Visit / to access the chat interface"
        }
    })
    
    
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