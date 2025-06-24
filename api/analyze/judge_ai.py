import logging
import json
from typing import Dict, List, Tuple
from openai import AsyncOpenAI
import asyncio

logger = logging.getLogger(__name__)

class JudgeAI:
    def __init__(self, openai_client: AsyncOpenAI):
        self.openai_client = openai_client
    
    async def evaluate_response(self, question: str, bot_response: str, expected_answer: str) -> Dict:
        """
        Evaluate bot response against expected answer.
        Returns dict with content_similarity, style_fidelity, and overall_score.
        """
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
            "error": error_msg
        }
    
    async def batch_evaluate(self, test_results: List[Dict], qa_pairs: List[Dict[str, str]]) -> List[Dict]:
        """
        Evaluate multiple responses in batch.
        """
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
                evaluation = await self.evaluate_response(question, bot_response, expected_answer)
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
        valid_results = [r for r in evaluated_results if not r.get("error") and r.get("evaluation")]
        
        if not valid_results:
            return {
                "total_questions": len(evaluated_results),
                "successful_responses": 0,
                "avg_content_similarity": 0.0,
                "avg_style_fidelity": 0.0,
                "avg_overall_score": 0.0,
                "pass_rate": 0.0
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
            }
        }

    async def evaluate_multi_turn_response(self, user_message: str, bot_response: str, conversation_history: List[Dict[str, str]]) -> Dict:
        """
        Evaluate a single response in a multi-turn conversation.
        """
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
            "pass_rate": sum(1 for r in responses if r["evaluation"]["overall_score"] >= 0.7) / total_responses
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
            "reasoning": "Evaluation failed"
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
            "pass_rate": 0.0
        } 