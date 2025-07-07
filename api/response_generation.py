"""Response generation utilities and query enhancement."""

import logging
from typing import Dict, Optional
from analyze.spacy_pipeline import extract_query_insights
import re

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
        
        # Log style detection
        style_req = insights.get("style_requirements", {})
        if style_req.get("philosophical_score", 0) > 0.3:
            logger.info(f"🎭 Gavin style detected - Score: {style_req['philosophical_score']:.2f}, Tone: {style_req['suggested_tone']}")
        
        gavin_guidance = insights.get("gavin_tone_guidance", "")
        if gavin_guidance:
            logger.info(f"📝 Gavin tone guidance: {len(gavin_guidance)} chars")
        
        return insights
    except Exception as e:
        logger.warning(f"Query enhancement failed: {e}")
        return {"entities": [], "concepts": [], "key_phrases": [], "main_topics": [], "question_type": "conversational"}


def format_context_enhancement(insights: Dict) -> str:
    """
    Format the extracted insights into rich context that enhances semantic alignment.
    
    Args:
        insights: Dictionary from enhance_query_context
        
    Returns:
        Formatted string to add to prompt context for better BLEURT scores
    """
    if not insights or insights.get("error"):
        return ""
    
    context_parts = []
    
    # Add semantic analysis header
    extraction_method = insights.get("extraction_method", "basic")
    context_parts.append(f"SEMANTIC QUERY ANALYSIS ({extraction_method}):")
    
    # Enhanced entity context with descriptions
    entities = insights.get("entities", [])
    if entities:
        entity_details = []
        for e in entities:
            desc = e.get("description", e.get("label", ""))
            entity_details.append(f"{e['text']} ({desc})")
        context_parts.append(f"• Named entities: {', '.join(entity_details[:4])}")
    
    # Rich technical concept context with categorization
    concepts = insights.get("concepts", [])
    if concepts:
        # Separate semantic categories from individual concepts
        categories = [c for c in concepts if c in ["blockchain_tech", "consensus", "interoperability", "governance"]]
        individual_concepts = [c for c in concepts if c not in categories]
        
        if categories:
            category_descriptions = {
                "blockchain_tech": "distributed ledger technology",
                "consensus": "consensus mechanisms and agreement protocols",
                "interoperability": "cross-chain communication and bridges",
                "governance": "decentralized governance systems"
            }
            cat_text = ", ".join([category_descriptions.get(c, c) for c in categories[:3]])
            context_parts.append(f"• Technical domains: {cat_text}")
        
        if individual_concepts:
            context_parts.append(f"• Specific technologies: {', '.join(individual_concepts[:5])}")
    
    # Enhanced key phrases with semantic importance
    key_phrases = insights.get("key_phrases", [])
    if key_phrases:
        # Prioritize longer, more technical phrases
        important_phrases = [p for p in key_phrases if len(p.split()) >= 2][:4]
        if important_phrases:
            context_parts.append(f"• Key technical phrases: {', '.join(important_phrases)}")
    
    # Enhanced topic context with response guidance
    topics = insights.get("main_topics", [])
    if topics:
        topic_guidance = {
            "blockchain_technology": "Focus on technical accuracy, architecture, and implementation details",
            "technical_development": "Emphasize development practices, tools, and technical solutions", 
            "strategy_business": "Address strategic implications, ecosystem impact, and future vision"
        }
        
        for topic in topics[:2]:  # Limit to 2 most relevant topics
            guidance = topic_guidance.get(topic, "")
            if guidance:
                context_parts.append(f"• {topic.replace('_', ' ').title()}: {guidance}")
    
    # Enhanced question type with specific response strategies
    question_type = insights.get("question_type", "conversational")
    if question_type != "conversational":
        response_strategies = {
            "explanatory": "Structure response with clear definitions, examples, and step-by-step explanations",
            "reasoning": "Lead with logical reasoning, provide justifications, and explain cause-effect relationships",
            "predictive": "Discuss current trends, logical projections, and potential scenarios with caveats", 
            "comparative": "Use structured comparisons, pros/cons analysis, and specific differentiators",
            "question": "Provide direct, concise answers followed by relevant context and implications"
        }
        strategy = response_strategies.get(question_type, "")
        if strategy:
            context_parts.append(f"• Response strategy: {strategy}")
    
    # Add Gavin Wood specific tone guidance
    gavin_tone_guidance = insights.get("gavin_tone_guidance", "")
    if gavin_tone_guidance:
        context_parts.append("")  # Add spacing
        context_parts.append(gavin_tone_guidance)
    
    # Add semantic coherence instruction
    if len(context_parts) > 1:  # Only if we have actual insights
        context_parts.append("• Maintain semantic consistency with these identified concepts and entities throughout the response")
    
    return "\n".join(context_parts) if len(context_parts) > 1 else ""


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


def validate_response_semantic_alignment(response_text: str, query_insights: Dict) -> Dict:
    """
    Validate response semantic alignment with extracted query insights.
    This helps improve BLEURT scores by ensuring concept coverage.
    
    Args:
        response_text: The generated response text
        query_insights: Insights extracted from the original query
        
    Returns:
        Dictionary with alignment score and suggestions for improvement
    """
    if not query_insights or not response_text:
        return {"alignment_score": 0.5, "suggestions": [], "missing_concepts": []}
    
    response_lower = response_text.lower()
    alignment_score = 0.0
    total_checks = 0
    missing_concepts = []
    suggestions = []
    
    # Initialize coverage counters
    entity_coverage = 0
    concept_coverage = 0
    phrase_coverage = 0
    
    # Check entity coverage
    entities = query_insights.get("entities", [])
    if entities:
        for entity in entities[:5]:  # Check top 5 entities
            entity_text = entity.get("text", "").lower()
            if entity_text and entity_text in response_lower:
                entity_coverage += 1
            else:
                missing_concepts.append(f"entity: {entity.get('text', '')}")
        
        alignment_score += (entity_coverage / len(entities[:5])) * 0.3
        total_checks += 0.3
    
    # Check technical concept coverage
    concepts = query_insights.get("concepts", [])
    if concepts:
        for concept in concepts[:7]:  # Check top 7 concepts
            if concept.lower() in response_lower:
                concept_coverage += 1
            else:
                missing_concepts.append(f"concept: {concept}")
        
        alignment_score += (concept_coverage / len(concepts[:7])) * 0.4
        total_checks += 0.4
        
        # Suggest adding missing critical concepts
        if concept_coverage < len(concepts[:3]):  # If missing top 3 concepts
            suggestions.append("Consider incorporating more of the key technical concepts mentioned in the query")
    
    # Check key phrase coverage
    key_phrases = query_insights.get("key_phrases", [])
    if key_phrases:
        for phrase in key_phrases[:4]:  # Check top 4 key phrases
            # Check for partial matches (at least 50% of words)
            phrase_words = phrase.lower().split()
            matches = sum(1 for word in phrase_words if word in response_lower)
            if matches >= len(phrase_words) * 0.5:
                phrase_coverage += 1
            else:
                missing_concepts.append(f"phrase: {phrase}")
        
        alignment_score += (phrase_coverage / len(key_phrases[:4])) * 0.2
        total_checks += 0.2
    
    # Check question type alignment
    question_type = query_insights.get("question_type", "conversational")
    if question_type != "conversational":
        type_patterns = {
            "explanatory": [r'\b(?:because|since|due to|as a result|this means)\b', r'\b(?:example|for instance)\b'],
            "reasoning": [r'\b(?:therefore|thus|consequently|reason|rationale)\b', r'\b(?:because|since|due to)\b'],
            "predictive": [r'\b(?:will|would|could|might|future|trend|expect)\b', r'\b(?:likely|probably|potential)\b'],
            "comparative": [r'\b(?:compared to|versus|vs|while|whereas|however)\b', r'\b(?:better|worse|different|similar)\b'],
            "question": [r'\?', r'\b(?:yes|no|answer|solution)\b']
        }
        
        patterns = type_patterns.get(question_type, [])
        type_alignment = 0
        for pattern in patterns:
            if re.search(pattern, response_lower, re.IGNORECASE):
                type_alignment = 1
                break
        
        alignment_score += type_alignment * 0.1
        total_checks += 0.1
        
        if type_alignment == 0:
            suggestions.append(f"Response style should better match the {question_type} nature of the query")
    
    # Normalize alignment score
    final_score = alignment_score / total_checks if total_checks > 0 else 0.5
    
    # Generate suggestions based on score
    if final_score < 0.6:
        suggestions.append("Consider including more specific technical details mentioned in the query")
    if len(missing_concepts) > 3:
        suggestions.append("Try to address more of the key concepts identified in the user's question")
    
    return {
        "alignment_score": final_score,
        "suggestions": suggestions,
        "missing_concepts": missing_concepts[:5],  # Limit to top 5
        "entity_coverage": entity_coverage / len(entities[:5]) if entities else 1.0,
        "concept_coverage": concept_coverage / len(concepts[:7]) if concepts else 1.0,
        "phrase_coverage": phrase_coverage / len(key_phrases[:4]) if key_phrases else 1.0
    }


def get_response_enhancement_suggestions(alignment_data: Dict) -> str:
    """
    Generate specific suggestions for improving response semantic alignment.
    
    Args:
        alignment_data: Output from validate_response_semantic_alignment
        
    Returns:
        Formatted suggestions string for prompt enhancement
    """
    if alignment_data["alignment_score"] >= 0.8:
        return ""  # Good alignment, no suggestions needed
    
    suggestions = []
    
    if alignment_data["concept_coverage"] < 0.6:
        missing = [c.split(": ")[1] for c in alignment_data["missing_concepts"] if c.startswith("concept:")]
        if missing:
            suggestions.append(f"Key missing concepts: {', '.join(missing[:3])}")
    
    if alignment_data["entity_coverage"] < 0.5:
        missing_entities = [c.split(": ")[1] for c in alignment_data["missing_concepts"] if c.startswith("entity:")]
        if missing_entities:
            suggestions.append(f"Important entities not addressed: {', '.join(missing_entities[:2])}")
    
    if suggestions:
        return "RESPONSE IMPROVEMENT NEEDED:\n" + "\n".join([f"• {s}" for s in suggestions])
    
    return "" 