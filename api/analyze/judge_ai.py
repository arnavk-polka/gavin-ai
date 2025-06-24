import logging
import json
from typing import Dict, List, Tuple, Optional
from openai import AsyncOpenAI
import asyncio
from .mt_bench_evaluator import MTBenchEvaluator, MTBenchEvaluation

logger = logging.getLogger(__name__)

class JudgeAI:
    def __init__(self, openai_client: AsyncOpenAI, use_mt_bench: bool = True):
        self.openai_client = openai_client
        self.use_mt_bench = use_mt_bench
        
        # Initialize MT-Bench evaluator if enabled
        if self.use_mt_bench:
            self.mt_bench_evaluator = MTBenchEvaluator(openai_client)
    
    async def evaluate_response(self, question: str, bot_response: str, expected_answer: str) -> Dict:
        """
        Evaluate bot response against expected answer.
        Returns dict with content_similarity, style_fidelity, and overall_score.
        """
        if self.use_mt_bench:
            return await self._evaluate_with_mt_bench(question, bot_response, expected_answer)
        else:
            return await self._evaluate_with_legacy(question, bot_response, expected_answer)
    
    async def _evaluate_with_mt_bench(self, question: str, bot_response: str, expected_answer: str) -> Dict:
        """Evaluate using MT-Bench methodology."""
        logger.info(f"=== JudgeAI MT-Bench Evaluation ===")
        logger.info(f"Question: {question[:100]}...")
        logger.info(f"Bot Response: {bot_response[:100]}...")
        logger.info(f"Expected Answer: {expected_answer[:100] if expected_answer else 'None'}...")
        
        try:
            mt_evaluation = await self.mt_bench_evaluator.evaluate_single_response(
                question=question,
                response=bot_response,
                expected_answer=expected_answer
            )
            
            logger.info(f"MT-Bench evaluation received:")
            logger.info(f"  Overall Score: {mt_evaluation.overall_score:.3f}")
            logger.info(f"  Dimension Scores: {mt_evaluation.dimension_scores}")
            logger.info(f"  Confidence: {mt_evaluation.confidence:.3f}")
            
            # Convert MT-Bench evaluation to legacy format for compatibility
            legacy_evaluation = {
                "content_similarity": mt_evaluation.dimension_scores.get("relevance", 0.0),
                "style_fidelity": mt_evaluation.dimension_scores.get("clarity", 0.0),
                "overall_score": mt_evaluation.overall_score,
                "mt_bench_scores": mt_evaluation.dimension_scores,
                "reasoning": {
                    "content_analysis": mt_evaluation.reasoning,
                    "style_analysis": f"Clarity score: {mt_evaluation.dimension_scores.get('clarity', 0.0):.2f}",
                    "strengths": mt_evaluation.strengths,
                    "weaknesses": mt_evaluation.weaknesses
                },
                "evaluation_method": "mt_bench",
                "confidence": mt_evaluation.confidence
            }
            
            logger.info(f"Converted to legacy format:")
            logger.info(f"  Content Similarity: {legacy_evaluation['content_similarity']:.3f}")
            logger.info(f"  Style Fidelity: {legacy_evaluation['style_fidelity']:.3f}")
            logger.info(f"  Overall Score: {legacy_evaluation['overall_score']:.3f}")
            logger.info(f"  Evaluation Method: {legacy_evaluation['evaluation_method']}")
            
            return legacy_evaluation
            
        except Exception as e:
            logger.error(f"MT-Bench evaluation failed, falling back to legacy: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"MT-Bench fallback traceback: {traceback.format_exc()}")
            return await self._evaluate_with_legacy(question, bot_response, expected_answer)
    
    async def _evaluate_with_legacy(self, question: str, bot_response: str, expected_answer: str) -> Dict:
        """Legacy evaluation method."""
        try:
            logger.info(f"Evaluating response for question: {question[:50]}...")
            
            evaluation_prompt = f"""
            You are an expert AI evaluator. Compare the bot's response to the expected answer and provide scores.
            
            Question: {question}
            
            Expected Answer: {expected_answer}
            
            Bot Response: {bot_response}
            
            Evaluate on these criteria and return ONLY a JSON object:
            
            {{
                "content_similarity": <float 0-1>,
                "style_fidelity": <float 0-1>, 
                "overall_score": <float 0-1>,
                "reasoning": {{
                    "content_analysis": "Brief explanation of content similarity",
                    "style_analysis": "Brief explanation of style match",
                    "strengths": ["strength1", "strength2"],
                    "weaknesses": ["weakness1", "weakness2"]
                }}
            }}
            
            Scoring guidelines:
            - content_similarity: How well does the bot capture the key information/meaning?
            - style_fidelity: How well does the bot match the expected communication style?
            - overall_score: Weighted average (70% content, 30% style)
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": evaluation_prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            try:
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content[start_idx:end_idx]
                    evaluation = json.loads(json_str)
                    
                    # Validate required fields
                    required_fields = ["content_similarity", "style_fidelity", "overall_score"]
                    for field in required_fields:
                        if field not in evaluation:
                            evaluation[field] = 0.0
                    
                    evaluation["evaluation_method"] = "legacy"
                    # Add confidence if not present
                    if "confidence" not in evaluation:
                        evaluation["confidence"] = 0.7  # Default confidence for legacy evaluations
                    logger.info(f"Evaluation complete - Overall score: {evaluation.get('overall_score', 0):.2f}")
                    return evaluation
                else:
                    logger.error("No valid JSON found in evaluation response")
                    return self._default_evaluation("JSON parsing failed")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse evaluation JSON: {e}")
                return self._default_evaluation(f"JSON decode error: {e}")
                
        except Exception as e:
            logger.error(f"Error evaluating response: {e}")
            return self._default_evaluation(f"Evaluation error: {e}")
    
    def _default_evaluation(self, error_msg: str) -> Dict:
        """Return default evaluation when AI evaluation fails."""
        return {
            "content_similarity": 0.0,
            "style_fidelity": 0.0,
            "overall_score": 0.0,
            "reasoning": {
                "content_analysis": "Evaluation failed",
                "style_analysis": "Evaluation failed", 
                "strengths": [],
                "weaknesses": [f"Evaluation error: {error_msg}"]
            },
            "error": error_msg,
            "evaluation_method": "legacy"
        }
    
    async def batch_evaluate(self, test_results: List[Dict], qa_pairs: List[Dict[str, str]]) -> List[Dict]:
        """
        Evaluate multiple responses in batch.
        """
        if self.use_mt_bench:
            return await self._batch_evaluate_with_mt_bench(test_results, qa_pairs)
        else:
            return await self._batch_evaluate_with_legacy(test_results, qa_pairs)
    
    async def _batch_evaluate_with_mt_bench(self, test_results: List[Dict], qa_pairs: List[Dict[str, str]]) -> List[Dict]:
        """Batch evaluate using MT-Bench."""
        logger.info(f"=== JudgeAI MT-Bench Batch Evaluation ===")
        logger.info(f"Test results count: {len(test_results)}")
        logger.info(f"QA pairs count: {len(qa_pairs)}")
        
        try:
            # Extract questions and responses
            questions = []
            responses = []
            valid_indices = []
            
            for i, result in enumerate(test_results):
                if result.get("error"):
                    logger.warning(f"Test result {i} has error: {result.get('error')}")
                    continue
                
                if i < len(qa_pairs):
                    questions.append(qa_pairs[i].get("question", ""))
                    responses.append(result.get("bot_response", ""))
                    valid_indices.append(i)
                    logger.info(f"Added valid test result {i}: {qa_pairs[i].get('question', '')[:50]}...")
                else:
                    logger.warning(f"Test result {i} has no corresponding QA pair")
            
            logger.info(f"Valid test results for MT-Bench evaluation: {len(questions)}")
            
            # Get MT-Bench evaluations
            logger.info("Calling MT-Bench batch evaluator...")
            mt_evaluations = await self.mt_bench_evaluator.evaluate_batch_responses(
                [{"question": q, "answer": qa_pairs[i].get("answer", "")} for i, q in enumerate(questions)],
                responses
            )
            
            logger.info(f"Received {len(mt_evaluations)} MT-Bench evaluations")
            
            # Merge results
            evaluated_results = []
            for i, result in enumerate(test_results):
                if i in valid_indices:
                    mt_idx = valid_indices.index(i)
                    mt_eval = mt_evaluations[mt_idx]
                    
                    logger.info(f"Converting MT-Bench evaluation {mt_idx} for test result {i}")
                    logger.info(f"  MT-Bench Overall Score: {mt_eval.overall_score:.3f}")
                    logger.info(f"  MT-Bench Dimension Scores: {mt_eval.dimension_scores}")
                    
                    # Convert to legacy format
                    result["evaluation"] = {
                        "content_similarity": mt_eval.dimension_scores.get("relevance", 0.0),
                        "style_fidelity": mt_eval.dimension_scores.get("clarity", 0.0),
                        "overall_score": mt_eval.overall_score,
                        "mt_bench_scores": mt_eval.dimension_scores,
                        "reasoning": {
                            "content_analysis": mt_eval.reasoning,
                            "style_analysis": f"Clarity score: {mt_eval.dimension_scores.get('clarity', 0.0):.2f}",
                            "strengths": mt_eval.strengths,
                            "weaknesses": mt_eval.weaknesses
                        },
                        "evaluation_method": "mt_bench",
                        "confidence": mt_eval.confidence
                    }
                    result["expected_answer"] = qa_pairs[i].get("answer", "")
                    
                    logger.info(f"  Legacy Overall Score: {result['evaluation']['overall_score']:.3f}")
                    logger.info(f"  Legacy Content Similarity: {result['evaluation']['content_similarity']:.3f}")
                    logger.info(f"  Legacy Style Fidelity: {result['evaluation']['style_fidelity']:.3f}")
                else:
                    logger.warning(f"Test result {i} not in valid indices, using default evaluation")
                    result["evaluation"] = self._default_evaluation(result.get("error", "No expected answer found"))
                
                evaluated_results.append(result)
            
            logger.info(f"Batch evaluation complete. Processed {len(evaluated_results)} results.")
            return evaluated_results
            
        except Exception as e:
            logger.error(f"MT-Bench batch evaluation failed, falling back to legacy: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"MT-Bench batch fallback traceback: {traceback.format_exc()}")
            return await self._batch_evaluate_with_legacy(test_results, qa_pairs)
    
    async def _batch_evaluate_with_legacy(self, test_results: List[Dict], qa_pairs: List[Dict[str, str]]) -> List[Dict]:
        """Legacy batch evaluation method."""
        evaluated_results = []
        
        for i, result in enumerate(test_results):
            if result.get("error"):
                # Skip evaluation for errored results
                result["evaluation"] = self._default_evaluation(result["error"])
                evaluated_results.append(result)
                continue
            
            # Get expected answer from QA pairs
            if i < len(qa_pairs):
                expected_answer = qa_pairs[i].get("answer", "")
                question = result.get("question", "")
                bot_response = result.get("bot_response", "")
                
                # Evaluate this response
                evaluation = await self._evaluate_with_legacy(question, bot_response, expected_answer)
                result["evaluation"] = evaluation
                result["expected_answer"] = expected_answer
            else:
                result["evaluation"] = self._default_evaluation("No expected answer found")
            
            evaluated_results.append(result)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.3)
        
        return evaluated_results
    
    def calculate_aggregate_metrics(self, evaluated_results: List[Dict]) -> Dict:
        """
        Calculate aggregate metrics across all evaluations.
        """
        if self.use_mt_bench:
            return self._calculate_mt_bench_metrics(evaluated_results)
        else:
            return self._calculate_legacy_metrics(evaluated_results)
    
    def _calculate_mt_bench_metrics(self, evaluated_results: List[Dict]) -> Dict:
        """Calculate metrics using MT-Bench methodology."""
        logger.info(f"=== JudgeAI MT-Bench Metrics Calculation ===")
        logger.info(f"Evaluated results count: {len(evaluated_results)}")
        
        valid_results = [r for r in evaluated_results if not r.get("error") and r.get("evaluation")]
        logger.info(f"Valid results count: {len(valid_results)}")
        
        if not valid_results:
            logger.warning("No valid results for MT-Bench metrics calculation")
            return self.mt_bench_evaluator._create_default_metrics()
        
        # Extract MT-Bench evaluations
        mt_evaluations = []
        for i, result in enumerate(valid_results):
            eval_data = result["evaluation"]
            if eval_data.get("evaluation_method") == "mt_bench":
                logger.info(f"Processing MT-Bench evaluation {i}:")
                logger.info(f"  Overall Score: {eval_data['overall_score']:.3f}")
                logger.info(f"  MT-Bench Scores: {eval_data.get('mt_bench_scores', {})}")
                
                mt_eval = MTBenchEvaluation(
                    overall_score=eval_data["overall_score"],
                    dimension_scores=eval_data.get("mt_bench_scores", {}),
                    reasoning=eval_data["reasoning"]["content_analysis"],
                    strengths=eval_data["reasoning"].get("strengths", []),
                    weaknesses=eval_data["reasoning"].get("weaknesses", []),
                    confidence=eval_data.get("confidence", 0.5)
                )
                mt_evaluations.append(mt_eval)
            else:
                logger.warning(f"Result {i} uses {eval_data.get('evaluation_method', 'unknown')} method, skipping MT-Bench metrics")
        
        logger.info(f"MT-Bench evaluations extracted: {len(mt_evaluations)}")
        
        metrics = self.mt_bench_evaluator.calculate_aggregate_metrics(mt_evaluations)
        logger.info(f"MT-Bench metrics calculated: {json.dumps(metrics, indent=2)}")
        
        return metrics
    
    def _calculate_legacy_metrics(self, evaluated_results: List[Dict]) -> Dict:
        """Calculate metrics using legacy methodology."""
        valid_results = [r for r in evaluated_results if not r.get("error") and r.get("evaluation")]
        
        if not valid_results:
            return {
                "total_questions": len(evaluated_results),
                "successful_responses": 0,
                "avg_content_similarity": 0.0,
                "avg_style_fidelity": 0.0,
                "avg_overall_score": 0.0,
                "pass_rate": 0.0,
                "evaluation_method": "legacy"
            }
        
        content_scores = [r["evaluation"]["content_similarity"] for r in valid_results]
        style_scores = [r["evaluation"]["style_fidelity"] for r in valid_results]  
        overall_scores = [r["evaluation"]["overall_score"] for r in valid_results]
        
        # Calculate pass rate (overall score >= 0.7)
        passing_scores = [s for s in overall_scores if s >= 0.7]
        pass_rate = len(passing_scores) / len(overall_scores) if overall_scores else 0.0
        
        return {
            "total_questions": len(evaluated_results),
            "successful_responses": len(valid_results),
            "avg_content_similarity": sum(content_scores) / len(content_scores) if content_scores else 0.0,
            "avg_style_fidelity": sum(style_scores) / len(style_scores) if style_scores else 0.0,
            "avg_overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0.0,
            "pass_rate": pass_rate,
            "score_distribution": {
                "excellent": len([s for s in overall_scores if s >= 0.9]),
                "good": len([s for s in overall_scores if 0.7 <= s < 0.9]),
                "fair": len([s for s in overall_scores if 0.5 <= s < 0.7]),
                "poor": len([s for s in overall_scores if s < 0.5])
            },
            "evaluation_method": "legacy"
        }

    async def evaluate_multi_turn_response(self, user_message: str, bot_response: str, conversation_history: List[Dict[str, str]]) -> Dict:
        """
        Evaluate a single response in a multi-turn conversation.
        """
        if self.use_mt_bench:
            return await self._evaluate_multi_turn_with_mt_bench(user_message, bot_response, conversation_history)
        else:
            return await self._evaluate_multi_turn_with_legacy(user_message, bot_response, conversation_history)
    
    async def _evaluate_multi_turn_with_mt_bench(self, user_message: str, bot_response: str, conversation_history: List[Dict[str, str]]) -> Dict:
        """Evaluate multi-turn response using MT-Bench."""
        try:
            # Create conversation context
            context = self._format_conversation_history(conversation_history)
            
            mt_evaluation = await self.mt_bench_evaluator.evaluate_single_response(
                question=user_message,
                response=bot_response,
                context=context
            )
            
            # Convert to legacy format
            return {
                "overall_score": mt_evaluation.overall_score,
                "relevance_score": mt_evaluation.dimension_scores.get("relevance", 0.0),
                "consistency_score": mt_evaluation.dimension_scores.get("accuracy", 0.0),
                "technical_score": mt_evaluation.dimension_scores.get("accuracy", 0.0),
                "clarity_score": mt_evaluation.dimension_scores.get("clarity", 0.0),
                "persona_score": mt_evaluation.dimension_scores.get("helpfulness", 0.0),
                "reasoning": mt_evaluation.reasoning,
                "confidence": mt_evaluation.confidence,
                "evaluation_method": "mt_bench",
                "mt_bench_scores": mt_evaluation.dimension_scores
            }
            
        except Exception as e:
            logger.error(f"MT-Bench multi-turn evaluation failed, falling back to legacy: {e}")
            return await self._evaluate_multi_turn_with_legacy(user_message, bot_response, conversation_history)
    
    async def _evaluate_multi_turn_with_legacy(self, user_message: str, bot_response: str, conversation_history: List[Dict[str, str]]) -> Dict:
        """Legacy multi-turn evaluation method."""
        try:
            # Build evaluation prompt
            prompt = f"""
            Evaluate this response in a multi-turn conversation context.
            
            Conversation History:
            {self._format_conversation_history(conversation_history)}
            
            User Message: {user_message}
            Bot Response: {bot_response}
            
            Evaluate the response on:
            1. Relevance to the user's message
            2. Consistency with conversation history
            3. Technical accuracy
            4. Clarity and conciseness
            5. Adherence to Gavin's persona
            
            Return a JSON object with:
            - overall_score (0-1)
            - relevance_score (0-1)
            - consistency_score (0-1)
            - technical_score (0-1)
            - clarity_score (0-1)
            - persona_score (0-1)
            - confidence (0-1, your confidence in this evaluation)
            - reasoning (detailed analysis)
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            try:
                # Find JSON object in response
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content[start_idx:end_idx]
                    evaluation = json.loads(json_str)
                    evaluation["evaluation_method"] = "legacy"
                    # Add confidence if not present
                    if "confidence" not in evaluation:
                        evaluation["confidence"] = 0.7  # Default confidence for legacy evaluations
                    return evaluation
                else:
                    logger.error("No valid JSON object found in AI response")
                    return self._create_default_evaluation()
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from AI response: {e}")
                logger.error(f"Response content: {content}")
                return self._create_default_evaluation()
                
        except Exception as e:
            logger.error(f"Error evaluating multi-turn response: {e}")
            return self._create_default_evaluation()

    def calculate_multi_turn_metrics(self, responses: List[Dict]) -> Dict:
        """
        Calculate aggregate metrics for a multi-turn conversation.
        """
        if not responses:
            return self._create_default_metrics()
            
        total_responses = len(responses)
        
        # Calculate averages
        metrics = {
            "avg_overall_score": sum(r["evaluation"]["overall_score"] for r in responses) / total_responses,
            "avg_relevance_score": sum(r["evaluation"]["relevance_score"] for r in responses) / total_responses,
            "avg_consistency_score": sum(r["evaluation"]["consistency_score"] for r in responses) / total_responses,
            "avg_technical_score": sum(r["evaluation"]["technical_score"] for r in responses) / total_responses,
            "avg_clarity_score": sum(r["evaluation"]["clarity_score"] for r in responses) / total_responses,
            "avg_persona_score": sum(r["evaluation"]["persona_score"] for r in responses) / total_responses,
            "total_responses": total_responses,
            "pass_rate": sum(1 for r in responses if r["evaluation"]["overall_score"] >= 0.7) / total_responses,
            "evaluation_method": responses[0]["evaluation"].get("evaluation_method", "legacy") if responses else "legacy"
        }
        
        return metrics

    def _format_conversation_history(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history for evaluation prompt."""
        formatted = []
        for msg in history:
            role = msg["role"].capitalize()
            content = msg["content"]
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    def _create_default_evaluation(self) -> Dict:
        """Create a default evaluation object."""
        return {
            "overall_score": 0.0,
            "relevance_score": 0.0,
            "consistency_score": 0.0,
            "technical_score": 0.0,
            "clarity_score": 0.0,
            "persona_score": 0.0,
            "confidence": 0.0,
            "reasoning": "Evaluation failed",
            "evaluation_method": "legacy"
        }

    def _create_default_metrics(self) -> Dict:
        """Create a default metrics object."""
        return {
            "avg_overall_score": 0.0,
            "avg_relevance_score": 0.0,
            "avg_consistency_score": 0.0,
            "avg_technical_score": 0.0,
            "avg_clarity_score": 0.0,
            "avg_persona_score": 0.0,
            "total_responses": 0,
            "pass_rate": 0.0,
            "evaluation_method": "legacy"
        } 