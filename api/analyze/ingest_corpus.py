#!/usr/bin/env python3
"""Corpus ingestion script for processing JSONL files through spaCy pipeline."""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Iterator, Dict, Any

from spacy_pipeline import get_nlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_jsonl(file_path: Path) -> Iterator[Dict[str, Any]]:
    """Load and yield lines from JSONL file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    if 'text' not in data:
                        logger.warning(f"Line {line_num}: Missing 'text' field, skipping")
                        continue
                    yield data
                except json.JSONDecodeError as e:
                    logger.error(f"Line {line_num}: JSON decode error - {e}")
                    continue
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise


def extract_texts(data_stream: Iterator[Dict[str, Any]]) -> Iterator[str]:
    """Extract text content from data stream."""
    for item in data_stream:
        yield item['text']


def process_corpus(input_path: Path, batch_size: int = 32, mem0_client=None) -> None:
    """Process JSONL corpus through spaCy pipeline with progress logging."""
    
    logger.info(f"Starting corpus ingestion from: {input_path}")
    logger.info(f"Batch size: {batch_size}")
    
    # Initialize spaCy pipeline
    logger.info("Loading spaCy pipeline...")
    nlp = get_nlp(mem0_client=mem0_client)
    logger.info(f"Pipeline loaded with components: {nlp.pipe_names}")
    
    # Load data stream
    data_stream = load_jsonl(input_path)
    text_stream = extract_texts(data_stream)
    
    # Process in batches
    processed_count = 0
    start_time = time.time()
    
    try:
        for doc_batch in nlp.pipe(text_stream, batch_size=batch_size):
            processed_count += 1
            
            # Log progress every 1000 documents
            if processed_count % 1000 == 0:
                elapsed = time.time() - start_time
                rate = processed_count / elapsed
                logger.info(f"Processed {processed_count:,} documents "
                          f"({rate:.1f} docs/sec)")
        
        # Final summary
        total_time = time.time() - start_time
        avg_rate = processed_count / total_time if total_time > 0 else 0
        
        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info(f"Total documents processed: {processed_count:,}")
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Average rate: {avg_rate:.1f} documents/second")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info(f"\nIngestion interrupted. Processed {processed_count:,} documents.")
        raise
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        logger.info(f"Processed {processed_count:,} documents before error.")
        raise


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Ingest JSONL corpus through spaCy pipeline for embedding storage",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Path to input JSONL file with 'text' and 'source' fields"
    )
    
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=32,
        help="Batch size for spaCy processing"
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.input.exists():
        logger.error(f"Input file does not exist: {args.input}")
        return 1
    
    if not args.input.suffix == '.jsonl':
        logger.warning(f"Input file doesn't have .jsonl extension: {args.input}")
    
    # Validate batch size
    if args.batch < 1:
        logger.error("Batch size must be positive")
        return 1
    
    try:
        # Note: mem0_client would need to be initialized here
        # For now, passing None - VectorExporter will handle gracefully
        process_corpus(args.input, args.batch, mem0_client=None)
        return 0
    except KeyboardInterrupt:
        return 130  # Standard exit code for Ctrl+C
    except Exception as e:
        logger.error(f"Script failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 