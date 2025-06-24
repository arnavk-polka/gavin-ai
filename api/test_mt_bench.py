#!/usr/bin/env python3
"""
Test script for MT-Bench integration with JudgeAI.
Demonstrates the new evaluation capabilities.
"""

import asyncio
import os
import sys
from openai import AsyncOpenAI
from analyze.mt_bench_evaluator import MTBenchEvaluator, MTBenchEvaluation
from analyze.judge_ai import JudgeAI

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_mt_bench_evaluator():
    """Test the MT-Bench evaluator directly."""
    print("=== Testing MT-Bench Evaluator ===")
    
    # Initialize OpenAI client (you'll need to set OPENAI_API_KEY)
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create MT-Bench evaluator
    evaluator = MTBenchEvaluator(openai_client)
    
    # Test single response evaluation
    question = "What is the difference between proof-of-work and proof-of-stake?"
    response = "Proof-of-work and proof-of-stake are two different consensus mechanisms used in blockchain networks. Proof-of-work requires miners to solve complex mathematical puzzles to validate transactions and create new blocks, while proof-of-stake allows validators to create blocks based on the amount of cryptocurrency they hold and are willing to stake as collateral."
    expected_answer = "Proof-of-work uses computational puzzles for consensus, while proof-of-stake uses staked tokens."
    
    print(f"Question: {question}")
    print(f"Response: {response}")
    print(f"Expected: {expected_answer}")
    print("\nEvaluating with MT-Bench...")
    
    evaluation = await evaluator.evaluate_single_response(
        question=question,
        response=response,
        expected_answer=expected_answer
    )
    
    print(f"\nMT-Bench Evaluation Results:")
    print(f"Overall Score: {evaluation.overall_score:.2f}")
    print(f"Dimension Scores:")
    for dim, score in evaluation.dimension_scores.items():
        print(f"  {dim}: {score:.2f}")
    print(f"Confidence: {evaluation.confidence:.2f}")
    print(f"Reasoning: {evaluation.reasoning}")
    print(f"Strengths: {evaluation.strengths}")
    print(f"Weaknesses: {evaluation.weaknesses}")

async def test_judge_ai_integration():
    """Test the JudgeAI integration with MT-Bench."""
    print("\n=== Testing JudgeAI with MT-Bench Integration ===")
    
    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create JudgeAI with MT-Bench enabled
    judge_ai = JudgeAI(openai_client, use_mt_bench=True)
    
    # Test single response evaluation
    question = "How does Polkadot achieve interoperability?"
    response = "Polkadot achieves interoperability through its unique architecture that consists of a central relay chain and multiple parachains. The relay chain coordinates the network and ensures security, while parachains can have their own specialized functionality and governance. Cross-chain communication is enabled through the Cross-Chain Message Passing (XCMP) protocol, allowing different parachains to exchange data and assets seamlessly."
    expected_answer = "Polkadot uses relay chains and parachains with XCMP for cross-chain communication."
    
    print(f"Question: {question}")
    print(f"Response: {response}")
    print(f"Expected: {expected_answer}")
    print("\nEvaluating with JudgeAI (MT-Bench enabled)...")
    
    evaluation = await judge_ai.evaluate_response(question, response, expected_answer)
    
    print(f"\nJudgeAI Evaluation Results:")
    print(f"Overall Score: {evaluation['overall_score']:.2f}")
    print(f"Content Similarity: {evaluation['content_similarity']:.2f}")
    print(f"Style Fidelity: {evaluation['style_fidelity']:.2f}")
    print(f"Evaluation Method: {evaluation['evaluation_method']}")
    if 'mt_bench_scores' in evaluation:
        print(f"MT-Bench Dimension Scores:")
        for dim, score in evaluation['mt_bench_scores'].items():
            print(f"  {dim}: {score:.2f}")
    print(f"Reasoning: {evaluation['reasoning']['content_analysis']}")

async def test_multi_turn_evaluation():
    """Test multi-turn conversation evaluation."""
    print("\n=== Testing Multi-Turn Evaluation ===")
    
    # Initialize OpenAI client
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create JudgeAI with MT-Bench enabled
    judge_ai = JudgeAI(openai_client, use_mt_bench=True)
    
    # Simulate a multi-turn conversation
    conversation = [
        {"role": "user", "content": "What is Web3?"},
        {"role": "assistant", "content": "Web3 is the next evolution of the internet, built on blockchain technology. It aims to create a decentralized web where users have ownership and control over their data and digital assets."},
        {"role": "user", "content": "How does it differ from Web2?"},
        {"role": "assistant", "content": "Web2 is centralized, controlled by big tech companies who own user data. Web3 is decentralized, giving users control over their data and enabling peer-to-peer interactions without intermediaries."}
    ]
    
    print("Multi-turn conversation:")
    for msg in conversation:
        print(f"{msg['role'].capitalize()}: {msg['content']}")
    
    print("\nEvaluating multi-turn responses...")
    
    # Evaluate the assistant responses
    for i, msg in enumerate(conversation):
        if msg["role"] == "assistant":
            user_message = conversation[i-1]["content"] if i > 0 else ""
            conversation_history = conversation[:i]
            
            evaluation = await judge_ai.evaluate_multi_turn_response(
                user_message, 
                msg["content"], 
                conversation_history
            )
            
            print(f"\nResponse {i//2 + 1} Evaluation:")
            print(f"Overall Score: {evaluation['overall_score']:.2f}")
            print(f"Relevance: {evaluation['relevance_score']:.2f}")
            print(f"Consistency: {evaluation['consistency_score']:.2f}")
            print(f"Technical: {evaluation['technical_score']:.2f}")
            print(f"Clarity: {evaluation['clarity_score']:.2f}")
            print(f"Persona: {evaluation['persona_score']:.2f}")
            print(f"Method: {evaluation['evaluation_method']}")

async def main():
    """Run all tests."""
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        return
    
    try:
        await test_mt_bench_evaluator()
        await test_judge_ai_integration()
        await test_multi_turn_evaluation()
        
        print("\n=== All tests completed successfully! ===")
        print("MT-Bench integration is working correctly.")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 