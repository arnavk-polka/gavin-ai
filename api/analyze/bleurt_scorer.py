import logging
import warnings
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

class BLEURTScorer:
    """
    BLEURT scorer for evaluating text similarity using HuggingFace evaluate.
    Handles negative scores appropriately by normalizing them.
    """
    
    def __init__(self):
        self.scorer = None
        self._model_loaded = False
        self._use_sentence_transformer = False
        
    def _load_model(self):
        """Load BLEURT model only when needed."""
        if self._model_loaded:
            return
            
        try:
            logger.info("Loading BLEURT model via HuggingFace evaluate...")
            
            # Suppress warnings during model loading
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                logger.info("Importing evaluate library...")
                import evaluate
                
                logger.info("Initializing BLEURT scorer...")
                logger.info("About to call evaluate.load('bleurt', 'bleurt-tiny-128')...")
                
                # Load BLEURT via HuggingFace evaluate (using smallest model)
                # bleurt-tiny-128 is much smaller than others (~100MB vs 405MB+ for base)
                self.scorer = evaluate.load("bleurt", "bleurt-tiny-128")
                logger.info("BLEURT model loaded successfully")
                
            self._model_loaded = True
            logger.info("BLEURT initialization complete")
            
        except ImportError as e:
            logger.error(f"HuggingFace evaluate not available: {e}")
            logger.error("Please install: pip install evaluate")
            raise ImportError("HuggingFace evaluate not available. Please install with: pip install evaluate")
        except Exception as e:
            logger.error(f"Failed to load BLEURT model: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"BLEURT loading traceback: {traceback.format_exc()}")
            
            # Since model should be pre-downloaded, this is a serious error
            raise RuntimeError(f"BLEURT model failed to load. Model should be pre-downloaded during Docker build. Error: {e}")
    
    def compute_score(self, reference: str, candidate: str) -> float:
        """
        Compute BLEURT score between reference and candidate texts.
        
        Args:
            reference: The reference text (expected answer)
            candidate: The candidate text (bot response)
            
        Returns:
            Normalized BLEURT score between 0 and 1
        """
        if not self._model_loaded:
            self._load_model()
            
        try:
            if self._use_sentence_transformer:
                logger.debug("Computing SentenceTransformer similarity...")
                
                # Use SentenceTransformer cosine similarity
                ref_embedding = self.scorer.encode([reference])
                cand_embedding = self.scorer.encode([candidate])
                
                from sklearn.metrics.pairwise import cosine_similarity
                similarity = cosine_similarity(ref_embedding, cand_embedding)[0][0]
                
                # Cosine similarity is already 0-1 range
                score = max(0.0, min(1.0, similarity))
                
                logger.debug(f"SentenceTransformer similarity: {score:.3f}")
                return score
            else:
                logger.debug("Computing BLEURT score...")
                
                # Compute raw BLEURT score using HuggingFace evaluate
                result = self.scorer.compute(
                    predictions=[candidate],
                    references=[reference]
                )
                raw_score = result['scores'][0]
                
                # Normalize score to 0-1 range
                # BLEURT scores typically range from about -2 to +2
                # We'll map this to 0-1 using a sigmoid-like transformation
                normalized_score = self._normalize_score(raw_score)
                
                logger.debug(f"BLEURT raw score: {raw_score:.3f}, normalized: {normalized_score:.3f}")
                
                return normalized_score
            
        except Exception as e:
            logger.error(f"Error computing similarity score: {e}")
            # Return a default low score if computation fails
            return 0.1
    
    def batch_compute_scores(self, references: List[str], candidates: List[str]) -> List[float]:
        """
        Compute BLEURT scores for multiple reference-candidate pairs.
        
        Args:
            references: List of reference texts
            candidates: List of candidate texts
            
        Returns:
            List of normalized BLEURT scores
        """
        if not self._model_loaded:
            self._load_model()
            
        if len(references) != len(candidates):
            raise ValueError("References and candidates must have the same length")
            
        try:
            logger.debug(f"Computing BLEURT scores for {len(references)} pairs...")
            
            # Compute raw BLEURT scores using HuggingFace evaluate
            result = self.scorer.compute(
                predictions=candidates,
                references=references
            )
            raw_scores = result['scores']
            
            # Normalize all scores
            normalized_scores = [self._normalize_score(score) for score in raw_scores]
            
            logger.info(f"Computed BLEURT scores for {len(references)} pairs")
            logger.debug(f"Score range: {min(normalized_scores):.3f} - {max(normalized_scores):.3f}")
            
            return normalized_scores
            
        except Exception as e:
            logger.error(f"Error computing batch BLEURT scores: {e}")
            # Return default low scores if computation fails
            return [0.1] * len(references)
    
    def _normalize_score(self, raw_score: float) -> float:
        """
        Normalize BLEURT score to 0-1 range.
        
        BLEURT scores can be negative and typically range from about -2 to +2.
        We use a modified sigmoid function to map them to [0, 1].
        
        Args:
            raw_score: Raw BLEURT score
            
        Returns:
            Normalized score between 0 and 1
        """
        # Use a modified sigmoid transformation
        # This maps:
        # - Scores around 0 to 0.5
        # - Positive scores (good) to > 0.5
        # - Negative scores (poor) to < 0.5
        # - Very negative scores approach 0
        # - Very positive scores approach 1
        
        # Sigmoid with adjusted parameters for BLEURT range
        normalized = 1 / (1 + np.exp(-raw_score))
        
        # Ensure the score is in [0, 1] range
        normalized = max(0.0, min(1.0, normalized))
        
        return normalized
    
    def get_score_interpretation(self, normalized_score: float) -> str:
        """
        Get human-readable interpretation of the BLEURT score.
        
        Args:
            normalized_score: Normalized BLEURT score (0-1)
            
        Returns:
            Human-readable interpretation
        """
        if normalized_score >= 0.8:
            return "Excellent semantic similarity"
        elif normalized_score >= 0.7:
            return "Good semantic similarity"
        elif normalized_score >= 0.6:
            return "Moderate semantic similarity"
        elif normalized_score >= 0.4:
            return "Fair semantic similarity"
        elif normalized_score >= 0.2:
            return "Poor semantic similarity"
        else:
            return "Very poor semantic similarity"
    
    def is_model_loaded(self) -> bool:
        """Check if the BLEURT model is loaded."""
        return self._model_loaded 