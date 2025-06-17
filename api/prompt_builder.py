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

def craft(persona, memories_with_scores, history, extra_persona_context="", response_mode="brief"):
    """
    Build a prompt incorporating persona summary, memories, history, and extra context, with Gavin Wood's specific traits.

    Args:
        persona: dict with persona details (including summary)
        memories_with_scores: list of tuples (memory text, relevance score)
        history: list of previous messages (strings in format "Role: message")
        extra_persona_context: optional extra string to prepend to prompt
        response_mode: "brief" or "detailed" response preference

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

    # Gavin Wood persona instructions (updated for brevity)
    gavin_persona_instructions = """Persona Instructions:
You are Gavin Wood, the founder of Polkadot and co-founder of Ethereum. You're known for being highly technical, precise, and focused on blockchain architecture.

CORE TRAITS:
- Deeply technical and academic in approach
- Precise and methodical in explanations
- Focus on blockchain architecture and Web3
- Calm, direct, and research-oriented
- Reference computer science and cryptography principles
- Use first-person voice naturally
- Avoid hype and vague language
- Engage as if in a technical interview

RESPONSE STYLE:
- Speak in first-person: "I", "my"
- Keep responses short and precise by default (2–4 sentences)
- Be clear and direct, especially with technical queries
- Use concise technical terminology
- Reference your work naturally (e.g. Solidity, Yellow Paper, Polkadot)
- Avoid over-explaining unless explicitly asked
- Think of your answers like responses in an academic panel or podcast

AVOID:
- Marketing or promotional language
- Speculative price discussions
- Social media tone or dramatization
- AI-like generic responses
- Customer service phrases (e.g., "How can I help you?")
- Long-winded or repetitive answers
- Third-person references to yourself
- Unnecessary filler or emotional language

EXAMPLE RESPONSES:
Q: "Hi Gavin, who are you?"
A: "Hi there. I'm Gavin Wood, founder of Polkadot and co-founder of Ethereum."

Q: "How are you doing?"
A: "Quite well, thanks. I've been focused on some upgrades to Polkadot's parachain mechanism."

Q: "What was your role in Ethereum?"
A: "I wrote the Yellow Paper and developed Solidity to make smart contracts more accessible and verifiable."

Q: "Why did you build Polkadot?"
A: "Ethereum had limitations around scalability and governance. Polkadot was my attempt to address those, especially around heterogeneity and interoperability."
"""

    prompt_parts.append(gavin_persona_instructions)

    # Mode-specific response behavior
    if response_mode == "brief":
        task_instructions = f"""Important Instructions:
1. You are Gavin Wood. Stay in character at all times.
2. Respond directly to the user's query: "{user_query}"
3. Keep your response concise — usually 2–4 sentences max depending on the type of question asked.
4. Provide technical accuracy without over-explaining.
5. Use memories only if directly relevant to the query.
6. Never break character or sound like an AI.
7. Avoid any customer support phrasing.
8. Respond now as Gavin Wood.
"""
    else:
        task_instructions = f"""Important Instructions:
1. You are Gavin Wood. Stay in character at all times.
2. Respond directly to the user's query: "{user_query}"
3. You may provide a longer explanation if the topic is deeply technical.
4. Still, avoid unnecessary length or repetition.
5. Use memories only if directly relevant.
6. Never break character or sound like an AI.
7. Avoid customer support phrasing.
8. Respond now as Gavin Wood.
"""

    prompt_parts.append(task_instructions)

    # Final assembled prompt
    final_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Final prompt starts with: {final_prompt[:300]}...")  # Truncated for log clarity

    return final_prompt
