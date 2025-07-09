#!/usr/bin/env python3
"""
Database Migration Script for GavinAI
=====================================

This script migrates the conversations table from the old single-message format
to the new multi-turn conversation format.

Usage:
    python migrate_db.py

Requirements:
    - DB_CONNECTION_URL environment variable set
    - asyncpg installed
"""

import os
import asyncio
import asyncpg
import json
import logging
from datetime import datetime
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_database():
    """Migrate database from old to new schema."""
    
    db_url = os.getenv("DB_CONNECTION_URL")
    if not db_url:
        logger.error("DB_CONNECTION_URL environment variable not set")
        return False
    
    logger.info("Starting database migration...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(db_url)
        
        # Check if old schema exists
        old_schema_check = await conn.fetchval("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'conversations' AND column_name = 'user_message'
        """)
        
        if not old_schema_check:
            logger.info("No old schema detected - migration not needed")
            await conn.close()
            return True
        
        logger.info("Old schema detected - starting migration...")
        
        # Backup old conversations
        old_conversations = await conn.fetch("""
            SELECT handle, user_message, assistant_response, row_number, 
                   memories_used, serper_results, processing_time, timestamp, metadata
            FROM conversations
        """)
        
        logger.info(f"Found {len(old_conversations)} conversations to migrate")
        
        if len(old_conversations) == 0:
            logger.info("No conversations to migrate - dropping old table")
        else:
            # Save backup to file
            backup_data = []
            for conv in old_conversations:
                backup_data.append({
                    'handle': conv['handle'],
                    'user_message': conv['user_message'],
                    'assistant_response': conv['assistant_response'],
                    'row_number': conv['row_number'],
                    'memories_used': conv['memories_used'],
                    'serper_results': conv['serper_results'],
                    'processing_time': conv['processing_time'],
                    'timestamp': conv['timestamp'].isoformat() if conv['timestamp'] else None,
                    'metadata': conv['metadata']
                })
            
            # Write backup file
            backup_file = f"conversations_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)
            logger.info(f"Backup saved to {backup_file}")
        
        # Drop old tables
        await conn.execute("DROP TABLE IF EXISTS conversations CASCADE")
        await conn.execute("DROP TABLE IF EXISTS conversation_messages CASCADE")
        logger.info("Dropped old tables")
        
        # Create new schema
        await conn.execute("""
            CREATE TABLE conversations (
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
        
        await conn.execute("""
            CREATE TABLE conversation_messages (
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
        
        # Create indexes
        indexes = [
            "CREATE INDEX idx_conversations_session_id ON conversations(session_id)",
            "CREATE INDEX idx_conversations_handle ON conversations(handle)", 
            "CREATE INDEX idx_conversations_last_message_time ON conversations(last_message_time)",
            "CREATE INDEX idx_conversation_messages_session_id ON conversation_messages(session_id)",
            "CREATE INDEX idx_conversation_messages_timestamp ON conversation_messages(timestamp)"
        ]
        
        for index_sql in indexes:
            await conn.execute(index_sql)
        
        logger.info("Created new schema")
        
        # Migrate old conversations if any
        if old_conversations:
            logger.info("Migrating conversations to new format...")
            
            for i, old_conv in enumerate(old_conversations):
                try:
                    # Generate session ID
                    timestamp_str = str(old_conv["timestamp"]) if old_conv["timestamp"] else f"migration_{i}"
                    session_id = f"{old_conv['handle']}_{hashlib.md5(timestamp_str.encode()).hexdigest()[:8]}"
                    
                    # Convert to new message format
                    message_data = {
                        "user_message": old_conv["user_message"],
                        "assistant_response": old_conv["assistant_response"],
                        "row_number": old_conv["row_number"],
                        "memories_used": json.loads(old_conv["memories_used"]) if old_conv["memories_used"] else [],
                        "serper_results": old_conv["serper_results"] or "",
                        "processing_time": old_conv["processing_time"] or 0.0,
                        "timestamp": old_conv["timestamp"].isoformat() if old_conv["timestamp"] else datetime.utcnow().isoformat()
                    }
                    
                    # Insert into conversations table
                    conversation_id = await conn.fetchval("""
                        INSERT INTO conversations 
                        (session_id, handle, messages, total_messages, row_numbers_used, total_processing_time, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING id
                    """, session_id, old_conv["handle"], json.dumps([message_data]), 1,
                        json.dumps([old_conv["row_number"]]), old_conv["processing_time"] or 0.0,
                        json.dumps(json.loads(old_conv["metadata"]) if old_conv["metadata"] else {}))
                    
                    # Insert into messages table
                    await conn.execute("""
                        INSERT INTO conversation_messages 
                        (conversation_id, session_id, message_index, user_message, assistant_response, 
                         row_number, memories_used, serper_results, processing_time, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, conversation_id, session_id, 0, old_conv["user_message"], old_conv["assistant_response"],
                        old_conv["row_number"], old_conv["memories_used"] or '[]',
                        old_conv["serper_results"] or '', old_conv["processing_time"] or 0.0,
                        old_conv["metadata"] or '{}')
                    
                    if (i + 1) % 10 == 0:
                        logger.info(f"Migrated {i + 1}/{len(old_conversations)} conversations")
                        
                except Exception as e:
                    logger.error(f"Error migrating conversation {i}: {e}")
            
            logger.info(f"Successfully migrated {len(old_conversations)} conversations")
        
        await conn.close()
        logger.info("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run migration
    success = asyncio.run(migrate_database())
    exit(0 if success else 1) 