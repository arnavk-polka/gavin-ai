import asyncio
import logging
import time
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from .tester_ai import TesterAI
from .judge_ai import JudgeAI

logger = logging.getLogger(__name__)

class AnalyzeOrchestrator:
    def __init__(self, openai_client: AsyncOpenAI, gavin_bot_handler):
        self.openai_client = openai_client
        self.gavin_bot_handler = gavin_bot_handler
        self.tester_ai = TesterAI(openai_client)
        self.judge_ai = JudgeAI(openai_client)
        
        # Test session state
        self.current_session = None
        self.current_multi_turn_session = None
        self.session_id = 0
    
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
            
            logger.info(f"Analysis completed successfully. Overall score: {aggregate_metrics.get('avg_overall_score', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
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
            "start_time": self.current_session["start_time"]
        }
        
        if "end_time" in self.current_session:
            status["end_time"] = self.current_session["end_time"]
            status["duration"] = self.current_session["duration"]
        
        if "aggregate_metrics" in self.current_session:
            status["aggregate_metrics"] = self.current_session["aggregate_metrics"]
        
        if "error" in self.current_session:
            status["error"] = self.current_session["error"]
        
        return status
    
    def get_detailed_results(self) -> Optional[Dict]:
        """
        Get detailed test results for completed session.
        """
        if not self.current_session or self.current_session["status"] not in ["completed", "failed"]:
            return None
        
        return {
            "session_info": self.get_session_status(),
            "qa_pairs": self.current_session.get("qa_pairs", []),
            "evaluated_results": self.current_session.get("evaluated_results", []),
            "aggregate_metrics": self.current_session.get("aggregate_metrics", {})
        }

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