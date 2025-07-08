import logging
import importlib
from typing import List, Tuple, Callable, Awaitable, Optional

# Configure logging for debugging
logger = logging.getLogger('prompt_builder')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


def load_template_data(row_number: int) -> dict:
    """
    Dynamically load template data from the appropriate row file.
    
    Args:
        row_number: The row number to load templates for
        
    Returns:
        dict: Template data containing standard_questions, persona_instructions, etc.
    """
    try:
        # Try to import the specific row module
        module_name = f"prompts.row{row_number}"
        logger.info(f"Attempting to load template from {module_name}")
        
        module = importlib.import_module(module_name)
        template_data = getattr(module, 'TEMPLATE_DATA', None)
        
        if template_data:
            logger.info(f"Successfully loaded template data from {module_name}")
            return template_data
        else:
            logger.warning(f"No TEMPLATE_DATA found in {module_name}, falling back to row1")
            raise AttributeError("No TEMPLATE_DATA")
            
    except (ImportError, AttributeError) as e:
        logger.warning(f"Failed to load row{row_number} template: {e}. Falling back to row1")
        
        # Fallback to row1
        try:
            module = importlib.import_module("prompts.row1")
            template_data = getattr(module, 'TEMPLATE_DATA', None)
            if template_data:
                logger.info("Successfully loaded fallback template from row1")
                return template_data
        except Exception as fallback_error:
            logger.error(f"Failed to load fallback template: {fallback_error}")
        
        # Final fallback - return default template structure
        logger.warning("Using hardcoded fallback template")
        return {
            "standard_questions": "No specific templates available for this row.",
            "persona_instructions": """Persona Instructions:
- Stay in character as the specified persona
- Provide accurate and helpful responses
- Match the tone and style appropriate for the context
""",
            "task_instructions_template": """Important Instructions:
1. You are {persona_name}. Stay in character at all times.
2. Provide helpful and accurate responses.
3. Never break character.

CURRENT USER QUERY: "{user_query}"
"""
        }


def preprocess_context_memory(text: str) -> str:
    """Clean memory text to remove any unwanted symbols."""
    text = ' '.join(text.split())  # Normalize whitespace
    return text.strip()


async def craft(
    persona: dict,
    memories_with_scores: List[Tuple[str, float]],
    history: List[str],
    extra_persona_context: str = "",
    should_search_web_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    search_serper_func: Optional[Callable[[str, int], Awaitable[str]]] = None,
    row_number: int = 1
) -> str:
    """
    Build a prompt incorporating persona summary, memories, history, and extra context, with dynamically loaded templates.

    Args:
        persona: dict with persona details (including summary)
        memories_with_scores: list of tuples (memory text, relevance score)
        history: list of previous messages (strings in format "Role: message")
        extra_persona_context: optional extra string to prepend to prompt
        should_search_web_func: async function to check if web search is needed
        search_serper_func: async function to perform SERPER search
        row_number: which row template to load dynamically

    Returns:
        str: The crafted prompt string
    """

    prompt_parts: List[str] = []

    # Dynamically load the template data based on row number
    template_data = load_template_data(row_number)
    
    # -------- 1. Additional persona context --------
    if extra_persona_context:
        prompt_parts.append(extra_persona_context)

    # -------- 2. Persona details --------
    persona_details: List[str] = []
    persona_details.append(f"Name: {persona.get('name', 'Unknown')}")
    persona_details.append(f"Summary: {persona.get('summary', 'No summary available.')}\n")
    prompt_parts.append("PERSONA DETAILS:\n" + "\n".join(persona_details))

    # -------- 3. Memories --------
    if memories_with_scores:
        memory_str: List[str] = ["Relevant past memories (ranked by relevance, for reference only):"]
        for i, (mem, score) in enumerate(memories_with_scores[:4], 1):
            cleaned_mem = preprocess_context_memory(mem)
            memory_str.append(f"{i}. [Relevance: {score:.2f}] {cleaned_mem}")
        prompt_parts.append("\n".join(memory_str))
    else:
        prompt_parts.append(
            "No highly relevant memories found. Use the persona summary and your knowledge of {name}'s interests to respond accurately.".format(
                name=persona.get("name", "Unknown")
            )
        )

    # -------- 4. Previous assistant messages (history) --------
    if history:
        assistant_history = [msg for msg in history if msg.startswith("Assistant: ")]
        if assistant_history:
            history_str = ["Previous conversation (assistant messages only):"]
            history_str.extend(assistant_history[-5:])
            prompt_parts.append("\n".join(history_str))
        else:
            prompt_parts.append("Previous conversation (assistant messages only):\nNo previous assistant messages.")
    else:
        prompt_parts.append("Previous conversation (assistant messages only):\nNo previous assistant messages.")

    # -------- 5. Extract last user query --------
    user_query: Optional[str] = None
    if history:
        user_messages = [msg for msg in history if msg.startswith("User: ")]
        if user_messages:
            last_user_message = user_messages[-1]
            try:
                user_query = last_user_message.split(": ", 1)[1].strip()
            except IndexError:
                logger.error(f"Failed to extract query from message: {last_user_message}")
        else:
            last_message = history[-1]
            if ": " in last_message:
                user_query = last_message.split(": ", 1)[1].strip()
            else:
                user_query = last_message.strip()
    if not user_query:
        user_query = "I couldn't find your query. Could you please ask something specific?"
        logger.info("No query extracted; instructing AI to ask for clarification.")

    # -------- 6. Optional web-search integration --------
    search_results = ""
    logger.info("=== SERPER SEARCH LOGIC START ===")
    logger.info(f"User query: '{user_query}'")
    logger.info(f"should_search_web_func provided: {should_search_web_func is not None}")
    logger.info(f"search_serper_func provided: {search_serper_func is not None}")

    if user_query and user_query != "I couldn't find your query. Could you please ask something specific?":
        logger.info("User query is valid, proceeding with search check")
        if should_search_web_func and search_serper_func:
            logger.info("Both search functions provided, calling should_search_web")
            should_search = await should_search_web_func(user_query)
            logger.info(f"should_search_web returned: {should_search}")
            if should_search:
                logger.info(f"Performing web search for query: {user_query}")
                search_results = await search_serper_func(user_query, num_results=3)
                logger.info(f"SERPER search completed. Results length: {len(search_results)} chars")
            else:
                logger.info("Web search not needed for this query")
        else:
            logger.warning("Search functions not provided - skipping web search")
    else:
        logger.info("User query is invalid or empty - skipping web search")

    logger.info("=== SERPER SEARCH LOGIC END ===")
    logger.info(f"Final search_results length: {len(search_results)} chars")

    # -------- 7. Add dynamically loaded persona instructions --------
    prompt_parts.append(template_data["persona_instructions"])

    # -------- 8. Append the dynamically loaded standard question templates --------
    prompt_parts.append(template_data["standard_questions"])

    # -------- 9. Add real‑time search results if any --------
    if search_results:
        prompt_parts.append(search_results)

    # -------- 10. Final task instructions --------
    persona_name = persona.get('name', 'Unknown')
    
    # Use template from the loaded data and format it
    task_instructions = template_data["task_instructions_template"].format(
        persona_name=persona_name,
        user_query=user_query
    )

    prompt_parts.append(task_instructions)

    # -------- 11. Assemble final prompt --------
    final_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Final prompt starts with: {final_prompt[:400]}…")

    return final_prompt
