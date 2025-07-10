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


def extract_specific_template(standard_questions: str, template_number: int) -> str:
    """
    Extract a specific numbered template from the standard_questions text.
    
    Args:
        standard_questions: The full standard_questions text containing all templates
        template_number: The template number to extract (1-10)
        
    Returns:
        str: The extracted template text, or all templates if extraction fails
    """
    try:
        lines = standard_questions.split('\n')
        template_lines = []
        found_start = False
        next_template_pattern = f"{template_number + 1}."
        
        for line in lines:
            # Check if we found the start of our template
            if line.strip().startswith(f"{template_number}."):
                found_start = True
                template_lines.append(line)
                continue
                
            # If we found the start and hit the next template number, stop
            if found_start and line.strip().startswith(next_template_pattern):
                break
                
            # If we found the start and hit "Examples with real backfills", stop
            if found_start and "Examples with real backfills" in line:
                break
                
            # If we're collecting and this isn't an empty line at the start, add it
            if found_start:
                template_lines.append(line)
        
        if template_lines:
            # Clean up the extracted template
            result = '\n'.join(template_lines).strip()
            logger.info(f"Successfully extracted template {template_number}")
            return result
        else:
            logger.warning(f"Could not extract template {template_number}, using all templates")
            return standard_questions
            
    except Exception as e:
        logger.error(f"Error extracting template {template_number}: {e}")
        return standard_questions


def select_template_based_on_analysis(analysis_data: dict, row_number: int) -> int:
    """
    Select the most appropriate template number (1-10) based on preprocessing analysis data.
    
    Args:
        analysis_data: The analysis data from preprocessing containing intent, sentiment, emotion, etc.
        row_number: The selected row number (1-13)
        
    Returns:
        int: Template number (1-10) that best matches the analysis
    """
    try:
        # Extract key analysis fields
        intent_main = analysis_data.get("intent_main", "").lower()
        intent_secondary = analysis_data.get("intent_secondary", "").lower()
        sentiment_main = analysis_data.get("sentiment_main", "").lower()
        emotion = analysis_data.get("emotion", "").lower()
        tone = analysis_data.get("tone", "").lower()
        urgency = analysis_data.get("urgency", "").lower()
        topic = analysis_data.get("topic", "").lower()
        
        logger.info(f"Template selection for row {row_number}: intent='{intent_main}', sentiment='{sentiment_main}', emotion='{emotion}', tone='{tone}', urgency='{urgency}'")
        
        # Template selection logic based on common patterns across rows
        # This maps analysis characteristics to template positions
        
        # High urgency or direct questions -> templates 1-3 (direct, factual)
        if urgency in ["high", "urgent", "immediate"] or "urgent" in intent_main:
            return 1
            
        # Personal or anecdotal queries -> templates 8-9 (personal examples, anecdotes)
        if "personal" in intent_main or "personal" in topic or "anecdote" in intent_secondary:
            return 8
            
        # Advice-seeking or guidance -> templates 2, 6 (guidance patterns)
        if "advice" in intent_main or "guidance" in intent_main or "help" in intent_main:
            return 2
            
        # Skeptical or challenging tone -> templates 4, 9 (cautionary, counterpoint)
        if "skeptical" in emotion or "doubt" in emotion or "challenge" in intent_main:
            return 4
            
        # Future-oriented or speculative -> template 7 (future trends)
        if "future" in topic or "predict" in intent_main or "timeline" in intent_main:
            return 7
            
        # Enthusiastic or positive sentiment -> templates 3, 5 (energy redirection, positive examples)
        if sentiment_main in ["positive", "enthusiastic"] or emotion in ["excited", "enthusiastic", "curious"]:
            return 3
            
        # Technical or analytical -> templates 5, 6 (mental models, principles)
        if "technical" in topic or "analytical" in tone or "explain" in intent_main:
            return 5
            
        # Critique or negative sentiment -> templates 6, 9 (push back, critique)
        if sentiment_main in ["negative", "critical"] or "critique" in intent_main:
            return 6
            
        # Resource seeking or learning -> template 9 (resource pointers)
        if "learn" in intent_main or "resource" in intent_secondary or "study" in intent_main:
            return 9
            
        # Philosophical or open-ended -> template 10 (sign-off, principle-based)
        if "philosophy" in topic or "principle" in intent_main or "open" in tone:
            return 10
            
        # Default fallback based on row characteristics
        if row_number == 1:  # Standard Question - prefer factual templates
            return 1
        elif row_number == 2:  # Question + Implied Advice - prefer guidance templates  
            return 2
        elif row_number == 3:  # Enthusiastic Question - prefer energy management
            return 3
        elif row_number in [6, 7]:  # Critique rows - prefer direct response
            return 4
        elif row_number in [4, 13]:  # Technical rows - prefer analytical
            return 5
        else:
            # Balanced default for other rows
            return 3
            
    except Exception as e:
        logger.error(f"Error in template selection: {e}")
        return 1  # Safe fallback


async def craft(
    persona: dict,
    memories_with_scores: List[Tuple[str, float]],
    history: List[str],
    extra_persona_context: str = "",
    should_search_web_func: Optional[Callable[[str], Awaitable[bool]]] = None,
    search_serper_func: Optional[Callable[[str, int], Awaitable[str]]] = None,
    row_number: int = 1,
    template_number: Optional[int] = None
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
        template_number: which specific template to use from the row (1-10, optional)

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
    if template_number is not None and 1 <= template_number <= 10:
        # Extract the specific selected template
        selected_template = extract_specific_template(template_data["standard_questions"], template_number)
        
        # Create a formatted section with the selected template highlighted
        template_section = f"""SELECTED TEMPLATE TO USE:
Template #{template_number}:
{selected_template}

ALL AVAILABLE TEMPLATES (for reference):
{template_data["standard_questions"]}"""
        
        prompt_parts.append(template_section)
        logger.info(f"Using template {template_number} as primary from row {row_number}, with all templates for reference")
    else:
        # Otherwise, append all standard questions
        prompt_parts.append(template_data["standard_questions"])
        logger.info(f"Using all templates from row {row_number}")

    # -------- 9. Add real‑time search results if any --------
    if search_results:
        prompt_parts.append(search_results)

    # -------- 10. Final task instructions --------
    persona_name = persona.get('name', 'Unknown')
    
    # Use template from the loaded data and format it
    # Update task instructions based on whether a specific template was selected
    task_template = template_data["task_instructions_template"]
    if template_number is not None and 1 <= template_number <= 10:
        # Replace references to choosing templates with using the selected one
        task_template = task_template.replace(
            'choose **one** of the "Standard Question Response Templates" above',
            f'use the **SELECTED TEMPLATE #{template_number}** highlighted above. The other templates are provided for reference only'
        ).replace(
            'choose **one** of the "Question + Implied Advice Templates" above',
            f'use the **SELECTED TEMPLATE #{template_number}** highlighted above. The other templates are provided for reference only'
        ).replace(
            'choose **one** of the "Enthusiastic Question Templates" above',
            f'use the **SELECTED TEMPLATE #{template_number}** highlighted above. The other templates are provided for reference only'
        )
    
    task_instructions = task_template.format(
        persona_name=persona_name,
        user_query=user_query
    )

    prompt_parts.append(task_instructions)

    # -------- 11. Assemble final prompt --------
    final_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Final prompt starts with: {final_prompt[:400]}…")

    return final_prompt
