import asyncio
import logging
import time
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from .tester_ai import TesterAI
from .judge_ai import JudgeAI

logger = logging.getLogger(__name__)

class AnalyzeOrchestrator:
    def __init__(self, openai_client: AsyncOpenAI, gavin_bot_handler, use_mt_bench: bool = True):
        self.openai_client = openai_client
        self.gavin_bot_handler = gavin_bot_handler
        self.tester_ai = TesterAI(openai_client)
        self.judge_ai = JudgeAI(openai_client, use_mt_bench=use_mt_bench)
        
        # Test session state
        self.current_session = None
        self.current_multi_turn_session = None
        self.session_id = 0
        
        logger.info(f"=== AnalyzeOrchestrator Initialized ===")
        logger.info(f"Using MT-Bench evaluation: {use_mt_bench}")
        logger.info(f"JudgeAI configuration: use_mt_bench={self.judge_ai.use_mt_bench}")
        if use_mt_bench:
            logger.info("MT-Bench evaluation will be used for all assessments")
        else:
            logger.info("Legacy evaluation will be used for all assessments")
    
    async def start_stress_test(self, transcript_text: str, session_name: str = None) -> Dict:
        """
        Start a complete analysis session.
        Returns session info and begins async processing.
        """
        self.session_id += 1
        session_name = session_name or f"Analysis_{self.session_id}_{int(time.time())}"
        
        logger.info(f"Starting analysis session: {session_name}")
        
        # Initialize session state
        self.current_session = {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "parsing_transcript",
            "start_time": time.time(),
            "transcript_text": transcript_text,
            "qa_pairs": [],
            "questions": [],
            "test_results": [],
            "evaluated_results": [],
            "aggregate_metrics": {},
            "progress": {
                "current_step": "parsing_transcript",
                "questions_total": 0,
                "questions_completed": 0,
                "evaluations_completed": 0
            }
        }
        
        # Start async processing
        asyncio.create_task(self._run_stress_test_async())
        
        return {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "started",
            "message": "Analysis initiated. Check dashboard for progress."
        }
    
    async def start_content_analysis(self, content_text: str, session_name: str = None) -> Dict:
        """
        Start a content analysis session specifically for content analysis.
        Returns session info and begins async processing.
        """
        self.session_id += 1
        session_name = session_name or f"Content_Analysis_{self.session_id}_{int(time.time())}"
        
        logger.info(f"Starting content analysis session: {session_name}")
        
        # Initialize session state
        self.current_session = {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "parsing_content",
            "start_time": time.time(),
            "content_text": content_text,
            "qa_pairs": [],
            "questions": [],
            "test_results": [],
            "evaluated_results": [],
            "aggregate_metrics": {},
            "progress": {
                "current_step": "parsing_content",
                "questions_total": 0,
                "questions_completed": 0,
                "evaluations_completed": 0
            }
        }
        
        # Start async processing
        asyncio.create_task(self._run_content_analysis_async())
        
        return {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "started",
            "message": "Content analysis initiated. Check dashboard for progress."
        }
    
    async def _run_stress_test_async(self):
        """
        Run the complete stress test pipeline asynchronously.
        """
        try:
            session = self.current_session
            
            # Step 1: Parse transcript and extract Q&A pairs
            logger.info("Step 1: Parsing transcript...")
            session["status"] = "parsing_transcript"
            session["progress"]["current_step"] = "parsing_transcript"
            
            qa_pairs = await self.tester_ai.parse_transcript(session["transcript_text"])
            session["qa_pairs"] = qa_pairs
            
            if not qa_pairs:
                session["status"] = "failed"
                session["error"] = "No Q&A pairs extracted from transcript"
                return
            
            # Step 2: Extract questions for testing
            logger.info("Step 2: Extracting questions...")
            questions = await self.tester_ai.extract_questions_from_qa_pairs(qa_pairs)
            session["questions"] = questions
            session["progress"]["questions_total"] = len(questions)
            
            # Step 3: Fire questions sequentially and get bot responses
            logger.info("Step 3: Testing bot responses...")
            session["status"] = "testing_responses"
            session["progress"]["current_step"] = "testing_responses"
            
            test_results = await self.tester_ai.fire_questions_sequentially(
                questions, 
                self._handle_question_callback
            )
            session["test_results"] = test_results
            
            # Step 4: Evaluate responses
            logger.info("Step 4: Evaluating responses...")
            session["status"] = "evaluating_responses"
            session["progress"]["current_step"] = "evaluating_responses"
            
            logger.info(f"=== Starting Response Evaluation ===")
            logger.info(f"Test results count: {len(test_results)}")
            logger.info(f"QA pairs count: {len(qa_pairs)}")
            logger.info(f"JudgeAI using MT-Bench: {self.judge_ai.use_mt_bench}")
            
            evaluated_results = await self.judge_ai.batch_evaluate(test_results, qa_pairs)
            session["evaluated_results"] = evaluated_results
            session["progress"]["evaluations_completed"] = len(evaluated_results)
            
            logger.info(f"Evaluation complete. Evaluated {len(evaluated_results)} results.")
            
            # Log evaluation results summary
            valid_evaluations = [r for r in evaluated_results if not r.get("error") and r.get("evaluation")]
            if valid_evaluations:
                overall_scores = [r["evaluation"]["overall_score"] for r in valid_evaluations]
                avg_score = sum(overall_scores) / len(overall_scores)
                logger.info(f"Evaluation Summary:")
                logger.info(f"  Valid evaluations: {len(valid_evaluations)}")
                logger.info(f"  Average overall score: {avg_score:.3f}")
                logger.info(f"  Score range: {min(overall_scores):.3f} - {max(overall_scores):.3f}")
                logger.info(f"  Evaluation methods used: {list(set(r['evaluation'].get('evaluation_method', 'unknown') for r in valid_evaluations))}")
                
                # Log MT-Bench specific metrics if available
                mt_bench_results = [r for r in valid_evaluations if r["evaluation"].get("evaluation_method") == "mt_bench"]
                if mt_bench_results:
                    logger.info(f"MT-Bench Results:")
                    logger.info(f"  MT-Bench evaluations: {len(mt_bench_results)}")
                    for i, result in enumerate(mt_bench_results[:3]):  # Log first 3 for brevity
                        eval_data = result["evaluation"]
                        logger.info(f"  Result {i+1}: Overall={eval_data['overall_score']:.3f}, "
                                  f"Relevance={eval_data.get('mt_bench_scores', {}).get('relevance', 0):.3f}, "
                                  f"Accuracy={eval_data.get('mt_bench_scores', {}).get('accuracy', 0):.3f}")
            
            # Step 5: Calculate aggregate metrics
            logger.info("Step 5: Calculating metrics...")
            session["status"] = "calculating_metrics"
            session["progress"]["current_step"] = "calculating_metrics"
            
            aggregate_metrics = self.judge_ai.calculate_aggregate_metrics(evaluated_results)
            session["aggregate_metrics"] = aggregate_metrics
            
            logger.info(f"=== Final Aggregate Metrics ===")
            logger.info(f"Evaluation method: {aggregate_metrics.get('evaluation_method', 'unknown')}")
            logger.info(f"Total evaluations: {aggregate_metrics.get('total_evaluations', 0)}")
            logger.info(f"Average overall score: {aggregate_metrics.get('avg_overall_score', 0):.3f}")
            logger.info(f"Pass rate: {aggregate_metrics.get('pass_rate', 0):.3f}")
            
            if aggregate_metrics.get('evaluation_method') == 'mt_bench':
                logger.info(f"MT-Bench Dimension Averages:")
                for key, value in aggregate_metrics.get('dimension_averages', {}).items():
                    logger.info(f"  {key}: {value:.3f}")
                logger.info(f"Common strengths: {aggregate_metrics.get('common_strengths', [])}")
                logger.info(f"Common weaknesses: {aggregate_metrics.get('common_weaknesses', [])}")
            
            # Complete
            session["status"] = "completed"
            session["end_time"] = time.time()
            session["duration"] = session["end_time"] - session["start_time"]
            session["progress"]["current_step"] = "completed"
            
            logger.info(f"Analysis completed successfully. Overall score: {aggregate_metrics.get('avg_overall_score', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Analysis failure traceback: {traceback.format_exc()}")
            if self.current_session:
                self.current_session["status"] = "failed"
                self.current_session["error"] = str(e)
                self.current_session["end_time"] = time.time()
    
    async def _handle_question_callback(self, question: str, question_index: int) -> Dict:
        """
        Callback to handle individual question through GavinBot.
        """
        try:
            # Update progress
            if self.current_session:
                self.current_session["progress"]["questions_completed"] = question_index + 1
            
            logger.info(f"Getting GavinBot response for question {question_index + 1}")
            
            # Call the existing GavinBot handler
            bot_response = await self._get_gavin_bot_response(question)
            
            return {
                "question_index": question_index,
                "question": question,
                "bot_response": bot_response,
                "timestamp": time.time(),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Error getting bot response for question {question_index}: {e}")
            return {
                "question_index": question_index,
                "question": question,
                "bot_response": None,
                "timestamp": time.time(),
                "status": "error",
                "error": str(e)
            }
    
    async def _get_gavin_bot_response(self, question: str) -> str:
        """
        Get response from GavinBot using existing chat handler.
        """
        try:
            # Call the gavin_bot_handler with the correct message format
            response = await self.gavin_bot_handler("gavinwood", {
                "message": question,
                "history": []
            })
            # Extract the actual message content from the response
            if isinstance(response, dict) and "message" in response:
                return response["message"]
            elif isinstance(response, str):
                return response
            else:
                logger.error(f"Unexpected response format: {response}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting GavinBot response: {e}")
            raise e
    
    def get_session_status(self) -> Optional[Dict]:
        """
        Get current session status and progress.
        """
        if not self.current_session:
            return None
        
        # Return a copy of current session state (excluding large data)
        status = {
            "session_id": self.current_session["session_id"],
            "session_name": self.current_session["session_name"],
            "status": self.current_session["status"],
            "progress": self.current_session["progress"].copy(),
            "start_time": self.current_session["start_time"],
            "evaluation_method": "mt_bench" if self.judge_ai.use_mt_bench else "legacy"
        }
        
        if "end_time" in self.current_session:
            status["end_time"] = self.current_session["end_time"]
            status["duration"] = self.current_session["duration"]
        
        if "aggregate_metrics" in self.current_session:
            status["aggregate_metrics"] = self.current_session["aggregate_metrics"]
            
            # Add MT-Bench specific status info
            if self.judge_ai.use_mt_bench and status["aggregate_metrics"].get("evaluation_method") == "mt_bench":
                status["mt_bench_summary"] = {
                    "average_overall_score": status["aggregate_metrics"].get("avg_overall_score", 0.0),
                    "pass_rate": status["aggregate_metrics"].get("pass_rate", 0.0),
                    "total_evaluations": status["aggregate_metrics"].get("total_evaluations", 0),
                    "dimension_averages": status["aggregate_metrics"].get("dimension_averages", {}),
                    "score_distribution": status["aggregate_metrics"].get("score_distribution", {})
                }
        
        if "error" in self.current_session:
            status["error"] = self.current_session["error"]
        
        return status
    
    def get_detailed_results(self) -> Optional[Dict]:
        """
        Get detailed test results for completed session.
        """
        if not self.current_session or self.current_session["status"] not in ["completed", "failed"]:
            return None
        
        # Get base results
        results = {
            "session_info": self.get_session_status(),
            "qa_pairs": self.current_session.get("qa_pairs", []),
            "evaluated_results": self.current_session.get("evaluated_results", []),
            "aggregate_metrics": self.current_session.get("aggregate_metrics", {})
        }
        
        # Add detailed MT-Bench analysis if available
        if self.judge_ai.use_mt_bench and results["aggregate_metrics"].get("evaluation_method") == "mt_bench":
            results["mt_bench_analysis"] = self._extract_mt_bench_analysis()
        
        return results
    
    def _extract_mt_bench_analysis(self) -> Dict:
        """
        Extract detailed MT-Bench analysis for dashboard display.
        """
        evaluated_results = self.current_session.get("evaluated_results", [])
        aggregate_metrics = self.current_session.get("aggregate_metrics", {})
        
        # Extract individual MT-Bench evaluations
        mt_bench_evaluations = []
        for i, result in enumerate(evaluated_results):
            if result.get("evaluation", {}).get("evaluation_method") == "mt_bench":
                eval_data = result["evaluation"]
                mt_bench_evaluations.append({
                    "question_index": i,
                    "question": result.get("question", ""),
                    "bot_response": result.get("bot_response", ""),
                    "expected_answer": result.get("expected_answer", ""),
                    "overall_score": eval_data.get("overall_score", 0.0),
                    "dimension_scores": eval_data.get("mt_bench_scores", {}),
                    "content_similarity": eval_data.get("content_similarity", 0.0),
                    "style_fidelity": eval_data.get("style_fidelity", 0.0),
                    "confidence": eval_data.get("confidence", 0.0),
                    "reasoning": eval_data.get("reasoning", {}),
                    "strengths": eval_data.get("reasoning", {}).get("strengths", []),
                    "weaknesses": eval_data.get("reasoning", {}).get("weaknesses", [])
                })
        
        # Calculate dimension breakdowns
        dimension_breakdown = {}
        if aggregate_metrics.get("dimension_averages"):
            for dim_key, avg_score in aggregate_metrics["dimension_averages"].items():
                dim_name = dim_key.replace("avg_", "")
                dimension_breakdown[dim_name] = {
                    "average_score": avg_score,
                    "description": self._get_dimension_description(dim_name),
                    "individual_scores": [
                        {
                            "question_index": eval["question_index"],
                            "score": eval["dimension_scores"].get(dim_name, 0.0)
                        }
                        for eval in mt_bench_evaluations
                    ]
                }
        
        result = {
            "evaluation_method": "mt_bench",
            "total_evaluations": len(mt_bench_evaluations),
            "individual_evaluations": mt_bench_evaluations,
            "dimension_breakdown": dimension_breakdown,
            "score_distribution": aggregate_metrics.get("score_distribution", {}),
            "common_strengths": aggregate_metrics.get("common_strengths", []),
            "common_weaknesses": aggregate_metrics.get("common_weaknesses", []),
            "pass_rate": aggregate_metrics.get("pass_rate", 0.0),
            "average_overall_score": aggregate_metrics.get("avg_overall_score", 0.0)
        }
        
        logger.info(f"  MT-Bench analysis result: {result}")
        return result
    
    def _get_dimension_description(self, dimension: str) -> str:
        """Get human-readable description of MT-Bench dimensions."""
        descriptions = {
            "relevance": "How well the response addresses the question",
            "accuracy": "Factual correctness and reliability of information",
            "clarity": "Clear, well-structured, and easy to understand",
            "depth": "Sufficient detail and insight provided",
            "helpfulness": "Useful and actionable response"
        }
        return descriptions.get(dimension, f"Score for {dimension}")

    async def start_multi_turn_test(self, messages: List[Dict[str, str]], session_name: str = None) -> Dict:
        """
        Start a multi-turn test session.
        Returns session info and begins async processing.
        """
        self.session_id += 1
        session_name = session_name or f"MultiTurn_{self.session_id}_{int(time.time())}"
        
        logger.info(f"Starting multi-turn test session: {session_name}")
        
        # Initialize session state
        self.current_multi_turn_session = {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "processing",
            "start_time": time.time(),
            "messages": messages,
            "responses": [],
            "evaluations": [],
            "aggregate_metrics": {},
            "progress": {
                "current_step": "processing",
                "total_messages": len(messages),
                "processed_messages": 0
            }
        }
        
        # Start async processing
        asyncio.create_task(self._run_multi_turn_test_async())
        
        return {
            "session_id": self.session_id,
            "session_name": session_name,
            "status": "started",
            "message": "Multi-turn test initiated. Check dashboard for progress."
        }

    async def _run_multi_turn_test_async(self):
        """
        Run the multi-turn test pipeline asynchronously.
        """
        try:
            session = self.current_multi_turn_session
            
            # Process each message and get bot response
            for i, message in enumerate(session["messages"]):
                if message["role"] == "user":
                    # Get bot response
                    bot_response = await self._get_gavin_bot_response(message["content"])
                    
                    # Evaluate response
                    evaluation = await self.judge_ai.evaluate_multi_turn_response(
                        user_message=message["content"],
                        bot_response=bot_response,
                        conversation_history=session["messages"][:i]
                    )
                    
                    # Store results
                    session["responses"].append({
                        "user_message": message["content"],
                        "bot_response": bot_response,
                        "evaluation": evaluation
                    })
                    
                    # Update progress
                    session["progress"]["processed_messages"] = i + 1
            
            # Calculate aggregate metrics
            session["aggregate_metrics"] = self.judge_ai.calculate_multi_turn_metrics(session["responses"])
            
            # Complete
            session["status"] = "completed"
            session["end_time"] = time.time()
            session["duration"] = session["end_time"] - session["start_time"]
            session["progress"]["current_step"] = "completed"
            
            logger.info(f"Multi-turn test completed successfully. Overall score: {session['aggregate_metrics'].get('avg_overall_score', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Multi-turn test failed: {e}")
            if self.current_multi_turn_session:
                self.current_multi_turn_session["status"] = "failed"
                self.current_multi_turn_session["error"] = str(e)
                self.current_multi_turn_session["end_time"] = time.time()

    def get_multi_turn_status(self) -> Optional[Dict]:
        """Get current multi-turn test session status."""
        if not self.current_multi_turn_session:
            return None
        return self.current_multi_turn_session

    def get_multi_turn_results(self) -> Optional[Dict]:
        """Get detailed results from completed multi-turn test session."""
        if not self.current_multi_turn_session or self.current_multi_turn_session["status"] != "completed":
            return None
        return self.current_multi_turn_session 

    async def _run_content_analysis_async(self):
        """
        Run the complete content analysis pipeline asynchronously.
        """
        try:
            session = self.current_session
            
            # Step 1: Parse content and generate questions
            logger.info("Step 1: Parsing content for questions...")
            session["status"] = "parsing_content"
            session["progress"]["current_step"] = "parsing_content"
            
            qa_pairs = await self.tester_ai.parse_content_for_analysis(session["content_text"])
            session["qa_pairs"] = qa_pairs
            
            if not qa_pairs:
                session["status"] = "failed"
                session["error"] = "No questions generated from content"
                return
            
            # Step 2: Extract questions for testing
            logger.info("Step 2: Extracting questions...")
            questions = await self.tester_ai.extract_questions_from_qa_pairs(qa_pairs)
            session["questions"] = questions
            session["progress"]["questions_total"] = len(questions)
            
            # Step 3: Fire questions sequentially and get bot responses
            logger.info("Step 3: Testing bot responses...")
            session["status"] = "testing_responses"
            session["progress"]["current_step"] = "testing_responses"
            
            test_results = await self.tester_ai.fire_questions_sequentially(
                questions, 
                self._handle_question_callback
            )
            session["test_results"] = test_results
            
            # Step 4: Evaluate responses
            logger.info("Step 4: Evaluating responses...")
            session["status"] = "evaluating_responses"
            session["progress"]["current_step"] = "evaluating_responses"
            
            evaluated_results = await self.judge_ai.batch_evaluate(test_results, qa_pairs)
            session["evaluated_results"] = evaluated_results
            session["progress"]["evaluations_completed"] = len(evaluated_results)
            
            # Step 5: Calculate aggregate metrics
            logger.info("Step 5: Calculating metrics...")
            session["status"] = "calculating_metrics"
            session["progress"]["current_step"] = "calculating_metrics"
            
            aggregate_metrics = self.judge_ai.calculate_aggregate_metrics(evaluated_results)
            session["aggregate_metrics"] = aggregate_metrics
            
            # Complete
            session["status"] = "completed"
            session["end_time"] = time.time()
            session["duration"] = session["end_time"] - session["start_time"]
            session["progress"]["current_step"] = "completed"
            
            logger.info(f"Content analysis completed successfully. Overall score: {aggregate_metrics.get('avg_overall_score', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            if self.current_session:
                self.current_session["status"] = "failed"
                self.current_session["error"] = str(e)
                self.current_session["end_time"] = time.time() 