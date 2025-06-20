import json
import os
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from config import app, logger, openai_client, static_path, mem0_client
from utils import preprocess_tweet, add_memory, get_relevant_memories
from prompt_builder import craft
from memory_routes import memory_router

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

async def store_memories_async(user_id: str, user_message: str, ai_response: str):
    """Store memories asynchronously without blocking the main response"""
    try:
        # Only store the AI response as memory
        await asyncio.to_thread(
            add_memory, 
            mem0_client, 
            user_id, 
            f"Assistant: {ai_response}", 
            {"role": "assistant"}
        )
    except Exception as e:
        logger.error(f"Error storing memories: {e}")

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
        
        # Retrieve relevant memories with timeout to prevent blocking
        memories = await get_memories_with_timeout(user_id, query_text, limit=4, timeout=5.0)
        memories_with_scores = [(mem["memory"], mem.get("score", 0.0)) for mem in memories]
        
        # If scores are too low or no memories found, don't use memories
        if not memories_with_scores or max(score for _, score in memories_with_scores) < 0.3:
            memories_with_scores = []  # Clear memories if they're not relevant enough
        
        # Build persona context
        persona_context_parts = []
        if summary := persona.get("summary"):
            persona_context_parts.append(f"Persona Summary:\n{summary}")
        persona_context = "\n\n".join(persona_context_parts)
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
        prompt = craft(persona, memories_with_scores, formatted_history, extra_persona_context=persona_context)
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
            async for chunk in response:
                content = chunk.choices[0].delta.content or ""
                full_response += content
                # Format as SSE with JSON data
                yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
                
                # When streaming is complete, add memories in background (non-blocking)
                if chunk.choices[0].finish_reason == "stop":
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



app.include_router(router)
app.include_router(memory_router)