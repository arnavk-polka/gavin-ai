import json
import os
import traceback
import asyncio
import time
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from config import logger, openai_client, mem0_client
from .preprocess_prompt import DEEP_DEBUG_PROMPT
from .deep_debug_prompt_builder import craft_deep_debug_prompt
from utils.debug_utils import get_memories_with_timeout
from utils.route_helpers import search_serper

deep_debug_router = APIRouter()

# Global storage for conversation history and user persona tracking
conversation_history = []
user_persona_history = []

async def save_preprocessing_to_db(user_message: str, row_number: int, analysis_data: dict, 
                                  search_query: str, memory_query: str, raw_openai_response: str, 
                                  processing_time: float):
    """Background task to save preprocessing prompt to database."""
    try:
        from database import save_preprocessing_prompt
        await save_preprocessing_prompt(
            user_message=user_message,
            row_number=row_number,
            analysis_data=analysis_data,
            search_query=search_query,
            memory_query=memory_query,
            raw_openai_response=raw_openai_response,
            processing_time=processing_time,
            metadata={"source": "deepdebug_preprocessing"}
        )
        logger.info(f"Successfully saved preprocessing prompt to database")
    except Exception as e:
        logger.error(f"Failed to save preprocessing prompt to database: {e}")

@deep_debug_router.post("/deepdebug/analyze")
async def analyze_input(user_input: dict, background_tasks: BackgroundTasks = None):
    """Send user input to OpenAI for deep debug analysis, then use results for searches."""
    global conversation_history, user_persona_history
    
    try:
        start_time = time.time()
        user_message = user_input.get("message", "")
        if not user_message:
            raise HTTPException(status_code=400, detail="No message provided")
        
        logger.info(f"Deep debug analysis requested for: {user_message[:50]}...")
        logger.info(f"User message: '{user_message}'")
        logger.info(f"DEEP_DEBUG_PROMPT type: {type(DEEP_DEBUG_PROMPT)}")
        logger.info(f"DEEP_DEBUG_PROMPT length: {len(DEEP_DEBUG_PROMPT)}")
        logger.info(f"DEEP_DEBUG_PROMPT preview: {DEEP_DEBUG_PROMPT[:200]}...")
        
        # Format the prompt with user input
        try:
            logger.info("Attempting to format prompt...")
            formatted_prompt = DEEP_DEBUG_PROMPT.format(user_input=user_message)
            logger.info(f"Prompt formatted successfully. Length: {len(formatted_prompt)}")
            logger.info(f"Formatted prompt preview: {formatted_prompt[:200]}...")
        except Exception as format_error:
            logger.error(f"Error during prompt formatting: {format_error}")
            logger.error(f"Format error type: {type(format_error)}")
            logger.error(f"Format error traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Prompt formatting failed: {str(format_error)}")
        
        # Send to OpenAI
        try:
            logger.info("Sending to OpenAI...")
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a deep debug assistant. Provide detailed analysis in a structured format."},
                    {"role": "user", "content": formatted_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            logger.info("OpenAI response received successfully")
        except Exception as openai_error:
            logger.error(f"OpenAI API error: {openai_error}")
            logger.error(f"OpenAI error traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(openai_error)}")
        
        analysis_result = response.choices[0].message.content
        logger.info(f"Deep debug analysis completed. Response length: {len(analysis_result)}")
        logger.info(f"Analysis result preview: {analysis_result[:200]}...")
        
        # Parse the analysis to extract search queries and row selection
        try:
            # Extract JSON from the response
            if "```json" in analysis_result:
                json_start = analysis_result.find("```json") + 7
                json_end = analysis_result.find("```", json_start)
                json_str = analysis_result[json_start:json_end].strip()
            else:
                # Try to find JSON without markdown
                json_start = analysis_result.find("{")
                json_end = analysis_result.rfind("}") + 1
                json_str = analysis_result[json_start:json_end]
            
            analysis_data = json.loads(json_str)
            # Store the raw response in the analysis data for debug purposes
            analysis_data["raw_response"] = analysis_result
            logger.info(f"Parsed analysis data: {analysis_data}")
            
            # Extract search queries
            search_query = analysis_data.get("search_query", "")
            memory_query = analysis_data.get("memory_query", "")
            
            # Extract row selection from collapsed_map_row
            collapsed_map_row = analysis_data.get("collapsed_map_row", "1 · Standard Question")
            # Extract row number from the collapsed_map_row string (e.g., "10 · External Tech Critique" -> 10)
            import re
            row_match = re.search(r'^(\d+)', collapsed_map_row)
            row_number = int(row_match.group(1)) if row_match else 1
            
            logger.info(f"Extracted search_query: '{search_query}'")
            logger.info(f"Extracted memory_query: '{memory_query}'")
            logger.info(f"Extracted collapsed_map_row: '{collapsed_map_row}'")
            logger.info(f"Extracted row_number: {row_number}")
            
            # Store user persona data for conversation tracking
            user_persona = analysis_data.get("user_persona", {})
            if user_persona:
                user_persona_history.append(user_persona)
                logger.info(f"Added user persona to history: {user_persona}")
            
        except Exception as parse_error:
            logger.error(f"Error parsing analysis JSON: {parse_error}")
            logger.error(f"Analysis result: {analysis_result}")
            # Fallback to using the original user message
            search_query = user_message
            memory_query = user_message
            row_number = 1  # Default to row 1
            analysis_data = {"error": "Failed to parse analysis", "raw_response": analysis_result}
        
        # Run memory search using EXACT same function as main app
        memory_results = []
        if memory_query:
            try:
                logger.info(f"=== DEEP DEBUG MEMORY SEARCH START ===")
                logger.info(f"Calling get_memories_with_timeout with:")
                logger.info(f"  user_id: 'gavinwood'")
                logger.info(f"  query_text: '{memory_query}'")
                logger.info(f"  limit: 4")
                logger.info(f"  timeout: 5.0")
                
                # Use the EXACT same call as main application
                memories = await get_memories_with_timeout("gavinwood", memory_query, limit=4, timeout=5.0)
                
                logger.info(f"Memory search returned: {type(memories)}")
                logger.info(f"Memory search result: {memories}")
                logger.info(f"Memory count: {len(memories) if memories else 0}")
                
                if memories:
                    for i, mem in enumerate(memories):
                        logger.info(f"Memory {i+1}: {mem}")
                
                memory_results = memories
                logger.info(f"=== DEEP DEBUG MEMORY SEARCH END ===")
            except Exception as mem_error:
                logger.error(f"=== DEEP DEBUG MEMORY SEARCH ERROR ===")
                logger.error(f"Memory search error: {mem_error}")
                logger.error(f"Error type: {type(mem_error)}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                memory_results = [{"error": f"Memory search failed: {str(mem_error)}"}]
        else:
            logger.warning("No memory query extracted from analysis")
            memory_results = [{"error": "No memory query extracted from analysis"}]
        
        # Run SERPER search using EXACT same function as main app
        serper_results = ""
        if search_query:
            try:
                logger.info(f"=== DEEP DEBUG SERPER SEARCH START ===")
                logger.info(f"Calling search_serper with:")
                logger.info(f"  query: '{search_query}'")
                logger.info(f"  num_results: 3")
                
                # Use the EXACT same call as main application
                serper_results = await search_serper(search_query, num_results=3)
                
                logger.info(f"SERPER search returned: {type(serper_results)}")
                logger.info(f"SERPER result length: {len(serper_results) if serper_results else 0}")
                logger.info(f"SERPER result preview: {serper_results[:200] if serper_results else 'None'}")
                logger.info(f"=== DEEP DEBUG SERPER SEARCH END ===")
            except Exception as serper_error:
                logger.error(f"=== DEEP DEBUG SERPER SEARCH ERROR ===")
                logger.error(f"SERPER search error: {serper_error}")
                logger.error(f"Error type: {type(serper_error)}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                serper_results = f"Error: SERPER search failed - {str(serper_error)}"
        else:
            logger.warning("No search query extracted from analysis")
            serper_results = "No search query extracted from analysis"
        
        # Store conversation history for later use
        conversation_history.append(f"User: {user_message}")
        
        # Keep only last 10 messages to prevent history from growing too large
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
        
        # Save preprocessing data to database in background
        if background_tasks:
            background_tasks.add_task(
                save_preprocessing_to_db,
                user_message,
                row_number,
                analysis_data,
                search_query,
                memory_query,
                analysis_result,  # raw OpenAI response
                time.time() - start_time
            )
        
        # Return just the analysis data without generating response
        return JSONResponse({
            "status": "success",
            "user_input": user_message,
            "analysis_data": analysis_data,
            "search_query": search_query,
            "memory_query": memory_query,
            "row_number": row_number,
            "selected_row": row_number,  # For consistency with other endpoints
            "memory_results": memory_results,
            "serper_results": serper_results,
            "conversation_history": conversation_history,
            "user_persona_history": user_persona_history,
            "model_used": "gpt-4o"
        })
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in deep debug analysis: {e}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@deep_debug_router.get("/deepdebug")
async def serve_deep_debug():
    """Serve the deep debug interface."""
    from fastapi.responses import FileResponse
    import os
    
    deep_debug_path = os.path.join(os.path.dirname(__file__), "static", "deepdebug.html")
    if os.path.isfile(deep_debug_path):
        return FileResponse(deep_debug_path)
    else:
        return JSONResponse({
            "error": "Deep debug interface not found",
            "path": deep_debug_path
        }, status_code=404)



@deep_debug_router.post("/deepdebug/clear-history")
async def clear_history():
    """Clear conversation and user persona history."""
    global conversation_history, user_persona_history
    conversation_history = []
    user_persona_history = []
    return JSONResponse({
        "status": "success",
        "message": "History cleared"
    }) 