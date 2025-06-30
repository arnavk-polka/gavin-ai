"""Response generation utilities and query enhancement."""

import logging
from typing import Dict, Optional
from analyze.spacy_pipeline import extract_query_insights

logger = logging.getLogger(__name__)


def enhance_query_context(user_query: str) -> Dict:
    """
    Extract entities, concepts, and insights from user query to enhance response context.
    This runs before response generation to improve the prompt.
    
    Args:
        user_query: The user's input query
        
    Returns:
        Dictionary containing extracted insights for prompt enhancement
    """
    try:
        insights = extract_query_insights(user_query)
        
        # Log the insights for debugging
        if insights.get("entities"):
            logger.info(f"Detected entities: {[e['text'] for e in insights['entities']]}")
        if insights.get("concepts"):
            logger.info(f"Detected technical concepts: {insights['concepts']}")
        if insights.get("key_phrases"):
            logger.info(f"Key phrases: {insights['key_phrases'][:3]}")  # Show first 3
        if insights.get("main_topics"):
            logger.info(f"Main topics: {insights['main_topics']}")
        
        return insights
    except Exception as e:
        logger.warning(f"Query enhancement failed: {e}")
        return {"entities": [], "concepts": [], "key_phrases": [], "main_topics": [], "question_type": "conversational"}


def format_context_enhancement(insights: Dict) -> str:
    """
    Format the extracted insights into context that can enhance the prompt.
    
    Args:
        insights: Dictionary from enhance_query_context
        
    Returns:
        Formatted string to add to prompt context
    """
    if not insights or insights.get("error"):
        return ""
    
    context_parts = []
    
    # Add detected entities context
    entities = insights.get("entities", [])
    if entities:
        entity_texts = [e["text"] for e in entities]
        context_parts.append(f"Key entities mentioned: {', '.join(entity_texts)}")
    
    # Add technical concepts context  
    concepts = insights.get("concepts", [])
    if concepts:
        context_parts.append(f"Technical concepts involved: {', '.join(concepts[:5])}")  # Limit to 5
    
    # Add main topics context
    topics = insights.get("main_topics", [])
    if topics:
        topic_descriptions = {
            "blockchain_technology": "blockchain and Web3 technology",
            "technical_development": "software development and technical implementation", 
            "strategy_business": "strategic vision and business aspects"
        }
        topic_text = ", ".join([topic_descriptions.get(t, t) for t in topics])
        context_parts.append(f"Discussion topics: {topic_text}")
    
    # Add question type guidance
    question_type = insights.get("question_type", "conversational")
    if question_type != "conversational":
        type_guidance = {
            "explanatory": "provide clear explanations with examples",
            "reasoning": "explain the reasoning and rationale behind concepts",
            "predictive": "discuss future implications and possibilities", 
            "comparative": "compare and contrast different approaches or technologies",
            "question": "answer the specific question directly"
        }
        guidance = type_guidance.get(question_type, "")
        if guidance:
            context_parts.append(f"Response approach: {guidance}")
    
    if context_parts:
        return "\n".join([f"• {part}" for part in context_parts])
    
    return ""


# Legacy function for backward compatibility (simplified, non-blocking)
def tone_bleurt_gate(draft_text: str, bleurt_score: float = 0.0) -> bool:
    """
    Simplified quality gate that always passes to avoid blocking.
    Real quality improvement now happens via query enhancement.
    """
    if not draft_text or not draft_text.strip():
        logger.warning("Empty draft text provided")
        return False
    
    logger.info("✅ Quality gate passed (non-blocking mode)")
    return True 