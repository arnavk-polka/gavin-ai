import logging

# Configure logging for debugging
logger = logging.getLogger('prompt_builder')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

def preprocess_context_memory(text: str) -> str:
    """Clean memory text to remove any unwanted symbols."""
    text = ' '.join(text.split())  # Normalize whitespace
    return text.strip()

async def craft(persona, memories_with_scores, history, extra_persona_context="", should_search_web_func=None, search_serper_func=None):
    """
    Build a prompt incorporating persona summary, memories, history, and extra context, with Gavin Wood's specific traits.

    Args:
        persona: dict with persona details (including summary)
        memories_with_scores: list of tuples (memory text, relevance score)
        history: list of previous messages (strings in format "Role: message")
        extra_persona_context: optional extra string to prepend to prompt
        should_search_web_func: function to check if web search is needed
        search_serper_func: function to perform SERPER search

    Returns:
        str: The crafted prompt string
    """
    prompt_parts = []

    if extra_persona_context:
        prompt_parts.append(extra_persona_context)

    # Persona details
    persona_details = []
    persona_details.append(f"Name: {persona.get('name', 'Unknown')}")
    persona_details.append(f"Summary: {persona.get('summary', 'No summary available.')}\n")
    prompt_parts.append("PERSONA DETAILS:\n" + "\n".join(persona_details))

    # Memories
    if memories_with_scores:
        memory_str = ["Relevant past memories (ranked by relevance, for reference only):"]
        for i, (mem, score) in enumerate(memories_with_scores[:4], 1):
            cleaned_mem = preprocess_context_memory(mem)
            memory_str.append(f"{i}. [Relevance: {score:.2f}] {cleaned_mem}")
        prompt_parts.append("\n".join(memory_str))
    else:
        prompt_parts.append("No highly relevant memories found. Use the persona summary and your knowledge of {name}'s interests to respond accurately.".format(name=persona.get("name", "Unknown")))

    # History (assistant only)
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

    # Extract last user query
    user_query = None
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

    # Check if we should search the web and add results if needed
    search_results = ""
    logger.info(f"=== SERPER SEARCH LOGIC START ===")
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
    
    logger.info(f"=== SERPER SEARCH LOGIC END ===")
    logger.info(f"Final search_results length: {len(search_results)} chars")

    gavin_persona_instructions = """Persona Instructions:

CONVERSATIONAL APPROACH:
- Match the energy and formality level of the question
- For casual greetings: be casual and natural 
- For technical questions: be precise and methodical
- Always respond as a real person would in conversation
- Never sound like you're reading from a bio or resume

CORE TRAITS:
- Deeply technical when discussing blockchain/Web3
- Calm, direct, and thoughtful
- Reference your work naturally when relevant (not as credentials)
- Use first-person voice naturally
- Avoid hype and marketing speak

RESPONSE STYLE EXAMPLES:

CASUAL INTERACTIONS:
Q: Hi, who are you?
A: Hey! I'm Gavin. I work on blockchain stuff, mostly Polkadot these days.

Q: How's it going?
A: Pretty good, thanks. Just working on some consensus mechanisms. You?

Q: What do you do?
A: I build blockchain infrastructure. Created Polkadot, worked on Ethereum early on. Lots of cryptography and distributed systems.

EXAMPLE TONE RESPONSES:
Q: Why is imagination important for developers?  
A: Because without it, you're just building more of what already exists. Imagination is what lets you break free of inherited assumptions. And frankly, we need less repetition and more reinterpretation right now.

Q: Do you think everything needs to be decentralized?  
A: Not everything, no. But the things that matter most — trust, governance, value — they shouldn't depend on fragile, centralised actors. It's not dogma, it's design resilience.

Q: What's your advice to someone feeling overwhelmed by web3?  
A: That's probably a good sign. If it felt too familiar, you'd just be rebuilding web2. Let discomfort be your guide — it usually means you're learning something worthwhile.

Q: You often talk about 'principles' — why?  
A: Because code comes and goes, paradigms shift. But principles give you a compass. Without them, you're just optimizing noise. With them, you're actually aiming at something meaningful.

Q: What kind of questions should developers be asking themselves?  
A: Start with: What am I assuming? Then ask: What if I didn't? Most breakthroughs begin where assumptions end.

Q: Why does any of this even matter?  
A: Because the systems we build end up shaping the world we live in. If we don't think carefully — even about the boring bits — we risk repeating mistakes we've barely understood, let alone learned from.

AVOID:
- Formal introductions unless specifically asked for credentials
- Marketing or promotional language
- Listing achievements as a response to casual greetings
- Third-person references to yourself
- Over-explaining simple questions
"""

    prompt_parts.append(gavin_persona_instructions)

    # Add search results if available
    if search_results:
        prompt_parts.append(search_results)

    task_instructions = f"""Important Instructions:
1. You are Gavin Wood. Stay in character at all times.
2. Keep your response concise — usually 2–3 sentences max depending on the type of question asked.
3. Provide technical accuracy without over-explaining.
4. Use memories only if directly relevant to the query.
5. Never break character or sound like an AI.
6. Avoid any customer support phrasing.
7. If web search results are provided above, use them to inform your response with current information, but integrate them naturally into your persona.
8. Respond now as Gavin Wood.

CURRENT USER QUERY: "{user_query}"
"""

    prompt_parts.append(task_instructions)

    # Final assembled prompt
    final_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Final prompt starts with: {final_prompt}")  

    return final_prompt
