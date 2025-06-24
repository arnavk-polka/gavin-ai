#!/usr/bin/env python3
"""
Test script for content analysis functionality.
"""

import asyncio
import logging
from openai import AsyncOpenAI
from analyze.tester_ai import TesterAI
from analyze.judge_ai import JudgeAI
from analyze.mt_bench_evaluator import MTBenchEvaluator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_content_analysis():
    """Test the content analysis pipeline."""
    
    # Initialize components
    openai_client = AsyncOpenAI(api_key="your-api-key-here")  # Replace with actual key
    tester_ai = TesterAI(openai_client)
    mt_bench_evaluator = MTBenchEvaluator(openai_client)
    judge_ai = JudgeAI(openai_client, use_mt_bench=True)
    
    # Test content
    test_content = """
    Polkadot is a next-generation blockchain protocol that enables cross-blockchain transfers of any type of data or asset, not just tokens. 
    By connecting to Polkadot, blockchains can achieve security and message passing capabilities. 
    Polkadot is designed to provide a foundation for a decentralized internet of blockchains, also known as Web3.
    
    The Polkadot network uses a sophisticated governance mechanism that is on-chain and forkless. 
    All DOT token holders can participate in governance by voting on referenda, proposing new referenda, or becoming a council member.
    
    Parachains are sovereign blockchains that can have their own tokens and optimize their functionality for specific use cases. 
    They connect to the Polkadot network through the relay chain, which provides shared security and cross-chain messaging.
    """
    
    print("=== Testing Content Analysis ===")
    print(f"Test content: {test_content[:200]}...")
    
    # Step 1: Parse content for questions
    print("\n1. Parsing content for questions...")
    qa_pairs = await tester_ai.parse_content_for_analysis(test_content)
    print(f"Generated {len(qa_pairs)} QA pairs:")
    for i, pair in enumerate(qa_pairs):
        print(f"  Q{i+1}: {pair.get('question', '')}")
        print(f"  A{i+1}: {pair.get('answer', '')}")
    
    # Step 2: Extract questions
    print("\n2. Extracting questions...")
    questions = await tester_ai.extract_questions_from_qa_pairs(qa_pairs)
    print(f"Extracted {len(questions)} questions:")
    for i, question in enumerate(questions):
        print(f"  {i+1}: {question}")
    
    # Step 3: Simulate bot responses
    print("\n3. Simulating bot responses...")
    test_results = []
    for i, question in enumerate(questions):
        # Simulate a bot response
        bot_response = f"This is a simulated response to question {i+1} about {question[:50]}..."
        test_results.append({
            "question_index": i,
            "question": question,
            "bot_response": bot_response,
            "timestamp": asyncio.get_event_loop().time(),
            "status": "success"
        })
        print(f"  Response {i+1}: {bot_response[:100]}...")
    
    # Step 4: Evaluate responses
    print("\n4. Evaluating responses...")
    evaluated_results = await judge_ai.batch_evaluate(test_results, qa_pairs)
    print(f"Evaluated {len(evaluated_results)} results:")
    for i, result in enumerate(evaluated_results):
        if result.get("evaluation"):
            eval_data = result["evaluation"]
            print(f"  Result {i+1}: Score={eval_data.get('overall_score', 0):.3f}, Method={eval_data.get('evaluation_method', 'unknown')}")
            if eval_data.get('evaluation_method') == 'mt_bench':
                mt_scores = eval_data.get('mt_bench_scores', {})
                print(f"    MT-Bench scores: {mt_scores}")
    
    # Step 5: Calculate metrics
    print("\n5. Calculating aggregate metrics...")
    aggregate_metrics = judge_ai.calculate_aggregate_metrics(evaluated_results)
    print(f"Aggregate metrics: {aggregate_metrics}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_content_analysis()) 