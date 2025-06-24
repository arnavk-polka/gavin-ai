import json
import re
from emoji import demojize
from typing import Dict, List, Tuple, Optional
import asyncio

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
                semantic_memory,  # Use new API format
                user_id=user_id,
                metadata=metadata or {}
            )
        return True
    except Exception as e:
        print(f"Error adding memory to Mem0: {e}")
        return False

def add_graph_memory(mem0_client, user_id: str, message: str, entities: List[str] = None, relationships: List[Dict] = None, metadata: Dict = None):
    """Add memory with graph structure using Mem0's built-in graph functionality."""
    try:
        # Only store Assistant messages as memories (consistent with add_memory)
        if message.startswith("Assistant: "):
            content = message[11:]  # Remove "Assistant: " prefix
            print(f"[GRAPH_MEMORY] Processing content: {content}")
            
            # Use Mem0's built-in graph memory - it automatically extracts entities and relationships
            print(f"[GRAPH_MEMORY] Calling mem0_client.add() for GRAPH memory...")
            print(f"[GRAPH_MEMORY] User ID: {user_id}")
            print(f"[GRAPH_MEMORY] Content: {content}")
            print(f"[GRAPH_MEMORY] Metadata: {metadata}")
            
            # Check mem0 client configuration
            if hasattr(mem0_client, 'config'):
                print(f"[GRAPH_MEMORY] Mem0 config exists")
                if hasattr(mem0_client.config, 'graph_store'):
                    print(f"[GRAPH_MEMORY] Graph store config: {mem0_client.config.graph_store}")
                else:
                    print(f"[GRAPH_MEMORY] No graph_store in config")
            else:
                print(f"[GRAPH_MEMORY] No config attribute on mem0_client")
            
            # Call mem0's add method - it will handle graph storage automatically
            result = mem0_client.add(
                content,  # Just pass the content directly
                user_id=user_id,
                metadata=metadata or {}
            )
            print(f"[GRAPH_MEMORY] ✓ mem0_client.add() completed successfully")
            print(f"[GRAPH_MEMORY] Result: {result}")
                
        return True
    except Exception as e:
        print(f"[GRAPH_MEMORY] ❌ Error adding graph memory to Mem0: {e}")
        import traceback
        print(f"[GRAPH_MEMORY] Full traceback: {traceback.format_exc()}")
        return False

def extract_entities(text: str) -> List[str]:
    """Extract entities from text using simple NLP patterns."""
    entities = []
    
    # Common blockchain/web3 entities
    blockchain_terms = ["bitcoin", "ethereum", "polkadot", "solidity", "smart contract", "defi", "nft", "dao", "web3", "blockchain"]
    person_patterns = [r"(?:Dr\.?|Mr\.?|Ms\.?|Mrs\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", r"[A-Z][a-z]+\s+[A-Z][a-z]+"]
    org_patterns = [r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Inc|LLC|Corp|Foundation|Labs|Protocol)"]
    
    text_lower = text.lower()
    
    # Extract blockchain terms
    for term in blockchain_terms:
        if term in text_lower:
            entities.append(term.title())
    
    # Extract people names
    for pattern in person_patterns:
        matches = re.findall(pattern, text)
        entities.extend(matches)
    
    # Extract organizations
    for pattern in org_patterns:
        matches = re.findall(pattern, text)
        entities.extend(matches)
    
    return list(set(entities))  # Remove duplicates

def extract_relationships(text: str, entities: List[str]) -> List[Dict]:
    """Extract relationships between entities."""
    relationships = []
    
    # Simple relationship patterns
    relation_patterns = {
        "created": ["created", "built", "developed", "founded"],
        "works_with": ["works with", "collaborates with", "partners with"],
        "part_of": ["part of", "member of", "belongs to"],
        "related_to": ["related to", "connected to", "associated with"]
    }
    
    text_lower = text.lower()
    
    for i, entity1 in enumerate(entities):
        for j, entity2 in enumerate(entities):
            if i != j:  # Don't relate entity to itself
                for relation_type, keywords in relation_patterns.items():
                    for keyword in keywords:
                        # Simple pattern matching
                        if f"{entity1.lower()}" in text_lower and f"{entity2.lower()}" in text_lower and keyword in text_lower:
                            relationships.append({
                                "source": entity1,
                                "target": entity2,
                                "relationship": relation_type,
                                "confidence": 0.7
                            })
                            break
    
    return relationships

def get_relevant_memories(mem0_client, user_id: str, query: str, limit: int = 4) -> List[Dict]:
    """Retrieve relevant memories from Mem0 based on a query - optimized for speed."""
    try:
        # Enhance query to focus on finding relevant knowledge
        enhanced_query = f"Knowledge about: {query}"
        
        # Single search strategy for faster performance
        memories = mem0_client.search(
            enhanced_query,  # Use new API format
            user_id=user_id,
            limit=limit
        )
        return memories or []
    except Exception as e:
        print(f"Error retrieving memories from Mem0: {e}")
        return []

def get_graph_memories(mem0_client, user_id: str, entity: str, relationship_type: str = None, limit: int = 10) -> List[Dict]:
    """Retrieve graph-structured memories related to a specific entity."""
    try:
        # Search for memories containing the entity
        query = f"entity:{entity}"
        if relationship_type:
            query += f" relationship:{relationship_type}"
            
        memories = mem0_client.search(
            query,  # Use new API format
            user_id=user_id,
            limit=limit
        )
        
        # With proper graph memory, all memories should be graph-enabled
        return memories or []
    except Exception as e:
        print(f"Error retrieving graph memories: {e}")
        return []

def build_knowledge_graph(mem0_client, user_id: str) -> Dict:
    """Build a knowledge graph from all user memories using Mem0's graph functionality."""
    try: 
        print(f"[BUILD_GRAPH] Building knowledge graph for user: {user_id}")
        
        # Get all memories for the user using new API
        all_memories = mem0_client.get_all(user_id=user_id, limit=1000)
        print(f"[BUILD_GRAPH] Retrieved {len(all_memories)} memories")
        
        # With Mem0's graph memory, the graph structure is handled automatically
        # We just need to return the memories in a graph format
        nodes = []
        edges = []
        
        for memory in all_memories:
            print(f"[BUILD_GRAPH] Processing memory: {memory}")
            # Extract entities and relationships from memory content/metadata
            # This would typically be handled by Mem0's graph functionality
            
        print(f"[BUILD_GRAPH] Graph contains {len(nodes)} nodes and {len(edges)} edges")
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "memories": all_memories  # Include raw memories for debugging
        }
    except Exception as e:
        print(f"[BUILD_GRAPH] Error building knowledge graph: {e}")
        import traceback
        print(f"[BUILD_GRAPH] Full traceback: {traceback.format_exc()}")
        return {"nodes": [], "edges": [], "total_nodes": 0, "total_edges": 0, "error": str(e)}

def extract_key_terms(text: str) -> List[str]:
    """Extract key terms from text for better semantic search."""
    # Remove common stop words and extract meaningful terms
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "how", "are", "you", "i", "me", "my"}
    words = re.findall(r'\b\w+\b', text.lower())
    key_terms = [word for word in words if word not in stop_words and len(word) > 2]
    return key_terms[:5]  # Return top 5 key terms