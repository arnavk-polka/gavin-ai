import json
import re
from emoji import demojize
from typing import Dict, List

def preprocess_tweet(text: str, is_query: bool = False) -> str:
    """Preprocess text for memory storage/retrieval."""
    if is_query:
        # For queries, preserve more semantic meaning
        text = demojize(text)
        text = re.sub(r'http\S+|www\S+', '', text, flags=re.MULTILINE)
        # Don't lowercase for better semantic matching
        text = ' '.join(text.split())
        return text.strip()
    else:
        text = re.sub(r'http\S+|www\S+', '', text, flags=re.MULTILINE)
        text = re.sub(r'[@#]\w+|\bRT\b', '', text)
        text = demojize(text)
        text = re.sub(r'[^\w\s]', '', text)
        text = ' '.join(text.lower().split())
        return text.strip()

def add_memory(mem0_client, user_id: str, message: str, metadata: Dict = None):
    try:
        # Only store Assistant messages as memories
        if message.startswith("Assistant: "):
            content = message[11:]  # Remove "Assistant: " prefix
            # Store the answer with its key topics
            semantic_memory = f"Knowledge about blockchain, Ethereum, and Web3: {content}"
            
            mem0_client.add(
                messages=[{"role": "user", "content": semantic_memory}],
                user_id=user_id,
                metadata=metadata or {}
            )
        return True
    except Exception as e:
        print(f"Error adding memory to Mem0: {e}")
        return False

def get_relevant_memories(mem0_client, user_id: str, query: str, limit: int = 4) -> List[Dict]:
    """Retrieve relevant memories from Mem0 based on a query - optimized for speed."""
    try:
        # Enhance query to focus on finding relevant knowledge
        enhanced_query = f"Knowledge about: {query}"
        
        # Single search strategy for faster performance
        memories = mem0_client.search(
            query=enhanced_query,
            user_id=user_id,
            limit=limit
        )
        return memories or []
    except Exception as e:
        print(f"Error retrieving memories from Mem0: {e}")
        return []

def extract_key_terms(text: str) -> List[str]:
    """Extract key terms from text for better semantic search."""
    # Remove common stop words and extract meaningful terms
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "how", "are", "you", "i", "me", "my"}
    words = re.findall(r'\b\w+\b', text.lower())
    key_terms = [word for word in words if word not in stop_words and len(word) > 2]
    return key_terms[:5]  # Return top 5 key terms