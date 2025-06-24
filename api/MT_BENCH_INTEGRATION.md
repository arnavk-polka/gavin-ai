# MT-Bench Integration for JudgeAI

This document describes the integration of MT-Bench (Hugging Face) evaluation methodology into the JudgeAI system for improved AI response quality assessment.

## Overview

MT-Bench is a comprehensive evaluation framework for AI models that provides standardized assessment across multiple dimensions. This integration enhances the existing JudgeAI evaluation capabilities with more detailed and structured evaluation metrics.

## Architecture

### Files Structure

```
api/analyze/
├── judge_ai.py              # Main JudgeAI class (updated)
├── mt_bench_evaluator.py    # New MT-Bench evaluator
└── orchestrator.py          # Updated to support MT-Bench

api/
├── test_mt_bench.py         # Test script for MT-Bench
└── MT_BENCH_INTEGRATION.md  # This documentation
```

### Key Components

1. **MTBenchEvaluator** (`mt_bench_evaluator.py`)
   - Standalone MT-Bench evaluation implementation
   - Supports single response, batch, and multi-turn evaluation
   - Provides structured evaluation results

2. **JudgeAI** (`judge_ai.py`)
   - Enhanced with MT-Bench integration
   - Backward compatible with legacy evaluation
   - Configurable to use MT-Bench or legacy methods

3. **AnalyzeOrchestrator** (`orchestrator.py`)
   - Updated to support MT-Bench evaluation
   - Configurable through constructor parameter

## MT-Bench Evaluation Dimensions

The MT-Bench evaluator assesses responses across these dimensions:

- **Relevance**: How well does the response address the question?
- **Accuracy**: Is the information factually correct and reliable?
- **Clarity**: Is the response clear, well-structured, and easy to understand?
- **Depth**: Does the response provide sufficient detail and insight?
- **Helpfulness**: How useful and actionable is the response?

## Usage

### Basic Usage

```python
from analyze.judge_ai import JudgeAI
from openai import AsyncOpenAI

# Initialize with MT-Bench enabled (default)
openai_client = AsyncOpenAI(api_key="your-api-key")
judge_ai = JudgeAI(openai_client, use_mt_bench=True)

# Evaluate a single response
evaluation = await judge_ai.evaluate_response(
    question="What is blockchain?",
    bot_response="Blockchain is a distributed ledger technology...",
    expected_answer="A decentralized digital ledger"
)
```

### Direct MT-Bench Usage

```python
from analyze.mt_bench_evaluator import MTBenchEvaluator

evaluator = MTBenchEvaluator(openai_client)

# Single response evaluation
evaluation = await evaluator.evaluate_single_response(
    question="What is blockchain?",
    response="Blockchain is a distributed ledger technology...",
    expected_answer="A decentralized digital ledger"
)

print(f"Overall Score: {evaluation.overall_score}")
print(f"Dimension Scores: {evaluation.dimension_scores}")
```

### Multi-Turn Conversation Evaluation

```python
# Evaluate multi-turn conversation
conversation = [
    {"role": "user", "content": "What is Web3?"},
    {"role": "assistant", "content": "Web3 is the next evolution..."},
    {"role": "user", "content": "How does it differ from Web2?"},
    {"role": "assistant", "content": "Web2 is centralized..."}
]

evaluations = await evaluator.evaluate_multi_turn_conversation(conversation)
```

## Configuration

### Enable/Disable MT-Bench

```python
# Enable MT-Bench (default)
judge_ai = JudgeAI(openai_client, use_mt_bench=True)

# Use legacy evaluation
judge_ai = JudgeAI(openai_client, use_mt_bench=False)
```

### Orchestrator Configuration

```python
# In analyze_routes.py
orchestrator = AnalyzeOrchestrator(
    openai_client=openai_client,
    gavin_bot_handler=create_gavin_bot_handler(),
    use_mt_bench=True  # Enable MT-Bench evaluation
)
```

## Evaluation Results

### MT-Bench Evaluation Structure

```python
@dataclass
class MTBenchEvaluation:
    overall_score: float              # 0-1 overall quality score
    dimension_scores: Dict[str, float] # Individual dimension scores
    reasoning: str                    # Detailed evaluation reasoning
    strengths: List[str]              # Identified strengths
    weaknesses: List[str]             # Identified weaknesses
    confidence: float                 # Evaluation confidence (0-1)
    evaluation_method: str = "mt_bench"
```

### Legacy Compatibility

MT-Bench evaluations are automatically converted to the legacy format for compatibility:

```python
{
    "content_similarity": 0.85,      # Maps to relevance score
    "style_fidelity": 0.78,          # Maps to clarity score
    "overall_score": 0.82,           # Overall quality score
    "mt_bench_scores": {             # Original MT-Bench scores
        "relevance": 0.85,
        "accuracy": 0.90,
        "clarity": 0.78,
        "depth": 0.75,
        "helpfulness": 0.80
    },
    "reasoning": {
        "content_analysis": "Detailed reasoning...",
        "style_analysis": "Style analysis...",
        "strengths": ["strength1", "strength2"],
        "weaknesses": ["weakness1", "weakness2"]
    },
    "evaluation_method": "mt_bench",
    "confidence": 0.85
}
```

## Testing

Run the test script to verify MT-Bench integration:

```bash
cd api
python test_mt_bench.py
```

The test script demonstrates:
- Direct MT-Bench evaluator usage
- JudgeAI integration with MT-Bench
- Multi-turn conversation evaluation
- Result formatting and compatibility

## Benefits

1. **Standardized Evaluation**: MT-Bench provides industry-standard evaluation metrics
2. **Multi-Dimensional Assessment**: Evaluates responses across 5 key dimensions
3. **Detailed Feedback**: Provides strengths, weaknesses, and reasoning
4. **Backward Compatibility**: Existing code continues to work unchanged
5. **Configurable**: Can be enabled/disabled as needed
6. **Comprehensive**: Supports single, batch, and multi-turn evaluation

## Migration Guide

### From Legacy to MT-Bench

1. **No Code Changes Required**: Existing code automatically uses MT-Bench when enabled
2. **Enhanced Results**: Additional dimension scores and detailed feedback
3. **Improved Accuracy**: More structured and comprehensive evaluation methodology

### Disabling MT-Bench

If you need to revert to legacy evaluation:

```python
# In analyze_routes.py
orchestrator = AnalyzeOrchestrator(
    openai_client=openai_client,
    gavin_bot_handler=create_gavin_bot_handler(),
    use_mt_bench=False  # Disable MT-Bench
)
```

## Performance Considerations

- MT-Bench evaluations may take slightly longer due to more comprehensive prompts
- Rate limiting is implemented to avoid API quota issues
- Fallback to legacy evaluation if MT-Bench fails
- Batch evaluation optimizes API calls for multiple responses

## Future Enhancements

Potential improvements for the MT-Bench integration:

1. **Custom Dimensions**: Allow configuration of evaluation dimensions
2. **Model Selection**: Support different evaluation models
3. **Caching**: Cache evaluation results for repeated queries
4. **A/B Testing**: Compare MT-Bench vs legacy evaluation results
5. **Dashboard Integration**: Enhanced UI for MT-Bench metrics 