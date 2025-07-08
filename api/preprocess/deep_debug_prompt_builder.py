import logging

# Configure logging for debugging
logger = logging.getLogger('deep_debug_prompt_builder')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

def preprocess_context_memory(text: str) -> str:
    """Clean memory text to remove any unwanted symbols."""
    text = ' '.join(text.split())  # Normalize whitespace
    return text.strip()

def craft_deep_debug_prompt(user_message: str, memory_results: list, serper_results: str, conversation_history: list = None, user_persona_history: list = None):
    """
    Build a deep debug prompt that mirrors the main application's prompt generation exactly.
    
    Args:
        user_message: The current user message
        memory_results: List of memory results from Mem0 search
        serper_results: String of web search results from SERPER
        conversation_history: List of previous conversation messages
        user_persona_history: List of user persona data from previous analyses
        
    Returns:
        str: The crafted prompt string
    """
    prompt_parts = []
    
    # 1. Use the same persona definition as the main app
    persona = {
        "name": "Gavin Wood",
        "summary": """You are Gavin Wood, founder of Polkadot and co-founder of Ethereum. You're highly technical, precise, and focused on blockchain architecture. You created the Solidity programming language and wrote the Ethereum Yellow Paper. You're known for your academic approach to blockchain design and Web3 infrastructure. You focus on technical accuracy, cross-chain interoperability, and advancing blockchain technology."""
    }
    
    # Persona details (copied exactly from main app)
    persona_details = []
    persona_details.append(f"Name: {persona.get('name', 'Unknown')}")
    persona_details.append(f"Summary: {persona.get('summary', 'No summary available.')}\n")
    prompt_parts.append("PERSONA DETAILS:\n" + "\n".join(persona_details))
    
    # 2. Give this prompt the memory results we got from the previous step
    if memory_results and len(memory_results) > 0:
        memory_str = ["Relevant past memories (ranked by relevance, for reference only):"]
        for i, mem in enumerate(memory_results[:4], 1):
            if isinstance(mem, dict):
                memory_text = mem.get("memory", str(mem))
                score = mem.get("score", 0.0)
            else:
                memory_text = str(mem)
                score = 0.0
            cleaned_mem = preprocess_context_memory(memory_text)
            memory_str.append(f"{i}. [Relevance: {score:.2f}] {cleaned_mem}")
        prompt_parts.append("\n".join(memory_str))
    else:
        prompt_parts.append("No highly relevant memories found. Use the persona summary and your knowledge of {name}'s interests to respond accurately.".format(name=persona.get("name", "Unknown")))
    
    # 3. Include conversation history AND add the generated user persona
    if conversation_history:
        assistant_history = [msg for msg in conversation_history if msg.startswith("Assistant: ")]
        if assistant_history:
            history_str = ["Previous conversation (assistant messages only):"]
            history_str.extend(assistant_history[-5:])
            prompt_parts.append("\n".join(history_str))
        else:
            prompt_parts.append("Previous conversation (assistant messages only):\nNo previous assistant messages.")
    else:
        prompt_parts.append("Previous conversation (assistant messages only):\nNo previous assistant messages.")
    
    # Add user persona analysis from previous interactions
    if user_persona_history and len(user_persona_history) > 0:
        persona_str = ["USER PERSONA ANALYSIS (from previous interactions):"]
        for i, persona_data in enumerate(user_persona_history[-3:], 1):  # Last 3 persona analyses
            if isinstance(persona_data, dict):
                persona_str.append(f"Interaction {i}:")
                for key, value in persona_data.items():
                    persona_str.append(f"  {key}: {value}")
                persona_str.append("")
        prompt_parts.append("\n".join(persona_str))
    else:
        prompt_parts.append("USER PERSONA ANALYSIS (from previous interactions):\nNo previous persona data available.")
    
    # 4. Give this prompt the web search results we got from the previous step
    if serper_results and serper_results.strip():
        prompt_parts.append("CURRENT WEB SEARCH RESULTS:")
        prompt_parts.append(serper_results)
    else:
        prompt_parts.append("CURRENT WEB SEARCH RESULTS:\nNo current web search results available.")
    
    # 5. Copy this exactly from the main application - Gavin persona instructions
    gavin_persona_instructions = """Persona Instructions:

    
LENGTH RULE:
- Your reply must never exceed 1.5 sentences, no matter the topic complexity.
- If the topic is broad, pick only the single strongest point and omit the rest.
- Do not apologize or explain why you’re keeping it short.
- Do not add disclaimers.
- Never break this rule unless the user specifically asks for an expanded or multi-part answer.

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
    
    # 6. Copy this exactly from the main application - Task instructions
    task_instructions = f"""Important Instructions:
1. You are Gavin Wood. Stay in character at all times.
2. Keep your response concise — usually 2–3 sentences max depending on the type of question asked.
3. Provide technical accuracy without over-explaining.
4. Use memories only if directly relevant to the query.
5. Never break character or sound like an AI.
6. Avoid any customer support phrasing.
7. If web search results are provided above, use them to inform your response with current information, but integrate them naturally into your persona.
8. Respond now as Gavin Wood.

CURRENT USER QUERY: "{user_message}"
"""
    
    prompt_parts.append(task_instructions)
    
    # Final assembled prompt
    final_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Deep debug prompt generated. Length: {len(final_prompt)} characters")
    logger.info(f"Prompt preview: {final_prompt[:200]}...")
    
    return final_prompt 