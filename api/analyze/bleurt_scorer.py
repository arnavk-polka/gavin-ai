import logging
import warnings
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

class BLEURTScorer:
    """
    BLEURT scorer for evaluating text similarity using HuggingFace evaluate.
    Returns raw BLEURT scores without normalization (range typically -2 to +2).
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
                logger.info("About to call evaluate.load('bleurt', 'bleurt-base-128')...")
                
                # Load BLEURT via HuggingFace evaluate (using smaller model)
                # bleurt-base-128 is much smaller than bleurt-20 (500MB vs 2.14GB)
                self.scorer = evaluate.load("bleurt", "bleurt-base-128")
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
            
            # Fallback to sentence transformer similarity
            logger.warning("BLEURT failed, falling back to SentenceTransformer semantic similarity...")
            try:
                from sentence_transformers import SentenceTransformer
                from sklearn.metrics.pairwise import cosine_similarity
                
                self.scorer = SentenceTransformer('all-MiniLM-L6-v2')  # Small, fast model
                self._use_sentence_transformer = True
                self._model_loaded = True
                logger.info("Fallback to SentenceTransformer successful")
                return
            except Exception as fallback_e:
                logger.error(f"Fallback to SentenceTransformer also failed: {fallback_e}")
                raise RuntimeError(f"Both BLEURT and SentenceTransformer fallback failed: {e}")
    
    def compute_score(self, reference: str, candidate: str) -> float:
        """
        Compute raw BLEURT score between reference and candidate texts.
        
        Args:
            reference: The reference text (expected answer)
            candidate: The candidate text (bot response)
            
        Returns:
            Raw BLEURT score (typically ranges from -2 to +2)
        """
        if not self._model_loaded:
            self._load_model()
            
        try:
            logger.debug("Computing BLEURT score...")
            
            # Compute raw BLEURT score using HuggingFace evaluate
            result = self.scorer.compute(
                predictions=[candidate],
                references=[reference]
            )
            raw_score = result['scores'][0]
            
            logger.debug(f"BLEURT raw score: {raw_score:.3f}")
            
            return raw_score
            
        except Exception as e:
            logger.error(f"Error computing BLEURT score: {e}")
            # Return a default low score if computation fails
            return -1.0
    
    def batch_compute_scores(self, references: List[str], candidates: List[str]) -> List[float]:
        """
        Compute raw BLEURT scores for multiple reference-candidate pairs.
        
        Args:
            references: List of reference texts
            candidates: List of candidate texts
            
        Returns:
            List of raw BLEURT scores (typically ranges from -2 to +2)
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
            
            logger.info(f"Computed BLEURT scores for {len(references)} pairs")
            logger.debug(f"Raw score range: {min(raw_scores):.3f} - {max(raw_scores):.3f}")
            
            return raw_scores
            
        except Exception as e:
            logger.error(f"Error computing batch BLEURT scores: {e}")
            # Return default low scores if computation fails
            return [-1.0] * len(references)
    
    def get_score_interpretation(self, raw_score: float) -> str:
        """
        Get human-readable interpretation of the raw BLEURT score.
        
        Args:
            raw_score: Raw BLEURT score (typically -2 to +2)
            
        Returns:
            Human-readable interpretation
        """
        if raw_score >= 1.0:
            return "Excellent semantic similarity"
        elif raw_score >= 0.5:
            return "Good semantic similarity"
        elif raw_score >= 0.0:
            return "Moderate semantic similarity"
        elif raw_score >= -0.5:
            return "Fair semantic similarity"
        elif raw_score >= -1.0:
            return "Poor semantic similarity"
        else:
            return "Very poor semantic similarity"
    
    def is_model_loaded(self) -> bool:
        """Check if the BLEURT model is loaded."""
        return self._model_loaded 