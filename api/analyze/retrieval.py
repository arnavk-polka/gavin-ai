"""Retrieval utilities for context search using spaCy embeddings and Mem0."""

import logging
from typing import List, Dict, Any, Optional

from spacy_pipeline import get_nlp

logger = logging.getLogger(__name__)

# Global pipeline instance for efficiency
_nlp_pipeline = None
_mem0_client = None


def initialize_retrieval(mem0_client=None) -> None:
    """Initialize retrieval system with Mem0 client and spaCy pipeline.
    
    Args:
        mem0_client: Mem0 client instance for similarity search
    """
    global _nlp_pipeline, _mem0_client
    
    if _nlp_pipeline is None:
        logger.info("Initializing spaCy pipeline for retrieval...")
        _nlp_pipeline = get_nlp(mem0_client=None)  # Don't need VectorExporter for queries
        logger.info(f"Pipeline initialized with components: {_nlp_pipeline.pipe_names}")
    
    _mem0_client = mem0_client
    logger.info(f"Mem0 client {'set' if mem0_client else 'not set'}")


def retrieve_context(query: str, k: int = 8, mem0_client: Optional[Any] = None) -> Dict[str, Any]:
    """Run the spaCy pipeline on query and retrieve similar contexts from Mem0.
    
    Args:
        query: Input text query to search for
        k: Maximum number of results to return (default: 8)
        mem0_client: Optional Mem0 client, uses global if not provided
        
    Returns:
        Dict with keys: 'results' (list of search hits) and 'query_tone' (tone stats)
        Format: {"results": [...], "query_tone": {...}}
    """
    global _nlp_pipeline, _mem0_client
    
    # Initialize if needed
    if _nlp_pipeline is None:
        initialize_retrieval(mem0_client)
    
    # Use provided client or global client
    client = mem0_client or _mem0_client
    
    if client is None:
        raise ValueError("No Mem0 client available for retrieval")
    
    if not query.strip():
        raise ValueError("Empty query provided")
    
    # Process query through spaCy pipeline to get vector and tone
    doc = _nlp_pipeline(query)
    
    if not hasattr(doc, 'vector') or doc.vector is None:
        raise RuntimeError("No vector available from spaCy pipeline")
    
    # Perform similarity search with Mem0
    search_results = client.similarity_search(
        query_vector=doc.vector,
        k=k
    )
    
    # Return both search results and query tone stats
    return {
        "results": search_results,
        "query_tone": doc._.tone
    }


def retrieve_context_with_filters(
    query: str, 
    k: int = 8, 
    filters: Optional[Dict[str, Any]] = None,
    mem0_client: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """Enhanced retrieval with metadata filtering support.
    
    Args:
        query: Input text query to search for
        k: Maximum number of results to return
        filters: Optional metadata filters for search
        mem0_client: Optional Mem0 client
        
    Returns:
        List of filtered context results
    """
    global _nlp_pipeline, _mem0_client
    
    # Initialize if needed
    if _nlp_pipeline is None:
        initialize_retrieval(mem0_client)
    
    client = mem0_client or _mem0_client
    
    if client is None:
        logger.warning("No Mem0 client available for filtered retrieval")
        return []
    
    try:
        # Process query
        doc = _nlp_pipeline(query)
        
        if not hasattr(doc, 'vector') or doc.vector is None:
            logger.error("No vector available from spaCy pipeline")
            return []
        
        # Perform filtered similarity search
        search_kwargs = {
            "query_vector": doc.vector,
            "k": k
        }
        
        # Add filters if supported and provided
        if filters:
            search_kwargs["filters"] = filters
        
        search_results = client.similarity_search(**search_kwargs)
        
        # Format results
        formatted_results = []
        for result in search_results:
            formatted_result = {
                "text": result.get("text", ""),
                "score": result.get("score", 0.0),
                "metadata": result.get("metadata", {})
            }
            formatted_results.append(formatted_result)
        
        logger.info(f"Retrieved {len(formatted_results)} filtered context results")
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error during filtered context retrieval: {e}")
        return []


def get_pipeline_info() -> Dict[str, Any]:
    """Get information about the loaded spaCy pipeline.
    
    Returns:
        Dictionary with pipeline information
    """
    global _nlp_pipeline
    
    if _nlp_pipeline is None:
        return {"status": "not_initialized"}
    
    return {
        "status": "initialized",
        "model": _nlp_pipeline.meta.get("name", "unknown"),
        "version": _nlp_pipeline.meta.get("version", "unknown"),
        "components": _nlp_pipeline.pipe_names,
        "vector_size": _nlp_pipeline.vocab.vectors_length if _nlp_pipeline.vocab.vectors_length else None
    } 