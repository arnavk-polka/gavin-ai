import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from database import get_conversations, get_preprocessing_prompts, get_conversation_stats
import os
import json

logger = logging.getLogger(__name__)

logs_router = APIRouter()

@logs_router.get("/logs")
async def serve_logs_ui():
    """Serve the logs UI interface."""
    from config import static_path
    logs_path = os.path.join(static_path, "logs.html")
    
    if os.path.isfile(logs_path):
        return FileResponse(logs_path)
    else:
        raise HTTPException(status_code=404, detail="Logs interface not found")

@logs_router.get("/api/logs/conversations")
async def get_conversations_api(
    limit: int = Query(50, le=100, description="Number of conversations to return"),
    offset: int = Query(0, ge=0, description="Number of conversations to skip")
):
    """Get conversations from database with pagination."""
    logger.info(f"API request for conversations: limit={limit}, offset={offset}")
    try:
        conversations = await get_conversations(limit=limit, offset=offset)
        
        # Get total count for pagination
        from database import pool
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM conversations")
        
        return JSONResponse({
            "status": "success",
            "conversations": conversations,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error(f"Error retrieving conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@logs_router.get("/api/logs/preprocessing")
async def get_preprocessing_api(
    limit: int = Query(50, le=100, description="Number of preprocessing records to return"),
    offset: int = Query(0, ge=0, description="Number of preprocessing records to skip")
):
    """Get preprocessing prompts from database with pagination."""
    try:
        preprocessing = await get_preprocessing_prompts(limit=limit, offset=offset)
        
        # Get total count for pagination
        from database import pool
        async with pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM preprocessing_prompts")
        
        return JSONResponse({
            "status": "success",
            "preprocessing": preprocessing,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error(f"Error retrieving preprocessing records: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@logs_router.get("/api/logs/stats")
async def get_logs_stats():
    """Get conversation and preprocessing statistics."""
    try:
        stats = await get_conversation_stats()
        return JSONResponse({
            "status": "success",
            **stats
        })
    except Exception as e:
        logger.error(f"Error retrieving logs stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@logs_router.get("/api/logs/conversation/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    """Get detailed information about a specific conversation."""
    try:
        from database import pool
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, session_id, handle, messages, total_messages,
                       first_message_time, last_message_time, row_numbers_used, 
                       total_processing_time, metadata
                FROM conversations 
                WHERE id = $1
            """, conversation_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Safely parse messages
            try:
                messages = json.loads(row["messages"]) if row["messages"] else []
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error parsing messages for conversation {conversation_id}: {e}")
                messages = []
            
            # Fetch related preprocessing data for each message
            preprocessing_data = []
            for i, msg in enumerate(messages):
                try:
                    user_message = msg.get("user_message", "") if isinstance(msg, dict) else ""
                    timestamp = msg.get("timestamp") if isinstance(msg, dict) else None
                    
                    if user_message:
                        # Find preprocessing records that match this message
                        prep_rows = await conn.fetch("""
                            SELECT id, user_message, row_number, analysis_data, search_query, 
                                   memory_query, raw_openai_response, processing_time, timestamp, metadata
                            FROM preprocessing_prompts 
                            WHERE user_message = $1
                            ORDER BY timestamp DESC 
                            LIMIT 1
                        """, user_message)
                        
                        if prep_rows:
                            prep_data = prep_rows[0]
                            preprocessing_data.append({
                                "id": prep_data["id"],
                                "user_message": prep_data["user_message"],
                                "row_number": prep_data["row_number"],
                                "analysis_data": json.loads(prep_data["analysis_data"]) if prep_data["analysis_data"] else {},
                                "search_query": prep_data["search_query"],
                                "memory_query": prep_data["memory_query"],
                                "raw_openai_response": prep_data["raw_openai_response"],
                                "processing_time": prep_data["processing_time"],
                                "timestamp": prep_data["timestamp"].isoformat() if prep_data["timestamp"] else None,
                                "metadata": json.loads(prep_data["metadata"]) if prep_data["metadata"] else {}
                            })
                        else:
                            preprocessing_data.append(None)
                    else:
                        preprocessing_data.append(None)
                except Exception as e:
                    logger.error(f"Error processing message {i} for conversation {conversation_id}: {e}")
                    preprocessing_data.append(None)
            
            # Safely parse other JSON fields
            try:
                row_numbers_used = json.loads(row["row_numbers_used"]) if row["row_numbers_used"] else []
            except (json.JSONDecodeError, TypeError):
                row_numbers_used = []
                
            try:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            
            conversation = {
                "id": row["id"],
                "session_id": row["session_id"],
                "handle": row["handle"],
                "messages": messages,
                "total_messages": row["total_messages"],
                "first_message_time": row["first_message_time"].isoformat() if row["first_message_time"] else None,
                "last_message_time": row["last_message_time"].isoformat() if row["last_message_time"] else None,
                "row_numbers_used": row_numbers_used,
                "total_processing_time": row["total_processing_time"],
                "metadata": metadata,
                "preprocessing_data": preprocessing_data  # Add preprocessing data
            }
            
            return JSONResponse({
                "status": "success",
                "conversation": conversation
            })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation {conversation_id}: {e}")
        logger.error(f"Error details: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@logs_router.get("/api/logs/preprocessing/{preprocessing_id}")
async def get_preprocessing_detail(preprocessing_id: int):
    """Get detailed information about a specific preprocessing record."""
    try:
        from database import pool
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_message, row_number, analysis_data, search_query, 
                       memory_query, raw_openai_response, processing_time, timestamp, metadata
                FROM preprocessing_prompts 
                WHERE id = $1
            """, preprocessing_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Preprocessing record not found")
            
            preprocessing = {
                "id": row["id"],
                "user_message": row["user_message"],
                "row_number": row["row_number"],
                "analysis_data": json.loads(row["analysis_data"]) if row["analysis_data"] else {},
                "search_query": row["search_query"],
                "memory_query": row["memory_query"],
                "raw_openai_response": row["raw_openai_response"],
                "processing_time": row["processing_time"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
            }
            
            return JSONResponse({
                "status": "success",
                "preprocessing": preprocessing
            })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving preprocessing {preprocessing_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 