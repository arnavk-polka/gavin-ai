"""Helper functions for routes that were moved from routes.py to keep it focused on route declarations."""

import json
import os
import asyncio
import httpx
import time
from openai import AsyncOpenAI
from config import logger, openai_client, mem0_client
from utils.utils import get_relevant_memories, add_memory

# Global variables to store debug information
last_prompt = ""
last_first_draft = ""
last_revised_response = ""
last_preprocessing_response = ""
last_row_number = None
last_template_number = None
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

 