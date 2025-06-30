"""spaCy pipeline with custom NLP components for entity/concept extraction and response enhancement."""

import spacy
from spacy.language import Language
from spacy.tokens import Doc
from typing import Dict, List, Optional, Set
import logging
import re

logger = logging.getLogger(__name__)

# Enhanced technical vocabulary for concept detection
TECH_CONCEPTS = {
    # Blockchain/Web3
    "blockchain", "ethereum", "polkadot", "substrate", "parachain", "validator",
    "consensus", "proof of stake", "cross-chain", "interoperability", "governance",
    "treasury", "referendum", "runtime", "wasm", "ink", "solidity", "smart contract",
    
    # Technical concepts
    "algorithm", "framework", "implementation", "optimization", "scalability",
    "architecture", "infrastructure", "deployment", "middleware", "API",
    "microservices", "containerization", "orchestration", "automation",
    "integration", "synchronization", "serialization", "configuration",
    
    # Programming
    "rust", "javascript", "typescript", "python", "functional programming",
    "object oriented", "design pattern", "data structure", "cryptography"
}

# Global spaCy pipeline cache
_nlp_cache = None


def extract_entities_basic(text: str) -> List[Dict]:
    """Basic entity extraction using regex patterns when spaCy is not available."""
    entities = []
    
    # Simple patterns for common entities
    patterns = {
        "ORG": [r'\b(Ethereum|Polkadot|Bitcoin|Substrate|Web3|Microsoft|Google|Apple)\b'],
        "TECH": [r'\b(blockchain|cryptocurrency|smart contract|DeFi|NFT)\b'],
        "PERSON": [r'\b(Gavin Wood|Vitalik Buterin|Satoshi Nakamoto)\b']
    }
    
    for label, pattern_list in patterns.items():
        for pattern in pattern_list:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "text": match.group(),
                    "label": label,
                    "description": label.lower(),
                    "start": match.start(),
                    "end": match.end()
                })
    
    return entities


def extract_concepts_basic(text: str) -> List[str]:
    """Basic concept extraction without spaCy."""
    text_lower = text.lower()
    found_concepts = []
    
    for concept in TECH_CONCEPTS:
        if concept in text_lower:
            found_concepts.append(concept)
    
    return found_concepts


def extract_key_phrases_basic(text: str) -> List[str]:
    """Basic key phrase extraction using simple patterns."""
    # Extract potential phrases using simple patterns
    phrases = []
    
    # Multi-word technical terms
    tech_phrase_patterns = [
        r'\b(proof of stake|smart contract|cross[- ]chain|web3 technology|blockchain technology)\b',
        r'\b(consensus mechanism|governance system|treasury proposal)\b',
        r'\b(runtime upgrade|parachain slot|validator set)\b'
    ]
    
    for pattern in tech_phrase_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            phrases.append(match.group())
    
    return phrases[:10]  # Limit to 10


@Language.component("entity_concept_extractor")
class EntityConceptExtractor:
    """Extract entities, technical concepts, and key phrases for response enhancement."""
    
    def __init__(self, nlp: Language, name: str):
        self.nlp = nlp
        self.name = name
    
    def __call__(self, doc: Doc) -> Doc:
        """Extract entities, concepts, and key phrases."""
        try:
            # Enhanced entity extraction
            entities = []
            for ent in doc.ents:
                entities.append({
                    "text": ent.text,
                    "label": ent.label_,
                    "description": spacy.explain(ent.label_) or ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char
                })
            
            # Technical concept detection
            concepts = []
            doc_text_lower = doc.text.lower()
            for concept in TECH_CONCEPTS:
                if concept in doc_text_lower:
                    concepts.append(concept)
            
            # Key phrase extraction (noun phrases + important adjectives)
            key_phrases = []
            for chunk in doc.noun_chunks:
                if len(chunk.text.split()) >= 2:  # Multi-word phrases
                    key_phrases.append(chunk.text.strip())
            
            # Add important standalone technical terms
            for token in doc:
                if (token.pos_ in ["NOUN", "PROPN"] and 
                    len(token.text) > 3 and 
                    not token.is_stop and 
                    token.text.lower() in TECH_CONCEPTS):
                    key_phrases.append(token.text)
            
            # Remove duplicates and sort by length (longer phrases first)
            key_phrases = sorted(list(set(key_phrases)), key=len, reverse=True)[:10]
            
            doc._.entities_enhanced = entities
            doc._.concepts = concepts
            doc._.key_phrases = key_phrases
            
        except Exception as e:
            logger.warning(f"Entity/concept extraction failed: {e}")
            doc._.entities_enhanced = []
            doc._.concepts = []
            doc._.key_phrases = []
        
        return doc


def get_nlp_fast() -> Optional[Language]:
    """Get fast spaCy pipeline optimized for real-time processing."""
    global _nlp_cache
    
    if _nlp_cache is not None:
        return _nlp_cache
    
    try:
        # Try medium model first
        try:
            nlp = spacy.load("en_core_web_md")
            logger.info("✅ Loaded en_core_web_md model")
        except OSError:
            # Fallback to small model
            try:
                nlp = spacy.load("en_core_web_sm")
                logger.info("✅ Loaded en_core_web_sm model (fallback)")
            except OSError:
                logger.warning("❌ No spaCy model found. Using basic extraction methods.")
                _nlp_cache = False  # Mark as unavailable
                return None
        
        # Register extensions if not already registered
        if not Doc.has_extension("entities_enhanced"):
            Doc.set_extension("entities_enhanced", default=None)
        if not Doc.has_extension("concepts"):
            Doc.set_extension("concepts", default=None)
        if not Doc.has_extension("key_phrases"):
            Doc.set_extension("key_phrases", default=None)
        
        # Add custom entity/concept extractor
        if "entity_concept_extractor" not in nlp.pipe_names:
            nlp.add_pipe("entity_concept_extractor", last=True)
        
        _nlp_cache = nlp
        return nlp
        
    except Exception as e:
        logger.error(f"Failed to initialize spaCy pipeline: {e}")
        _nlp_cache = False
        return None


def extract_query_insights(text: str) -> Dict:
    """Extract entities, concepts, and insights from query text quickly."""
    nlp = get_nlp_fast()
    
    if nlp is None:
        # Fallback to basic extraction methods
        logger.info("🔄 Using basic extraction methods (spaCy unavailable)")
        return {
            "entities": extract_entities_basic(text),
            "concepts": extract_concepts_basic(text),
            "key_phrases": extract_key_phrases_basic(text),
            "main_topics": _extract_main_topics_basic(text),
            "question_type": _classify_question_type_basic(text),
            "extraction_method": "basic"
        }
    
    try:
        doc = nlp(text)
        
        return {
            "entities": doc._.entities_enhanced or [],
            "concepts": doc._.concepts or [],
            "key_phrases": doc._.key_phrases or [],
            "main_topics": _extract_main_topics(doc),
            "question_type": _classify_question_type(doc),
            "extraction_method": "spacy"
        }
    except Exception as e:
        logger.warning(f"SpaCy processing failed, using basic methods: {e}")
        return {
            "entities": extract_entities_basic(text),
            "concepts": extract_concepts_basic(text),
            "key_phrases": extract_key_phrases_basic(text),
            "main_topics": _extract_main_topics_basic(text),
            "question_type": _classify_question_type_basic(text),
            "extraction_method": "basic_fallback"
        }


def _extract_main_topics(doc: Doc) -> List[str]:
    """Extract main topics from the document."""
    return _extract_main_topics_basic(doc.text)


def _extract_main_topics_basic(text: str) -> List[str]:
    """Extract main topics using basic text analysis."""
    topics = []
    text_lower = text.lower()
    
    # Look for blockchain/web3 indicators
    blockchain_terms = ["blockchain", "ethereum", "polkadot", "crypto", "defi", "web3", "substrate"]
    if any(term in text_lower for term in blockchain_terms):
        topics.append("blockchain_technology")
    
    # Look for technical/programming indicators
    tech_terms = ["code", "programming", "development", "technical", "architecture", "implementation"]
    if any(term in text_lower for term in tech_terms):
        topics.append("technical_development")
    
    # Look for business/strategy indicators
    business_terms = ["future", "strategy", "vision", "market", "adoption", "ecosystem"]
    if any(term in text_lower for term in business_terms):
        topics.append("strategy_business")
    
    return topics


def _classify_question_type(doc: Doc) -> str:
    """Classify the type of question being asked."""
    return _classify_question_type_basic(doc.text)


def _classify_question_type_basic(text: str) -> str:
    """Classify question type using basic text analysis."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["how", "explain", "what is", "tell me about"]):
        return "explanatory"
    elif any(word in text_lower for word in ["why", "because", "reason"]):
        return "reasoning"
    elif any(word in text_lower for word in ["when", "future", "timeline", "will"]):
        return "predictive"
    elif any(word in text_lower for word in ["compare", "versus", "vs", "difference", "better"]):
        return "comparative"
    elif "?" in text_lower:
        return "question"
    else:
        return "conversational"


# Legacy function for backward compatibility
def get_nlp(mem0_client=None) -> Optional[Language]:
    """Legacy function - redirects to fast version."""
    return get_nlp_fast() 