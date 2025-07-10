import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
    logger.info("asyncpg imported successfully")
except ImportError as e:
    ASYNCPG_AVAILABLE = False
    logger.error(f"asyncpg not available: {e}")
    logger.error("Please install asyncpg: pip install asyncpg>=0.28.0")

# Global connection pool
pool = None

async def init_database():
    """Initialize PostgreSQL connection pool using DB_CONNECTION_URL from environment."""
    global pool
    
    if not ASYNCPG_AVAILABLE:
        logger.error("Cannot initialize database: asyncpg is not available")
        logger.error("Install with: pip install asyncpg>=0.28.0")
        raise ImportError("asyncpg is required for database functionality")
    
    db_url = os.getenv("DB_CONNECTION_URL")
    logger.info(f"Raw DB_CONNECTION_URL from environment: {repr(db_url)}")
    
    if not db_url:
        logger.error("DB_CONNECTION_URL environment variable not set")
        raise ValueError("DB_CONNECTION_URL environment variable is required")
    
    logger.info(f"DB URL length: {len(db_url)} characters")
    logger.info(f"DB URL starts with: {db_url[:20]}...")
    
    # Try to parse and log safely
    try:
        if '@' in db_url:
            parts = db_url.split('@')
            masked_url = f"{parts[0].split('://')[0]}://***@{parts[1]}"
        else:
            masked_url = db_url[:20] + "***"
        logger.info(f"Connecting to PostgreSQL: {masked_url}")
    except Exception as parse_error:
        logger.warning(f"Could not parse URL for logging: {parse_error}")
        logger.info(f"Connecting to PostgreSQL: {db_url[:10]}***")
    
    try:
        # Create connection pool
        pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        
        # Create tables if they don't exist
        await create_tables()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def create_tables():
    """Create database tables if they don't exist."""
    async with pool.acquire() as conn:
        # Check if we need to migrate from old schema
        old_schema_check = await conn.fetchval("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'conversations' AND column_name = 'user_message'
        """)
        
        old_conversations = []  # Initialize for potential migration
        
        if old_schema_check:
            logger.info("Detected old conversation schema - migrating to new multi-turn schema")
            
            # Backup old data if exists
            old_conversations = await conn.fetch("""
                SELECT handle, user_message, assistant_response, row_number, 
                       memories_used, serper_results, processing_time, timestamp, metadata
                FROM conversations
            """)
            
            # Drop old table
            await conn.execute("DROP TABLE IF EXISTS conversations CASCADE")
            logger.info(f"Backed up {len(old_conversations)} old conversations")
        
        # Create new conversations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255),
                handle VARCHAR(255),
                messages JSONB,
                total_messages INTEGER DEFAULT 1,
                first_message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                row_numbers_used JSONB,
                total_processing_time REAL DEFAULT 0,
                metadata JSONB
            )
        """)
        
        # Create conversation_messages table for individual messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                session_id VARCHAR(255),
                message_index INTEGER,
                user_message TEXT,
                assistant_response TEXT,
                row_number INTEGER,
                memories_used JSONB,
                serper_results TEXT,
                processing_time REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            )
        """)
        
        # Create indexes for faster queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_handle ON conversations(handle)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_last_message_time ON conversations(last_message_time)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_id ON conversation_messages(session_id)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_messages_timestamp ON conversation_messages(timestamp)
        """)
        
        # Create preprocessing_prompts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS preprocessing_prompts (
                id SERIAL PRIMARY KEY,
                user_message TEXT,
                row_number INTEGER,
                analysis_data JSONB,
                search_query VARCHAR(500),
                memory_query VARCHAR(500),
                raw_openai_response TEXT,
                processing_time REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            )
        """)
        
        # Create index on timestamp for faster sorting
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_preprocessing_timestamp ON preprocessing_prompts(timestamp)
        """)
        
        # Migrate old conversations to new format if we had any
        if old_schema_check and old_conversations:
            logger.info("Migrating old conversations to new multi-turn format...")
            
            for old_conv in old_conversations:
                try:
                    # Create session ID from handle and timestamp
                    import hashlib
                    timestamp_str = str(old_conv["timestamp"]) if old_conv["timestamp"] else "unknown"
                    session_id = f"{old_conv['handle']}_{hashlib.md5(timestamp_str.encode()).hexdigest()[:8]}"
                    
                    # Convert old format to new message format
                    message_data = {
                        "user_message": old_conv["user_message"],
                        "assistant_response": old_conv["assistant_response"],
                        "row_number": old_conv["row_number"],
                        "memories_used": json.loads(old_conv["memories_used"]) if old_conv["memories_used"] else [],
                        "serper_results": old_conv["serper_results"] or "",
                        "processing_time": old_conv["processing_time"] or 0.0,
                        "timestamp": old_conv["timestamp"].isoformat() if old_conv["timestamp"] else datetime.utcnow().isoformat()
                    }
                    
                    # Insert into new format
                    conversation_id = await conn.fetchval("""
                        INSERT INTO conversations 
                        (session_id, handle, messages, total_messages, row_numbers_used, total_processing_time, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING id
                    """, session_id, old_conv["handle"], json.dumps([message_data]), 1, 
                        json.dumps([old_conv["row_number"]]), old_conv["processing_time"] or 0.0,
                        json.dumps(json.loads(old_conv["metadata"]) if old_conv["metadata"] else {}))
                    
                    # Also insert into messages table
                    await conn.execute("""
                        INSERT INTO conversation_messages 
                        (conversation_id, session_id, message_index, user_message, assistant_response, 
                         row_number, memories_used, serper_results, processing_time, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, conversation_id, session_id, 0, old_conv["user_message"], old_conv["assistant_response"],
                        old_conv["row_number"], old_conv["memories_used"] or '[]', 
                        old_conv["serper_results"] or '', old_conv["processing_time"] or 0.0,
                        old_conv["metadata"] or '{}')
                    
                except Exception as migrate_error:
                    logger.error(f"Error migrating conversation: {migrate_error}")
            
            logger.info(f"Successfully migrated {len(old_conversations)} conversations to new format")
        
        logger.info("Database tables created/verified")

async def save_conversation(
    handle: str,
    user_message: str,
    assistant_response: str,
    session_id: str,
    row_number: int = 1,
    memories_used: list = None,
    serper_results: str = "",
    processing_time: float = 0.0,
    metadata: dict = None
) -> int:
    """Save a conversation message to the database, tracking multi-turn sessions."""
    if pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with pool.acquire() as conn:
        try:
            # Check if conversation session already exists
            existing_conv = await conn.fetchrow("""
                SELECT id, messages, total_messages, row_numbers_used, total_processing_time
                FROM conversations 
                WHERE session_id = $1 AND handle = $2
            """, session_id, handle)
            
            message_data = {
                "user_message": user_message,
                "assistant_response": assistant_response,
                "row_number": row_number,
                "memories_used": memories_used or [],
                "serper_results": serper_results,
                "processing_time": processing_time,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if existing_conv:
                # Update existing conversation
                conversation_id = existing_conv["id"]
                existing_messages = json.loads(existing_conv["messages"]) if existing_conv["messages"] else []
                existing_row_numbers = json.loads(existing_conv["row_numbers_used"]) if existing_conv["row_numbers_used"] else []
                
                existing_messages.append(message_data)
                existing_row_numbers.append(row_number)
                
                await conn.execute("""
                    UPDATE conversations 
                    SET messages = $1, 
                        total_messages = $2,
                        last_message_time = CURRENT_TIMESTAMP,
                        row_numbers_used = $3,
                        total_processing_time = $4,
                        metadata = $5
                    WHERE id = $6
                """, json.dumps(existing_messages), 
                     len(existing_messages),
                     json.dumps(existing_row_numbers),
                     existing_conv["total_processing_time"] + processing_time,
                     json.dumps(metadata or {}),
                     conversation_id)
                
                message_index = len(existing_messages) - 1
                
            else:
                # Create new conversation
                conversation_id = await conn.fetchval("""
                    INSERT INTO conversations 
                    (session_id, handle, messages, total_messages, row_numbers_used, total_processing_time, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """, session_id, handle, json.dumps([message_data]), 1, 
                    json.dumps([row_number]), processing_time, json.dumps(metadata or {}))
                
                message_index = 0
            
            # Also save individual message for detailed tracking
            message_id = await conn.fetchval("""
                INSERT INTO conversation_messages 
                (conversation_id, session_id, message_index, user_message, assistant_response, 
                 row_number, memories_used, serper_results, processing_time, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, conversation_id, session_id, message_index, user_message, assistant_response,
                row_number, json.dumps(memories_used or []), serper_results, processing_time, 
                json.dumps(metadata or {}))
            
            logger.info(f"Saved conversation {conversation_id}, message {message_id} for handle {handle}, session {session_id}")
            return conversation_id
            
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            raise

async def save_preprocessing_prompt(
    user_message: str,
    row_number: int,
    analysis_data: dict = None,
    search_query: str = "",
    memory_query: str = "",
    raw_openai_response: str = "",
    processing_time: float = 0.0,
    metadata: dict = None
) -> int:
    """Save a preprocessing prompt to the database."""
    if pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with pool.acquire() as conn:
        try:
            prompt_id = await conn.fetchval("""
                INSERT INTO preprocessing_prompts 
                (user_message, row_number, analysis_data, search_query, memory_query, raw_openai_response, processing_time, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
            """, user_message, row_number, json.dumps(analysis_data or {}), 
                search_query, memory_query, raw_openai_response, processing_time, json.dumps(metadata or {}))
            
            logger.info(f"Saved preprocessing prompt {prompt_id} for row {row_number}")
            return prompt_id
            
        except Exception as e:
            logger.error(f"Error saving preprocessing prompt: {e}")
            raise

async def get_conversations(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get conversations from database, showing multi-turn sessions."""
    if pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, session_id, handle, messages, total_messages, 
                   first_message_time, last_message_time, row_numbers_used, 
                   total_processing_time, metadata
            FROM conversations 
            ORDER BY last_message_time DESC 
            LIMIT $1 OFFSET $2
        """, limit, offset)
        
        conversations = []
        for row in rows:
            messages = json.loads(row["messages"]) if row["messages"] else []
            row_numbers = json.loads(row["row_numbers_used"]) if row["row_numbers_used"] else []
            
            # Get first and last message for preview
            first_message = messages[0] if messages else {}
            last_message = messages[-1] if messages else {}
            
            conversations.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "handle": row["handle"],
                "total_messages": row["total_messages"],
                "first_user_message": first_message.get("user_message", ""),
                "last_user_message": last_message.get("user_message", "") if len(messages) > 1 else "",
                "first_assistant_response": first_message.get("assistant_response", ""),
                "last_assistant_response": last_message.get("assistant_response", ""),
                "row_numbers_used": row_numbers,
                "most_recent_row": row_numbers[-1] if row_numbers else 1,
                "total_processing_time": row["total_processing_time"],
                "first_message_time": row["first_message_time"].isoformat() if row["first_message_time"] else None,
                "last_message_time": row["last_message_time"].isoformat() if row["last_message_time"] else None,
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "messages": messages  # Include all messages for detailed view
            })
        
        return conversations

async def get_preprocessing_prompts(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get preprocessing prompts from database."""
    if pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, user_message, row_number, analysis_data, search_query, 
                   memory_query, raw_openai_response, processing_time, timestamp, metadata
            FROM preprocessing_prompts 
            ORDER BY timestamp DESC 
            LIMIT $1 OFFSET $2
        """, limit, offset)
        
        prompts = []
        for row in rows:
            prompts.append({
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
            })
        
        return prompts

async def get_conversation_stats() -> Dict[str, Any]:
    """Get conversation statistics."""
    if pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with pool.acquire() as conn:
        # Get total counts
        total_conversations = await conn.fetchval("SELECT COUNT(*) FROM conversations")
        total_preprocessing = await conn.fetchval("SELECT COUNT(*) FROM preprocessing_prompts")
        
        # Get row distribution
        row_dist_rows = await conn.fetch("""
            SELECT row_number, COUNT(*) as count 
            FROM conversations 
            GROUP BY row_number 
            ORDER BY row_number
        """)
        
        row_distribution = {}
        for row in row_dist_rows:
            row_distribution[f"row_{row['row_number']}"] = row["count"]
        
        # Get recent activity (last 24 hours)
        recent_conversations = await conn.fetchval("""
            SELECT COUNT(*) FROM conversations 
            WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """)
        
        recent_preprocessing = await conn.fetchval("""
            SELECT COUNT(*) FROM preprocessing_prompts 
            WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """)
        
        return {
            "total_conversations": total_conversations,
            "total_preprocessing": total_preprocessing,
            "row_distribution": row_distribution,
            "recent_24h": {
                "conversations": recent_conversations,
                "preprocessing": recent_preprocessing
            }
        }

async def close_database():
    """Close database connection pool."""
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database connection pool closed") 