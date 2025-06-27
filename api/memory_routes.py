import json
import asyncio
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from typing import Optional, List, Dict
from config import logger, mem0_client, get_embedder
from utils import add_memory, get_relevant_memories
# GRAPH IMPORTS COMMENTED OUT
# from utils import add_graph_memory, get_graph_memories, build_knowledge_graph, extract_entities, extract_relationships

memory_router = APIRouter(prefix="/memory", tags=["memory"])

@memory_router.post("/add")
async def add_memory_endpoint(data: dict):
    """Add a memory to mem0.
    
    Request body:
    {
        "user_id": "gavinwood",  // optional, defaults to gavinwood
        "message": "Your memory content here",
        "metadata": {"key": "value"}  // optional
    }
    """
    try:
        user_id = data.get("user_id", "gavinwood")
        message = data.get("message")
        metadata = data.get("metadata", {})
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Use the utility function to add memory
        success = await asyncio.to_thread(add_memory, mem0_client, user_id, f"Assistant: {message}", metadata)
        
        if success:
            return {"status": "success", "message": "Memory added successfully", "user_id": user_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to add memory")
            
    except Exception as e:
        logger.error(f"Error in add_memory endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# GRAPH ENDPOINTS COMMENTED OUT
# @memory_router.post("/add-graph")
# async def add_graph_memory_endpoint(data: dict):
#     """Add a graph-structured memory with entities and relationships.
#     
#     Request body:
#     {
#         "user_id": "gavinwood",  // optional, defaults to gavinwood
#         "message": "Your memory content here",
#         "entities": ["Entity1", "Entity2"],  // optional, will be auto-extracted
#         "relationships": [  // optional, will be auto-extracted
#             {
#                 "source": "Entity1",
#                 "target": "Entity2", 
#                 "relationship": "created",
#                 "confidence": 0.8
#             }
#         ],
#         "metadata": {"key": "value"}  // optional
#     }
#     """
#     try:
#         user_id = data.get("user_id", "gavinwood")
#         message = data.get("message")
#         entities = data.get("entities")
#         relationships = data.get("relationships")
#         metadata = data.get("metadata", {})
#         
#         if not message:
#             raise HTTPException(status_code=400, detail="Message is required")
#         
#         # Use the utility function to add graph memory
#         success = await asyncio.to_thread(
#             add_graph_memory, 
#             mem0_client, 
#             user_id, 
#             f"Assistant: {message}", 
#             entities, 
#             relationships, 
#             metadata
#         )
#         
#         if success:
#             # Extract entities and relationships for response
#             if not entities:
#                 entities = await asyncio.to_thread(extract_entities, message)
#             if not relationships:
#                 relationships = await asyncio.to_thread(extract_relationships, message, entities or [])
#                 
#             return {
#                 "status": "success",
#                 "message": "Graph memory added successfully",
#                 "user_id": user_id,
#                 "entities": entities,
#                 "relationships": relationships
#             }
#         else:
#             raise HTTPException(status_code=500, detail="Failed to add graph memory")
#             
#     except Exception as e:
#         logger.error(f"Error in add_graph_memory endpoint: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@memory_router.post("/search")
async def search_memories_endpoint(data: dict):
    """Search memories by query.
    
    Request body:
    {
        "user_id": "gavinwood",  // optional, defaults to gavinwood
        "query": "blockchain",  // required - search query
        "limit": 10  // optional, defaults to 4
    }
    """
    try:
        user_id = data.get("user_id", "gavinwood")
        query = data.get("query")
        limit = data.get("limit", 4)
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Use the utility function to search memories
        memories = await asyncio.to_thread(get_relevant_memories, mem0_client, user_id, query, limit)
        
        return {
            "status": "success",
            "user_id": user_id,
            "query": query,
            "memories": memories,
            "count": len(memories)
        }
        
    except Exception as e:
        logger.error(f"Error in search_memories endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# @memory_router.post("/search-graph")
# async def search_graph_memories_endpoint(data: dict):
#     """Search graph memories by entity or relationship.
#     
#     Request body:
#     {
#         "user_id": "gavinwood",  // optional, defaults to gavinwood
#         "entity": "Ethereum",  // required - entity to search for
#         "relationship_type": "created",  // optional - filter by relationship type
#         "limit": 10  // optional, defaults to 10
#     }
#     """
#     try:
#         user_id = data.get("user_id", "gavinwood")
#         entity = data.get("entity")
#         relationship_type = data.get("relationship_type")
#         limit = data.get("limit", 10)
#         
#         if not entity:
#             raise HTTPException(status_code=400, detail="Entity is required")
#         
#         # Use the utility function to search graph memories
#         memories = await asyncio.to_thread(
#             get_graph_memories, 
#             mem0_client, 
#             user_id, 
#             entity, 
#             relationship_type, 
#             limit
#         )
#         
#         return {
#             "status": "success",
#             "user_id": user_id,
#             "entity": entity,
#             "relationship_type": relationship_type,
#             "memories": memories,
#             "count": len(memories)
#         }
#         
#     except Exception as e:
#         logger.error(f"Error in search_graph_memories endpoint: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @memory_router.get("/graph/{user_id}")
# async def get_knowledge_graph_endpoint(user_id: str = "gavinwood"):
#     """Build and return the knowledge graph for a user.
#     
#     Path parameters:
#     - user_id: User ID (defaults to gavinwood)
#     """
#     try:
#         # Build the knowledge graph
#         graph = await asyncio.to_thread(build_knowledge_graph, mem0_client, user_id)
#         
#         return {
#             "status": "success",
#             "user_id": user_id,
#             "graph": graph
#         }
#         
#     except Exception as e:
#         logger.error(f"Error in get_knowledge_graph endpoint: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@memory_router.post("/upload-doc")
async def upload_document_endpoint(
    file: UploadFile = File(...),
    user_id: str = Form("gavinwood"),
    doc_type: str = Form("document"),
    metadata: str = Form("{}")
):
    """Upload and process a document into memories.
    
    Parameters:
    - file: Document file (PDF, TXT, etc.)
    - user_id: User ID (defaults to gavinwood)
    - doc_type: Type of document (defaults to "document")
    - metadata: JSON string of additional metadata
    """
    try:
        # Read file content
        content = await file.read()
        
        # Parse metadata
        try:
            metadata_dict = json.loads(metadata)
        except:
            metadata_dict = {}
        
        # Add file info to metadata
        metadata_dict.update({
            "filename": file.filename,
            "content_type": file.content_type,
            "doc_type": doc_type,
            "upload_type": "document"
        })
        
        # Process based on file type
        if file.content_type == "text/plain" or file.filename.endswith('.txt'):
            text_content = content.decode('utf-8')
        elif file.content_type == "application/pdf" or file.filename.endswith('.pdf'):
            # For PDF, we'd need a PDF parser - for now just handle as text
            try:
                text_content = content.decode('utf-8')
            except:
                raise HTTPException(status_code=400, detail="Could not process PDF file")
        else:
            try:
                text_content = content.decode('utf-8')
            except:
                raise HTTPException(status_code=400, detail="Unsupported file type")
        
        # Split content into chunks (simple sentence-based splitting)
        chunks = []
        sentences = text_content.split('. ')
        
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk + sentence) < 500:  # Keep chunks under 500 chars
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Add each chunk as a memory
        added_memories = 0
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                chunk_metadata = metadata_dict.copy()
                chunk_metadata.update({
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                })
                
                success = await asyncio.to_thread(
                    add_memory, 
                    mem0_client, 
                    user_id, 
                    f"Assistant: Document content from {file.filename}: {chunk}", 
                    chunk_metadata
                )
                
                if success:
                    added_memories += 1
        
        return {
            "status": "success",
            "message": f"Document processed and {added_memories} memories added",
            "user_id": user_id,
            "filename": file.filename,
            "chunks_processed": len(chunks),
            "memories_added": added_memories
        }
        
    except Exception as e:
        logger.error(f"Error in upload_document endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.get("/list/{user_id}")
async def list_memories_endpoint(user_id: str = "gavinwood", limit: int = 10):
    """List all memories for a user.
    
    Path parameters:
    - user_id: User ID (defaults to gavinwood)
    
    Query parameters:
    - limit: Number of memories to return (defaults to 10)
    """
    try:
        # Get memories using search with empty query to get all
        memories = await asyncio.to_thread(
            lambda: mem0_client.get_all(user_id=user_id, limit=limit)
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "memories": memories,
            "count": len(memories)
        }
        
    except Exception as e:
        logger.error(f"Error in list_memories endpoint: {e}")
        # Fallback to search with generic query
        try:
            memories = await asyncio.to_thread(get_relevant_memories, mem0_client, user_id, "blockchain ethereum web3", limit)
            return {
                "status": "success",
                "user_id": user_id,
                "memories": memories,
                "count": len(memories),
                "note": "Retrieved using search fallback"
            }
        except Exception as e2:
            logger.error(f"Error in fallback search: {e2}")
            raise HTTPException(status_code=500, detail=str(e))

@memory_router.delete("/delete/{user_id}")
async def delete_memory_endpoint(user_id: str, memory_id: str):
    """Delete a specific memory.
    
    Path parameters:
    - user_id: User ID
    - memory_id: Memory ID to delete (passed as query parameter)
    """
    try:
        # Delete the memory
        await asyncio.to_thread(
            lambda: mem0_client.delete(memory_id=memory_id, user_id=user_id)
        )
        
        return {
            "status": "success",
            "message": "Memory deleted successfully",
            "user_id": user_id,
            "memory_id": memory_id
        }
        
    except Exception as e:
        logger.error(f"Error in delete_memory endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.delete("/delete-all/{user_id}")
async def delete_all_memories_endpoint(user_id: str = "gavinwood"):
    """Delete all memories for a user.
    
    Path parameters:
    - user_id: User ID (defaults to gavinwood)
    """
    try:
        # Delete all memories for the user
        await asyncio.to_thread(
            lambda: mem0_client.delete_all(user_id=user_id)
        )
        
        return {
            "status": "success",
            "message": "All memories deleted successfully",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error in delete_all_memories endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.get("/count/{user_id}")
async def count_memories_endpoint(user_id: str = "gavinwood"):
    """Count total memories for a user."""
    try:
        # Get all memories to count them
        memories = await asyncio.to_thread(
            lambda: mem0_client.get_all(user_id=user_id, limit=1000)
        )
        
        # Also try search with a broad query
        search_memories = await asyncio.to_thread(
            lambda: mem0_client.search("", user_id=user_id, limit=1000)
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "total_memories_get_all": len(memories) if memories else 0,
            "total_memories_search": len(search_memories.get('results', [])) if isinstance(search_memories, dict) else len(search_memories) if search_memories else 0,
            "memories_sample": memories[:3] if memories else [],
            "search_sample": search_memories
        }
        
    except Exception as e:
        logger.error(f"Error counting memories: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.post("/test")
async def test_mem0_endpoint():
    """Test mem0 functionality - add a test memory and search for it."""
    try:
        test_message = "Test memory: Gavin Wood created Polkadot"
        user_id = "gavinwood"
        
        # Test adding memory
        logger.info(f"Testing mem0 add operation...")
        add_result = await asyncio.to_thread(add_memory, mem0_client, user_id, test_message, {"test": True})
        
        if not add_result:
            return {
                "status": "error",
                "message": "Failed to add test memory",
                "add_result": add_result
            }
        
        # Test searching memories
        logger.info(f"Testing mem0 search operation...")
        search_result = await asyncio.to_thread(get_relevant_memories, mem0_client, user_id, "Polkadot", 5)
        
        # Test raw search
        raw_search = await asyncio.to_thread(
            lambda: mem0_client.search("Polkadot", user_id=user_id, limit=5)
        )
        
        return {
            "status": "success",
            "test_memory_added": add_result,
            "search_results": search_result,
            "raw_search_result": raw_search,
            "search_count": len(search_result) if search_result else 0
        }
        
    except Exception as e:
        logger.error(f"Error in test_mem0 endpoint: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e)) 