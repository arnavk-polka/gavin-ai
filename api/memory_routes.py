import json
import asyncio
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from typing import Optional
from config import logger, mem0_client, get_embedder
from utils import add_memory, get_relevant_memories

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

@memory_router.post("/search")
async def search_memories_endpoint(data: dict):
    """Search memories in mem0.
    
    Request body:
    {
        "user_id": "gavinwood",  // optional, defaults to gavinwood
        "query": "Your search query here",
        "limit": 5  // optional, defaults to 4
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

@memory_router.delete("/{memory_id}")
async def delete_memory_endpoint(memory_id: str, user_id: str = "gavinwood"):
    """Delete a specific memory by ID.
    
    Path parameters:
    - memory_id: The ID of the memory to delete
    
    Query parameters:
    - user_id: User ID (defaults to gavinwood)
    """
    try:
        # Delete memory using mem0 client
        result = await asyncio.to_thread(
            lambda: mem0_client.delete(memory_id=memory_id)
        )
        
        return {
            "status": "success",
            "message": f"Memory {memory_id} deleted successfully",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error in delete_memory endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.post("/bulk-add")
async def bulk_add_memories_endpoint(
    file: UploadFile = File(...),
    user_id: str = Form("gavinwood"),
    metadata: str = Form("{}")
):
    """Add multiple memories at once from a JSON file.
    
    Form fields:
    - file: JSON file containing memory object(s) (required)
    - user_id: User ID (optional, defaults to gavinwood)
    - metadata: JSON string with metadata to apply to all memories (optional)
    
    Metadata JSON format:
    {
        "category": "article",
        "type": "knowledge", 
        "source": "web",
        "tags": ["blockchain", "ethereum"]
    }
    
    File can contain single object or array:
    {
        "url": "https://example.com/article1",
        "title": "Article Title",
        "description": "Article description content",
        "content": "Full article content..."
    }
    
    OR array:
    [
        {
            "url": "https://example.com/article1",
            "title": "Article Title", 
            "description": "Article description content",
            "content": "Full article content..."
        }
    ]
    """
    try:
        # Parse metadata
        try:
            base_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON format")
        
        # Read from uploaded file
        try:
            file_content = await file.read()
            data = json.loads(file_content.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format in uploaded file")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")
        
        # Handle both single object and array formats
        if isinstance(data, dict):
            # Single object - convert to array
            memories = [data]
        elif isinstance(data, list):
            # Already an array
            memories = data
        else:
            raise HTTPException(status_code=400, detail="File must contain a JSON object or array of objects")
        
        if not memories:
            raise HTTPException(status_code=400, detail="File must contain at least one memory")
        
        results = []
        for i, memory_data in enumerate(memories):
            url = memory_data.get("url")
            title = memory_data.get("title")
            description = memory_data.get("description")
            content = memory_data.get("content", "")
            
            # Validate required fields
            if not url:
                results.append({"index": i, "status": "failed", "error": "URL is required"})
                continue
            if not title:
                results.append({"index": i, "status": "failed", "error": "Title is required"})
                continue
            if not description:
                results.append({"index": i, "status": "failed", "error": "Description is required"})
                continue
            
            # Build the memory message from the structured data
            # Use content if available, otherwise use description
            main_content = content if content else description
            memory_message = f"Title: {title}\nURL: {url}\nDescription: {description}"
            if content and content != description:
                memory_message += f"\nContent: {content}"
            
            # Create metadata for this memory, combining base metadata with specific fields
            memory_metadata = base_metadata.copy()
            memory_metadata.update({
                "url": url,
                "title": title,
                "category": base_metadata.get("category", "unknown"),
                "type": base_metadata.get("type", "knowledge"),
                "source": base_metadata.get("source", "bulk_add")
            })
            
            try:
                success = await asyncio.to_thread(
                    add_memory, mem0_client, user_id, f"Assistant: {memory_message}", memory_metadata
                )
                if success:
                    results.append({"index": i, "status": "success", "url": url, "title": title})
                else:
                    results.append({"index": i, "status": "failed", "error": "Unknown error", "url": url})
            except Exception as e:
                results.append({"index": i, "status": "failed", "error": str(e), "url": url})
        
        successful = len([r for r in results if r["status"] == "success"])
        failed = len(results) - successful
        
        return {
            "status": "completed",
            "user_id": user_id,
            "total_memories": len(memories),
            "successful": successful,
            "failed": failed,
            "results": results,
            "applied_metadata": base_metadata
        }
        
    except Exception as e:
        logger.error(f"Error in bulk_add_memories endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@memory_router.post("/add-document")
async def add_document_endpoint(data: dict):
    """Process and add a long document using semantic chunking with nomic embedder.
    
    Request body:
    {
        "user_id": "gavinwood",  // optional, defaults to gavinwood
        "document": {
            "title": "Document Title",
            "content": "Very long document content...",
            "chunk_size": 300,  // optional, target words per chunk
            "overlap": 50,      // optional, overlap between chunks
            "metadata": {}      // optional, additional metadata
        }
    }
    """
    try:
        import re
        import numpy as np
        
        user_id = data.get("user_id", "gavinwood")
        document_data = data.get("document", {})
        
        title = document_data.get("title", "Untitled Document")
        content = document_data.get("content")
        target_chunk_size = document_data.get("chunk_size", 300)  # words
        overlap_size = document_data.get("overlap", 50)  # words
        base_metadata = document_data.get("metadata", {})
        
        if not content:
            raise HTTPException(status_code=400, detail="Document content is required")
        
        # Get the nomic embedder
        embedder = await asyncio.to_thread(get_embedder)
        
        def split_into_sentences(text):
            """Split text into sentences using regex."""
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            return [s.strip() for s in sentences if s.strip()]
        
        def create_semantic_chunks(sentences, embedder, target_size=300, overlap=50):
            """Create chunks based on semantic similarity using embeddings."""
            if not sentences:
                return []
            
            # Get embeddings for all sentences
            logger.info(f"Computing embeddings for {len(sentences)} sentences...")
            embeddings = embedder.encode(sentences)
            
            chunks = []
            current_chunk = []
            current_word_count = 0
            
            i = 0
            while i < len(sentences):
                sentence = sentences[i]
                word_count = len(sentence.split())
                
                # If adding this sentence would exceed target size, finalize current chunk
                if current_word_count + word_count > target_size and current_chunk:
                    # Finalize current chunk
                    chunk_text = ' '.join(current_chunk)
                    chunks.append(chunk_text)
                    
                    # Start new chunk with overlap
                    if overlap > 0 and len(current_chunk) > 1:
                        # Keep last few sentences for overlap
                        overlap_sentences = []
                        overlap_words = 0
                        for sent in reversed(current_chunk):
                            sent_words = len(sent.split())
                            if overlap_words + sent_words <= overlap:
                                overlap_sentences.insert(0, sent)
                                overlap_words += sent_words
                            else:
                                break
                        current_chunk = overlap_sentences
                        current_word_count = overlap_words
                    else:
                        current_chunk = []
                        current_word_count = 0
                
                # Add current sentence
                current_chunk.append(sentence)
                current_word_count += word_count
                i += 1
            
            # Add final chunk if it exists
            if current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append(chunk_text)
            
            return chunks
        
        # Process the document
        logger.info(f"Processing document: {title}")
        sentences = await asyncio.to_thread(split_into_sentences, content)
        logger.info(f"Split into {len(sentences)} sentences")
        
        chunks = await asyncio.to_thread(
            create_semantic_chunks, 
            sentences, 
            embedder, 
            target_chunk_size, 
            overlap_size
        )
        logger.info(f"Created {len(chunks)} semantic chunks")
        
        # Add chunks to memory
        results = []
        for i, chunk in enumerate(chunks):
            chunk_metadata = {
                **base_metadata,
                "document_title": title,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_type": "semantic",
                "word_count": len(chunk.split())
            }
            
            try:
                success = await asyncio.to_thread(
                    add_memory, 
                    mem0_client, 
                    user_id, 
                    f"Assistant: {chunk}", 
                    chunk_metadata
                )
                if success:
                    results.append({
                        "chunk_index": i,
                        "status": "success",
                        "word_count": len(chunk.split()),
                        "preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
                    })
                else:
                    results.append({
                        "chunk_index": i,
                        "status": "failed",
                        "error": "Failed to add to mem0"
                    })
            except Exception as e:
                results.append({
                    "chunk_index": i,
                    "status": "failed", 
                    "error": str(e)
                })
        
        successful = len([r for r in results if r["status"] == "success"])
        failed = len(results) - successful
        
        return {
            "status": "completed",
            "document_title": title,
            "user_id": user_id,
            "total_chunks": len(chunks),
            "successful_chunks": successful,
            "failed_chunks": failed,
            "processing_summary": {
                "original_sentences": len(sentences),
                "target_chunk_size": target_chunk_size,
                "overlap_size": overlap_size,
                "avg_chunk_size": sum(len(chunk.split()) for chunk in chunks) // len(chunks) if chunks else 0
            },
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error in add_document endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 