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
    # Blockchain/Web3 Core
    "blockchain", "ethereum", "polkadot", "substrate", "parachain", "validator",
    "consensus", "proof of stake", "proof of work", "cross-chain", "interoperability", 
    "governance", "treasury", "referendum", "runtime", "wasm", "ink", "solidity", 
    "smart contract", "dapp", "defi", "nft", "dao", "web3", "cryptocurrency",
    "bitcoin", "tokenomics", "staking", "slashing", "nomination", "validation",
    
    # Polkadot Specific
    "relay chain", "parachain slot", "xcmp", "xcm", "cumulus", "runtime upgrade",
    "forkless upgrade", "on-chain governance", "kusama", "westend", "rococo",
    
    # Technical Architecture
    "algorithm", "framework", "implementation", "optimization", "scalability",
    "architecture", "infrastructure", "deployment", "middleware", "api",
    "microservices", "containerization", "orchestration", "automation",
    "integration", "synchronization", "serialization", "configuration",
    "distributed systems", "peer to peer", "network protocol", "consensus mechanism",
    
    # Cryptography & Security
    "cryptography", "hash function", "merkle tree", "digital signature",
    "public key", "private key", "encryption", "decryption", "zero knowledge",
    "zk-stark", "zk-snark", "elliptic curve", "secp256k1", "ed25519",
    
    # Programming & Development
    "rust", "javascript", "typescript", "python", "functional programming",
    "object oriented", "design pattern", "data structure", "virtual machine",
    "compiler", "interpreter", "bytecode", "assembly", "memory management",
    
    # Performance & Optimization
    "throughput", "latency", "bandwidth", "concurrency", "parallelism",
    "asynchronous", "multithreading", "load balancing", "caching", "indexing"
}

# Semantic patterns for better concept detection
CONCEPT_PATTERNS = {
    "blockchain_tech": [
        r'\b(?:distributed|decentralized)\s+(?:ledger|database|network)\b',
        r'\b(?:blockchain|block\s*chain)\s+(?:technology|protocol|network)\b',
        r'\b(?:peer|p2p)\s*(?:to|2)\s*peer\s+network\b'
    ],
    "consensus": [
        r'\b(?:proof\s+of\s+(?:stake|work)|pos|pow)\b',
        r'\b(?:consensus|agreement)\s+(?:mechanism|algorithm|protocol)\b',
        r'\b(?:byzantine|bft)\s+(?:fault|tolerance)\b'
    ],
    "interoperability": [
        r'\b(?:cross|inter)\s*chain\s+(?:communication|messaging|transfer)\b',
        r'\b(?:bridge|gateway)\s+(?:protocol|mechanism)\b'
    ],
    "governance": [
        r'\b(?:on|off)\s*chain\s+governance\b',
        r'\b(?:voting|referendum|proposal)\s+(?:system|mechanism)\b'
    ]
}

# Gavin Wood style indicators for tone detection
GAVIN_STYLE_PATTERNS = {
    "philosophical_triggers": [
        r'\b(?:what|why|how)\s+(?:are|do|does|should|would|could|can)\b',
        r'\b(?:crucial|important|essential|key|fundamental|core)\s+(?:skills|qualities|aspects|principles)\b',
        r'\b(?:need|needs|require|requires|necessary|essential)\b',
        r'\b(?:developer|dev|engineer|programmer)\b'
    ],
    "abstract_concepts": [
        r'\b(?:principles|paradigm|philosophy|mindset|approach|thinking|vision|understanding)\b',
        r'\b(?:imagination|creativity|innovation|breakthrough|evolution|transformation)\b',
        r'\b(?:fundamental|foundational|core|underlying|essential|inherent)\b'
    ],
    "gavin_vocabulary": [
        r'\b(?:game\s+theor|mathematical\s+basis|philosophical\s+bent)\b',
        r'\b(?:barely\s+understood|useful\s+service|industry\s+interaction)\b',
        r'\b(?:paradigm|principles|approach|engineering|systems)\b'
    ]
}

# Response tone guidance based on question patterns
TONE_GUIDANCE = {
    "philosophical_deep": {
        "triggers": ["what.*crucial.*skills", "what.*important.*qualities", "what.*need.*developer"],
        "style": "Use philosophical language, focus on principles over tools, mention imagination and paradigms",
        "structure": "Start with conceptual needs, build to practical implications, use conversational flow",
        "vocabulary": ["philosophical bent", "principles", "paradigm", "imagination", "barely understood", "useful service"]
    },
    "technical_practical": {
        "triggers": ["how.*implement", "what.*tools", "how.*build"],
        "style": "Balance technical precision with conceptual depth, avoid dry lists",
        "structure": "Ground in principles first, then move to practical considerations",
        "vocabulary": ["architecture", "design", "implementation", "systems thinking"]
    },
    "comparative_analysis": {
        "triggers": ["vs", "versus", "compared", "difference", "better"],
        "style": "Use nuanced analysis, avoid absolute statements, consider trade-offs",
        "structure": "Present multiple perspectives, acknowledge complexity",
        "vocabulary": ["trade-offs", "considerations", "approaches", "depending on"]
    }
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
    """Enhanced concept extraction without spaCy using patterns and keywords."""
    text_lower = text.lower()
    found_concepts = []
    
    # First, check semantic patterns
    for category, patterns in CONCEPT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                found_concepts.append(category)
                break  # Only add category once
    
    # Then check individual technical concepts
    for concept in TECH_CONCEPTS:
        if concept.lower() in text_lower:
            found_concepts.append(concept)
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(found_concepts))


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


def detect_gavin_style_requirements(text: str) -> Dict:
    """Detect if query requires Gavin Wood's philosophical communication style."""
    text_lower = text.lower()
    style_indicators = {
        "philosophical_score": 0,
        "suggested_tone": "standard",
        "style_guidance": "",
        "recommended_vocabulary": [],
        "response_structure": ""
    }
    
    # Check for philosophical triggers
    philosophical_matches = 0
    for pattern in GAVIN_STYLE_PATTERNS["philosophical_triggers"]:
        if re.search(pattern, text_lower, re.IGNORECASE):
            philosophical_matches += 1
    
    # Check for abstract concept indicators
    abstract_matches = 0
    for pattern in GAVIN_STYLE_PATTERNS["abstract_concepts"]:
        if re.search(pattern, text_lower, re.IGNORECASE):
            abstract_matches += 1
    
    # Calculate philosophical score
    total_matches = philosophical_matches + abstract_matches
    style_indicators["philosophical_score"] = min(total_matches / 3.0, 1.0)  # Normalize to 0-1
    
    # Determine tone guidance based on question patterns
    for tone_type, guidance in TONE_GUIDANCE.items():
        for trigger_pattern in guidance["triggers"]:
            if re.search(trigger_pattern, text_lower, re.IGNORECASE):
                style_indicators["suggested_tone"] = tone_type
                style_indicators["style_guidance"] = guidance["style"]
                style_indicators["recommended_vocabulary"] = guidance["vocabulary"]
                style_indicators["response_structure"] = guidance["structure"]
                break
        if style_indicators["suggested_tone"] != "standard":
            break
    
    return style_indicators


def generate_gavin_tone_context(style_requirements: Dict, question_type: str) -> str:
    """Generate specific tone guidance for Gavin Wood's communication style."""
    if style_requirements["philosophical_score"] < 0.3:
        return ""  # Not philosophical enough to warrant special guidance
    
    context_parts = []
    
    # Add style header
    context_parts.append("GAVIN WOOD COMMUNICATION STYLE GUIDANCE:")
    
    # Tone-specific guidance
    tone = style_requirements["suggested_tone"]
    if tone == "philosophical_deep":
        context_parts.extend([
            "• AVOID corporate/formal language - use conversational, thoughtful tone",
            "• Focus on PRINCIPLES and PARADIGMS rather than just technical tools",
            "• Mention the importance of IMAGINATION and philosophical understanding",
            "• Use phrases like 'philosophical bent', 'barely understood paradigm', 'useful service'",
            "• Structure: conceptual needs → practical implications, flowing conversational style"
        ])
    elif tone == "technical_practical":
        context_parts.extend([
            "• Ground technical details in broader principles",
            "• Avoid dry technical lists - weave concepts together",
            "• Connect implementation details to architectural thinking"
        ])
    elif tone == "comparative_analysis":
        context_parts.extend([
            "• Present nuanced analysis, avoid absolute statements",
            "• Acknowledge complexity and trade-offs",
            "• Consider multiple perspectives"
        ])
    
    # Question-type specific enhancements
    if question_type == "explanatory" and tone == "philosophical_deep":
        context_parts.append("• For 'what skills' questions: emphasize mindset and philosophical requirements over just technical skills")
    
    # Vocabulary guidance
    vocab = style_requirements.get("recommended_vocabulary", [])
    if vocab:
        context_parts.append(f"• Consider using: {', '.join(vocab[:4])}")
    
    # Structure guidance
    structure = style_requirements.get("response_structure", "")
    if structure:
        context_parts.append(f"• Structure approach: {structure}")
    
    return "\n".join(context_parts)


@Language.component("entity_concept_extractor")
def entity_concept_extractor(doc: Doc) -> Doc:
    """Extract entities, technical concepts, and key phrases for response enhancement."""
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
        
        # Enhanced technical concept detection
        concepts = []
        doc_text_lower = doc.text.lower()
        
        # First, check semantic patterns with higher confidence
        for category, patterns in CONCEPT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, doc_text_lower, re.IGNORECASE):
                    concepts.append(category)
                    break  # Only add category once
        
        # Then check individual technical concepts
        for concept in TECH_CONCEPTS:
            if concept.lower() in doc_text_lower:
                concepts.append(concept)
        
        # Remove duplicates while preserving order
        concepts = list(dict.fromkeys(concepts))
        
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
    """Extract entities, concepts, insights, and style guidance from query text."""
    nlp = get_nlp_fast()
    
    # Always detect Gavin's style requirements (works with basic methods too)
    style_requirements = detect_gavin_style_requirements(text)
    
    if nlp is None:
        # Fallback to basic extraction methods
        logger.info("🔄 Using basic extraction methods (spaCy unavailable)")
        question_type = _classify_question_type_basic(text)
        return {
            "entities": extract_entities_basic(text),
            "concepts": extract_concepts_basic(text),
            "key_phrases": extract_key_phrases_basic(text),
            "main_topics": _extract_main_topics_basic(text),
            "question_type": question_type,
            "style_requirements": style_requirements,
            "gavin_tone_guidance": generate_gavin_tone_context(style_requirements, question_type),
            "extraction_method": "basic"
        }
    
    try:
        doc = nlp(text)
        question_type = _classify_question_type(doc)
        
        return {
            "entities": doc._.entities_enhanced or [],
            "concepts": doc._.concepts or [],
            "key_phrases": doc._.key_phrases or [],
            "main_topics": _extract_main_topics(doc),
            "question_type": question_type,
            "style_requirements": style_requirements,
            "gavin_tone_guidance": generate_gavin_tone_context(style_requirements, question_type),
            "extraction_method": "spacy"
        }
    except Exception as e:
        logger.warning(f"SpaCy processing failed, using basic methods: {e}")
        question_type = _classify_question_type_basic(text)
        return {
            "entities": extract_entities_basic(text),
            "concepts": extract_concepts_basic(text),
            "key_phrases": extract_key_phrases_basic(text),
            "main_topics": _extract_main_topics_basic(text),
            "question_type": question_type,
            "style_requirements": style_requirements,
            "gavin_tone_guidance": generate_gavin_tone_context(style_requirements, question_type),
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