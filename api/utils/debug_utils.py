import json
import os
import asyncio
import httpx
from config import logger, mem0_client
from utils.utils import get_relevant_memories

async def get_memories_with_timeout(user_id: str, query_text: str, limit: int = 4, timeout: float = 3.0):
    """Get memories with timeout to prevent blocking."""
    try:
        # Run memory search with timeout
        memories = await asyncio.wait_for(
            asyncio.to_thread(get_relevant_memories, mem0_client, user_id, query_text, limit),
            timeout=timeout
        )
        return memories
    except asyncio.TimeoutError:
        logger.warning(f"Memory search timed out after {timeout}s for query: {query_text[:50]}")
        return []
    except Exception as e:
        logger.error(f"Error in memory search: {e}")
        return [] 