import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class EvaluationDimension(Enum):
    """MT-Bench evaluation dimensions"""
    RELEVANCE = "relevance"
    ACCURACY = "accuracy"
    CLARITY = "clarity"
    DEPTH = "depth"
    CREATIVITY = "creativity"
    HELPFULNESS = "helpfulness"
    HONESTY = "honesty"
    HARM_AVOIDANCE = "harm_avoidance"

@dataclass
class MTBenchEvaluation:
    """Structured evaluation result from MT-Bench"""
    overall_score: float
    dimension_scores: Dict[str, float]
    reasoning: str
    strengths: List[str]
    weaknesses: List[str]
    confidence: float
    evaluation_method: str = "mt_bench"

class MTBenchEvaluator:
    """
    MT-Bench evaluator for AI response quality assessment.
    Based on the MT-Bench framework from Hugging Face.
    """
    
    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4"):
        self.openai_client = openai_client
        self.model = model
        self.evaluation_dimensions = [
            EvaluationDimension.RELEVANCE,
            EvaluationDimension.ACCURACY, 
            EvaluationDimension.CLARITY,
            EvaluationDimension.DEPTH,
            EvaluationDimension.HELPFULNESS
        ]
        logger.info(f"MTBenchEvaluator initialized with model: {model}")
        logger.info(f"Evaluation dimensions: {[dim.value for dim in self.evaluation_dimensions]}")
    
    async def evaluate_single_response(
        self, 
        question: str, 
        response: str, 
        context: Optional[str] = None,
        expected_answer: Optional[str] = None
    ) -> MTBenchEvaluation:
        """
        Evaluate a single response using MT-Bench methodology.
        
        Args:
            question: The user's question
            response: The AI's response to evaluate
            context: Optional context or conversation history
            expected_answer: Optional expected answer for comparison
            
        Returns:
            MTBenchEvaluation object with scores and reasoning
        """
        try:
            logger.info(f"=== MT-Bench Single Response Evaluation ===")
            logger.info(f"Question: {question[:100]}...")
            logger.info(f"Response: {response[:100]}...")
            logger.info(f"Context provided: {context is not None}")
            logger.info(f"Expected answer provided: {expected_answer is not None}")
            
            # Build evaluation prompt based on MT-Bench methodology
            prompt = self._build_evaluation_prompt(question, response, context, expected_answer)
            logger.info(f"Evaluation prompt length: {len(prompt)} characters")
            logger.debug(f"Evaluation prompt: {prompt}")
            
            # Get evaluation from AI judge
            logger.info("Calling AI judge for evaluation...")
            ai_evaluation = await self._get_ai_evaluation(prompt)
            logger.info(f"AI evaluation response length: {len(ai_evaluation)} characters")
            logger.debug(f"AI evaluation response: {ai_evaluation}")
            
            # Parse and structure the evaluation
            logger.info("Parsing AI evaluation response...")
            evaluation = self._parse_evaluation_response(ai_evaluation)
            
            logger.info(f"=== MT-Bench Evaluation Complete ===")
            logger.info(f"Overall Score: {evaluation.overall_score:.3f}")
            logger.info(f"Dimension Scores:")
            for dim, score in evaluation.dimension_scores.items():
                logger.info(f"  {dim}: {score:.3f}")
            logger.info(f"Confidence: {evaluation.confidence:.3f}")
            logger.info(f"Strengths: {evaluation.strengths}")
            logger.info(f"Weaknesses: {evaluation.weaknesses}")
            logger.info(f"Reasoning: {evaluation.reasoning[:200]}...")
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Error in MT-Bench evaluation: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return self._create_default_evaluation(f"Evaluation error: {e}")
    
    async def evaluate_multi_turn_conversation(
        self, 
        conversation: List[Dict[str, str]], 
        persona_context: Optional[str] = None
    ) -> List[MTBenchEvaluation]:
        """
        Evaluate a multi-turn conversation using MT-Bench.
        
        Args:
            conversation: List of message dicts with 'role' and 'content'
            persona_context: Optional persona context for evaluation
            
        Returns:
            List of MTBenchEvaluation objects for each response
        """
        logger.info(f"=== MT-Bench Multi-Turn Evaluation ===")
        logger.info(f"Conversation length: {len(conversation)} messages")
        logger.info(f"Persona context provided: {persona_context is not None}")
        
        evaluations = []
        
        for i, message in enumerate(conversation):
            if message["role"] == "assistant":
                logger.info(f"Evaluating assistant response {len(evaluations) + 1}...")
                
                # Get the user message that prompted this response
                user_message = ""
                if i > 0 and conversation[i-1]["role"] == "user":
                    user_message = conversation[i-1]["content"]
                
                # Get conversation context up to this point
                context = self._format_conversation_context(conversation[:i])
                
                # Evaluate this response
                evaluation = await self.evaluate_single_response(
                    question=user_message,
                    response=message["content"],
                    context=context,
                    persona_context=persona_context
                )
                
                evaluations.append(evaluation)
                
                # Rate limiting
                await asyncio.sleep(0.2)
        
        logger.info(f"Multi-turn evaluation complete. Evaluated {len(evaluations)} responses.")
        return evaluations
    
    async def evaluate_batch_responses(
        self, 
        qa_pairs: List[Dict[str, str]], 
        responses: List[str]
    ) -> List[MTBenchEvaluation]:
        """
        Evaluate multiple question-response pairs in batch.
        
        Args:
            qa_pairs: List of dicts with 'question' and 'answer' keys
            responses: List of AI responses to evaluate
            
        Returns:
            List of MTBenchEvaluation objects
        """
        logger.info(f"=== MT-Bench Batch Evaluation ===")
        logger.info(f"QA pairs count: {len(qa_pairs)}")
        logger.info(f"Responses count: {len(responses)}")
        
        evaluations = []
        
        for i, (qa_pair, response) in enumerate(zip(qa_pairs, responses)):
            logger.info(f"Evaluating batch item {i + 1}/{len(qa_pairs)}...")
            logger.info(f"Question: {qa_pair['question'][:50]}...")
            logger.info(f"Response: {response[:50]}...")
            
            evaluation = await self.evaluate_single_response(
                question=qa_pair["question"],
                response=response,
                expected_answer=qa_pair.get("answer")
            )
            evaluations.append(evaluation)
            
            # Rate limiting
            await asyncio.sleep(0.3)
        
        logger.info(f"Batch evaluation complete. Evaluated {len(evaluations)} responses.")
        return evaluations
    
    def calculate_aggregate_metrics(self, evaluations: List[MTBenchEvaluation]) -> Dict[str, Any]:
        """
        Calculate aggregate metrics from MT-Bench evaluations.
        
        Args:
            evaluations: List of MTBenchEvaluation objects
            
        Returns:
            Dictionary with aggregate metrics
        """
        logger.info(f"=== Calculating MT-Bench Aggregate Metrics ===")
        logger.info(f"Evaluations count: {len(evaluations)}")
        
        if not evaluations:
            logger.warning("No evaluations provided, returning default metrics")
            return self._create_default_metrics()
        
        # Calculate overall scores
        overall_scores = [e.overall_score for e in evaluations]
        avg_overall = sum(overall_scores) / len(overall_scores)
        logger.info(f"Overall scores: {overall_scores}")
        logger.info(f"Average overall score: {avg_overall:.3f}")
        
        # Calculate dimension averages
        dimension_averages = {}
        for dimension in self.evaluation_dimensions:
            dim_name = dimension.value
            scores = [e.dimension_scores.get(dim_name, 0.0) for e in evaluations]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            dimension_averages[f"avg_{dim_name}"] = avg_score
            logger.info(f"Dimension {dim_name} scores: {scores}")
            logger.info(f"Average {dim_name} score: {avg_score:.3f}")
        
        # Calculate pass rates
        pass_rate = sum(1 for score in overall_scores if score >= 0.7) / len(overall_scores)
        logger.info(f"Pass rate (>=0.7): {pass_rate:.3f} ({sum(1 for score in overall_scores if score >= 0.7)}/{len(overall_scores)})")
        
        # Score distribution
        score_distribution = {
            "excellent": len([s for s in overall_scores if s >= 0.9]),
            "good": len([s for s in overall_scores if 0.7 <= s < 0.9]),
            "fair": len([s for s in overall_scores if 0.5 <= s < 0.7]),
            "poor": len([s for s in overall_scores if s < 0.5])
        }
        logger.info(f"Score distribution: {score_distribution}")
        
        # Common strengths and weaknesses
        all_strengths = []
        all_weaknesses = []
        for eval in evaluations:
            all_strengths.extend(eval.strengths)
            all_weaknesses.extend(eval.weaknesses)
        
        # Get most common strengths/weaknesses
        from collections import Counter
        common_strengths = Counter(all_strengths).most_common(5)
        common_weaknesses = Counter(all_weaknesses).most_common(5)
        
        logger.info(f"Common strengths: {common_strengths}")
        logger.info(f"Common weaknesses: {common_weaknesses}")
        
        metrics = {
            "total_evaluations": len(evaluations),
            "avg_overall_score": avg_overall,
            "pass_rate": pass_rate,
            "score_distribution": score_distribution,
            "dimension_averages": dimension_averages,
            "common_strengths": [item[0] for item in common_strengths],
            "common_weaknesses": [item[0] for item in common_weaknesses],
            "evaluation_method": "mt_bench"
        }
        
        logger.info(f"=== Aggregate Metrics Complete ===")
        logger.info(f"Final metrics: {json.dumps(metrics, indent=2)}")
        
        return metrics
    
    def _build_evaluation_prompt(
        self, 
        question: str, 
        response: str, 
        context: Optional[str] = None,
        expected_answer: Optional[str] = None,
        persona_context: Optional[str] = None
    ) -> str:
        """Build the MT-Bench evaluation prompt."""
        logger.debug("Building MT-Bench evaluation prompt...")
        
        prompt_parts = [
            "You are an expert AI evaluator using the MT-Bench methodology to assess response quality.",
            "",
            "Question: " + question,
            "Response: " + response
        ]
        
        if context:
            prompt_parts.extend(["", "Context:", context])
        
        if expected_answer:
            prompt_parts.extend(["", "Expected Answer:", expected_answer])
        
        if persona_context:
            prompt_parts.extend(["", "Persona Context:", persona_context])
        
        prompt_parts.extend([
            "",
            "Evaluate the response on these dimensions (0-10 scale):",
            "- Relevance: How well does the response address the question?",
            "- Accuracy: Is the information factually correct and reliable?",
            "- Clarity: Is the response clear, well-structured, and easy to understand?",
            "- Depth: Does the response provide sufficient detail and insight?",
            "- Helpfulness: How useful and actionable is the response?",
            "",
            "Return ONLY a JSON object with this exact structure:",
            "{",
            '  "overall_score": <float 0-1>,',
            '  "dimension_scores": {',
            '    "relevance": <float 0-1>,',
            '    "accuracy": <float 0-1>,',
            '    "clarity": <float 0-1>,',
            '    "depth": <float 0-1>,',
            '    "helpfulness": <float 0-1>',
            '  },',
            '  "reasoning": "<detailed evaluation reasoning>",',
            '  "strengths": ["<strength1>", "<strength2>"],',
            '  "weaknesses": ["<weakness1>", "<weakness2>"],',
            '  "confidence": <float 0-1>',
            "}",
            "",
            "Scoring guidelines:",
            "- 0.9-1.0: Exceptional quality",
            "- 0.7-0.8: Good quality with minor issues",
            "- 0.5-0.6: Acceptable with notable issues",
            "- 0.0-0.4: Poor quality or incorrect"
        ])
        
        prompt = "\n".join(prompt_parts)
        logger.debug(f"Built prompt with {len(prompt)} characters")
        return prompt
    
    async def _get_ai_evaluation(self, prompt: str) -> str:
        """Get evaluation from AI judge."""
        logger.debug("Calling OpenAI API for evaluation...")
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500
            )
            content = response.choices[0].message.content.strip()
            logger.debug(f"OpenAI API response received: {len(content)} characters")
            return content
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise e
    
    def _parse_evaluation_response(self, response: str) -> MTBenchEvaluation:
        """Parse AI evaluation response into structured format."""
        logger.debug("Parsing AI evaluation response...")
        try:
            # Extract JSON from response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            if start_idx == -1 or end_idx == 0:
                logger.error("No valid JSON found in response")
                logger.error(f"Response content: {response}")
                raise ValueError("No valid JSON found in response")
            
            json_str = response[start_idx:end_idx]
            logger.debug(f"Extracted JSON string: {json_str}")
            
            data = json.loads(json_str)
            logger.debug(f"Parsed JSON data: {data}")
            
            # Validate and normalize scores
            overall_score = float(data.get("overall_score", 0.0))
            dimension_scores = data.get("dimension_scores", {})
            
            # Ensure all dimension scores are floats
            for dim in self.evaluation_dimensions:
                dim_name = dim.value
                if dim_name not in dimension_scores:
                    dimension_scores[dim_name] = 0.0
                    logger.warning(f"Missing dimension score for {dim_name}, defaulting to 0.0")
                else:
                    dimension_scores[dim_name] = float(dimension_scores[dim_name])
            
            evaluation = MTBenchEvaluation(
                overall_score=overall_score,
                dimension_scores=dimension_scores,
                reasoning=data.get("reasoning", "No reasoning provided"),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                confidence=float(data.get("confidence", 0.5))
            )
            
            logger.debug(f"Created MTBenchEvaluation: {evaluation}")
            return evaluation
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse evaluation response: {e}")
            logger.error(f"Response content: {response}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Parse error traceback: {traceback.format_exc()}")
            return self._create_default_evaluation(f"Parsing error: {e}")
    
    def _format_conversation_context(self, conversation: List[Dict[str, str]]) -> str:
        """Format conversation history for context."""
        formatted = []
        for msg in conversation:
            role = msg["role"].capitalize()
            content = msg["content"]
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)
    
    def _create_default_evaluation(self, error_msg: str) -> MTBenchEvaluation:
        """Create default evaluation when evaluation fails."""
        logger.warning(f"Creating default evaluation due to error: {error_msg}")
        return MTBenchEvaluation(
            overall_score=0.0,
            dimension_scores={dim.value: 0.0 for dim in self.evaluation_dimensions},
            reasoning=f"Evaluation failed: {error_msg}",
            strengths=[],
            weaknesses=[f"Evaluation error: {error_msg}"],
            confidence=0.0
        )
    
    def _create_default_metrics(self) -> Dict[str, Any]:
        """Create default metrics when no evaluations available."""
        logger.warning("Creating default metrics - no evaluations available")
        return {
            "total_evaluations": 0,
            "avg_overall_score": 0.0,
            "pass_rate": 0.0,
            "score_distribution": {"excellent": 0, "good": 0, "fair": 0, "poor": 0},
            "dimension_averages": {f"avg_{dim.value}": 0.0 for dim in self.evaluation_dimensions},
            "common_strengths": [],
            "common_weaknesses": [],
            "evaluation_method": "mt_bench"
        } 