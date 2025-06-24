#!/usr/bin/env python3
"""
Debug script for MT-Bench evaluation to help troubleshoot scoring issues.
"""

import asyncio
import os
import sys
import logging
from openai import AsyncOpenAI
from analyze.mt_bench_evaluator import MTBenchEvaluator
from analyze.judge_ai import JudgeAI

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mt_bench_debug.log')
    ]
)

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def debug_single_evaluation():
    """Debug a single evaluation to see the full process."""
    print("=== Debug Single MT-Bench Evaluation ===")
    
    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create evaluator
    evaluator = MTBenchEvaluator(openai_client)
    
    # Test case that might be scoring differently
    question = "What is the main difference between proof-of-work and proof-of-stake consensus mechanisms?"
    response = "Proof-of-work and proof-of-stake are two different consensus mechanisms used in blockchain networks. Proof-of-work requires miners to solve complex mathematical puzzles to validate transactions and create new blocks, consuming significant computational power and energy. In contrast, proof-of-stake allows validators to create blocks based on the amount of cryptocurrency they hold and are willing to stake as collateral, which is more energy-efficient and environmentally friendly."
    expected_answer = "Proof-of-work uses computational puzzles and energy, while proof-of-stake uses staked tokens and is more efficient."
    
    print(f"\nQuestion: {question}")
    print(f"Response: {response}")
    print(f"Expected: {expected_answer}")
    
    # Get the evaluation prompt
    prompt = evaluator._build_evaluation_prompt(question, response, expected_answer=expected_answer)
    print(f"\n=== Evaluation Prompt ===")
    print(prompt)
    
    # Get AI evaluation
    print(f"\n=== Calling AI Judge ===")
    ai_response = await evaluator._get_ai_evaluation(prompt)
    print(f"AI Response: {ai_response}")
    
    # Parse evaluation
    print(f"\n=== Parsing Evaluation ===")
    evaluation = evaluator._parse_evaluation_response(ai_response)
    print(f"Parsed Evaluation: {evaluation}")

async def compare_legacy_vs_mt_bench():
    """Compare legacy vs MT-Bench evaluation for the same response."""
    print("\n=== Comparing Legacy vs MT-Bench ===")
    
    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create both evaluators
    mt_bench_judge = JudgeAI(openai_client, use_mt_bench=True)
    legacy_judge = JudgeAI(openai_client, use_mt_bench=False)
    
    # Test case
    question = "How does Polkadot achieve interoperability between different blockchains?"
    response = "Polkadot achieves interoperability through its unique architecture consisting of a central relay chain and multiple parachains. The relay chain coordinates the network and ensures security, while parachains can have their own specialized functionality and governance. Cross-chain communication is enabled through the Cross-Chain Message Passing (XCMP) protocol, allowing different parachains to exchange data and assets seamlessly."
    expected_answer = "Polkadot uses relay chains and parachains with XCMP for cross-chain communication."
    
    print(f"Question: {question}")
    print(f"Response: {response}")
    print(f"Expected: {expected_answer}")
    
    # MT-Bench evaluation
    print(f"\n--- MT-Bench Evaluation ---")
    mt_result = await mt_bench_judge.evaluate_response(question, response, expected_answer)
    print(f"Overall Score: {mt_result['overall_score']:.3f}")
    print(f"Content Similarity: {mt_result['content_similarity']:.3f}")
    print(f"Style Fidelity: {mt_result['style_fidelity']:.3f}")
    if 'mt_bench_scores' in mt_result:
        print(f"MT-Bench Scores: {mt_result['mt_bench_scores']}")
    
    # Legacy evaluation
    print(f"\n--- Legacy Evaluation ---")
    legacy_result = await legacy_judge.evaluate_response(question, response, expected_answer)
    print(f"Overall Score: {legacy_result['overall_score']:.3f}")
    print(f"Content Similarity: {legacy_result['content_similarity']:.3f}")
    print(f"Style Fidelity: {legacy_result['style_fidelity']:.3f}")
    
    # Comparison
    print(f"\n--- Comparison ---")
    print(f"Score Difference: {mt_result['overall_score'] - legacy_result['overall_score']:.3f}")
    print(f"MT-Bench higher: {mt_result['overall_score'] > legacy_result['overall_score']}")

async def test_batch_evaluation():
    """Test batch evaluation to see how multiple responses are processed."""
    print("\n=== Testing Batch Evaluation ===")
    
    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create evaluator
    evaluator = MTBenchEvaluator(openai_client)
    
    # Test cases
    qa_pairs = [
        {
            "question": "What is blockchain?",
            "answer": "A decentralized digital ledger"
        },
        {
            "question": "How does proof-of-stake work?",
            "answer": "Validators stake tokens to create blocks"
        }
    ]
    
    responses = [
        "Blockchain is a distributed ledger technology that maintains a continuously growing list of records, called blocks, which are linked and secured using cryptography.",
        "Proof-of-stake is a consensus mechanism where validators are chosen to create new blocks based on the amount of cryptocurrency they hold and are willing to stake as collateral."
    ]
    
    print(f"QA Pairs: {qa_pairs}")
    print(f"Responses: {responses}")
    
    # Batch evaluation
    evaluations = await evaluator.evaluate_batch_responses(qa_pairs, responses)
    
    print(f"\nBatch Evaluation Results:")
    for i, evaluation in enumerate(evaluations):
        print(f"Response {i+1}:")
        print(f"  Overall Score: {evaluation.overall_score:.3f}")
        print(f"  Dimension Scores: {evaluation.dimension_scores}")
        print(f"  Strengths: {evaluation.strengths}")
        print(f"  Weaknesses: {evaluation.weaknesses}")
    
    # Calculate aggregate metrics
    metrics = evaluator.calculate_aggregate_metrics(evaluations)
    print(f"\nAggregate Metrics:")
    print(f"Average Overall Score: {metrics['avg_overall_score']:.3f}")
    print(f"Dimension Averages: {metrics['dimension_averages']}")

async def main():
    """Run all debug tests."""
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        return
    
    try:
        await debug_single_evaluation()
        await compare_legacy_vs_mt_bench()
        await test_batch_evaluation()
        
        print("\n=== Debug Complete ===")
        print("Check mt_bench_debug.log for detailed logs")
        
    except Exception as e:
        print(f"Error during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 