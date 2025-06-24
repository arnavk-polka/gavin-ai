import re
import json
import logging
from typing import List, Dict, Tuple
from openai import AsyncOpenAI
import asyncio

logger = logging.getLogger(__name__)

class TesterAI:
    def __init__(self, openai_client: AsyncOpenAI):
        self.openai_client = openai_client
        
    async def parse_transcript(self, transcript_text: str) -> List[Dict[str, str]]:
        """
        Parse podcast transcript to extract Q&A pairs using AI.
        Returns list of {"question": str, "answer": str} dicts.
        """
        try:
            logger.info("Parsing transcript for Q&A pairs...")
            
            # Use AI to extract Q&A pairs from transcript
            prompt = f"""
            Analyze this podcast transcript and extract clear question-answer pairs. 
            Focus on questions that test knowledge about the topic being discussed.
            
            Return ONLY a JSON array of objects with "question" and "answer" fields.
            Each question should be self-contained and each answer should be the actual response from the transcript.
            
            Transcript:
            {transcript_text[:8000]}  # Limit to avoid token limits
            
            Format exactly like this:
            [
                {{"question": "What is...", "answer": "The answer is..."}},
                {{"question": "How does...", "answer": "It works by..."}}
            ]
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            try:
                # Find JSON array in response
                start_idx = content.find('[')
                end_idx = content.rfind(']') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content[start_idx:end_idx]
                    qa_pairs = json.loads(json_str)
                    
                    logger.info(f"Extracted {len(qa_pairs)} Q&A pairs from transcript")
                    return qa_pairs
                else:
                    logger.error("No valid JSON array found in AI response")
                    return []
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from AI response: {e}")
                logger.error(f"Response content: {content}")
                return []
                
        except Exception as e:
            logger.error(f"Error parsing transcript: {e}")
            return []
    
    async def extract_questions_from_qa_pairs(self, qa_pairs: List[Dict[str, str]]) -> List[str]:
        """
        Extract just the questions from Q&A pairs for sequential firing.
        """
        questions = [pair.get("question", "") for pair in qa_pairs if pair.get("question")]
        logger.info(f"Extracted {len(questions)} questions for testing")
        return questions
    
    async def parse_content_for_analysis(self, content_text: str) -> List[Dict[str, str]]:
        """
        Parse content and generate relevant questions for analysis.
        Returns list of {"question": str, "answer": str} dicts where answer is empty.
        """
        try:
            logger.info("Parsing content for analysis questions...")
            
            # Use AI to generate questions from content
            prompt = f"""
            Analyze this content and generate 4-6 specific technical questions about blockchain, crypto, or technology topics mentioned.
            
            The content could be a blog post, tweet, article, or any other format. Extract the key technical concepts and create questions that would test deep understanding.
            
            Each question should be:
            - Self-contained and clear
            - Focused on technical details and concepts
            - About blockchain, crypto, Web3, or related technology
            - Something that would require expert knowledge to answer well
            - Specific enough to test understanding, not just general knowledge
            
            Examples of good questions:
            - "What is the difference between optimistic and zero-knowledge rollups in terms of security guarantees?"
            - "How does the Polkadot relay chain coordinate parachain consensus?"
            - "What are the trade-offs between Layer 1 and Layer 2 scaling solutions?"
            
            Return ONLY a JSON array of objects with "question" and "answer" fields.
            Leave the "answer" field empty since we'll get responses from the bot.
            
            Content to analyze:
            {content_text[:8000]}  # Increased limit for better analysis
            
            Format exactly like this:
            [
                {{"question": "What is the technical difference between...", "answer": ""}},
                {{"question": "How does parallel execution improve...", "answer": ""}},
                {{"question": "What are the security implications of...", "answer": ""}}
            ]
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,  # Slightly higher for more creative questions
                max_tokens=2000
            )
            
            content_response = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            try:
                # Find JSON array in response
                start_idx = content_response.find('[')
                end_idx = content_response.rfind(']') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content_response[start_idx:end_idx]
                    qa_pairs = json.loads(json_str)
                    
                    logger.info(f"Generated {len(qa_pairs)} questions from content")
                    for i, pair in enumerate(qa_pairs):
                        logger.info(f"  Question {i+1}: {pair.get('question', '')[:100]}...")
                    return qa_pairs
                else:
                    logger.error("No valid JSON array found in AI response")
                    return []
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from AI response: {e}")
                logger.error(f"Response content: {content_response}")
                return []
                
        except Exception as e:
            logger.error(f"Error parsing content for analysis: {e}")
            return []
    
    async def fire_questions_sequentially(self, questions: List[str], orchestrator_callback) -> List[Dict]:
        """
        Fire questions sequentially through the orchestrator.
        Returns list of test results.
        """
        results = []
        
        for i, question in enumerate(questions):
            logger.info(f"Firing question {i+1}/{len(questions)}: {question[:50]}...")
            
            try:
                # Call orchestrator to get bot response
                result = await orchestrator_callback(question, i)
                results.append(result)
                
                # Small delay between questions to avoid rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error firing question {i+1}: {e}")
                results.append({
                    "question_index": i,
                    "question": question,
                    "error": str(e),
                    "bot_response": None,
                    "timestamp": asyncio.get_event_loop().time()
                })
        
        return results 