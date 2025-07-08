import logging
import os
import asyncio
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI
from mem0 import Memory
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import threading
from typing import List, Dict, Any, Optional, Tuple, Union
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('main')

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define static path
static_path = os.path.join(os.path.dirname(__file__), "static")
logger.info(f"Static path set to: {static_path}")

# Mount static files if directory exists
if os.path.isdir(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    logger.info("Mounted staticfiles directory")
else:
    logger.warning(f"Static directory {static_path} does not exist")

# Global variables for model management
_embedder = None
_embedder_lock = threading.Lock()
_model_ready = asyncio.Event()

def get_embedder():
    """Thread-safe getter for the sentence transformer model."""
    global _embedder
    
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                logger.info("Initializing sentence transformer model...")
                try:
                    _embedder = SentenceTransformer(
                        'nomic-ai/nomic-embed-text-v1',
                        trust_remote_code=True,
                    )
                    logger.info("Successfully loaded nomic-ai/nomic-embed-text-v1 embedder.")
                except Exception as e:
                    logger.error(f"Failed to load nomic-ai/nomic-embed-text-v1 embedder: {e}")
                    raise e
    
    return _embedder

async def ensure_model_ready():
    """Wait for the model to be ready before proceeding."""
    await _model_ready.wait()
    return get_embedder()

def initialize_model(loop=None):
    """Initialize the model in a background thread and set the ready event."""
    global _embedder
    try:
        _embedder = get_embedder()
        # Set the model ready event in the event loop
        if loop:
            loop.call_soon_threadsafe(_model_ready.set)
        logger.info("Model initialization completed and ready for use.")
    except Exception as e:
        logger.error(f"Failed to initialize model: {e}")
        raise e

# Initialize OpenAI client
openai_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_TOKEN")
if not openai_api_key:
    logger.error("OPENAI_API_KEY or OPENAI_TOKEN environment variable not set.")
    raise ValueError("OPENAI_API_KEY or OPENAI_TOKEN environment variable not set.")

openai_client = AsyncOpenAI(api_key=openai_api_key)

# Initialize Mem0 with proper configuration
# MEM0_API_KEY is optional for self-hosted version
mem0_api_key = os.getenv("MEM0_API_KEY", "")
if mem0_api_key:
    logger.info("Using MEM0_API_KEY for hosted version")
else:
    logger.info("No MEM0_API_KEY - using self-hosted mem0 configuration")

# Initialize SERPER API key (optional - only needed for web search)
serper_api_key = os.getenv("SERPER_API_KEY", None)
if not serper_api_key:
    logger.warning("SERPER_API_KEY environment variable not set. Web search functionality will be disabled.")

# Configure Mem0 with async-aware embedder
class AsyncEmbedder:
    def __init__(self):
        self._ready = False
    
    async def encode(self, sentences, **kwargs):
        if not self._ready:
            model = await ensure_model_ready()
            self._ready = True
        else:
            model = get_embedder()
        return model.encode(sentences, **kwargs)

async_embedder = AsyncEmbedder()

# Configure Mem0 with simple memory configuration only (graph implementation commented out)
# GRAPH CONFIGURATION COMMENTED OUT
# use_graph_memory = os.getenv("USE_GRAPH_MEMORY", "true").lower() == "true"
# neo4j_password = os.getenv("NEO4J_PASSWORD", "")

# if use_graph_memory and neo4j_password:
#     logger.info("Using full graph memory configuration with Neo4j")
#     mem0_config = {
#         "graph_store": {
#             "provider": "neo4j",
#             "config": {
#                 "url": os.getenv("NEO4J_URL", "bolt://localhost:7687"),
#                 "username": os.getenv("NEO4J_USERNAME", "neo4j"),
#                 "password": neo4j_password,
#                 "database": os.getenv("NEO4J_DATABASE", "neo4j")
#             }
#         },
#         "llm": {
#             "provider": "openai",
#             "config": {
#                 "model": "gpt-4o",
#                 "api_key": openai_api_key
#             }
#         },
#         "embedder": {
#             "provider": "openai",
#             "config": {
#                 "model": "text-embedding-ada-002",
#                 "api_key": openai_api_key,
#                 "embedding_dims": 1536
#             }
#         }
#     }
# else:

logger.info("Using simple memory configuration - graph implementation disabled")

# Try basic mem0 initialization first
try:
    if mem0_api_key:
        # Use hosted version if API key provided
        from mem0 import MemoryClient
        mem0_client = MemoryClient(api_key=mem0_api_key)
        logger.info("Initialized Mem0 with hosted API")
    else:
        # Use self-hosted version
        mem0_config = {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o",
                    "api_key": openai_api_key
                }
            }
        }
        mem0_client = Memory.from_config(config_dict=mem0_config)
        logger.info("Initialized Mem0 with self-hosted configuration")
except Exception as e:
    logger.error(f"Error initializing mem0: {e}")
    # Fallback to basic Memory initialization
    try:
        mem0_client = Memory()
        logger.info("Initialized Mem0 with default configuration")
    except Exception as e2:
        logger.error(f"Failed to initialize mem0 with any configuration: {e2}")
        raise e2
# GRAPH CONFIGURATION COMMENTED OUT
# logger.info(f"Neo4j URL: {os.getenv('NEO4J_URL', 'bolt://localhost:7687')}")
# logger.info(f"Neo4j Username: {os.getenv('NEO4J_USERNAME', 'neo4j')}")
# logger.info(f"Neo4j Database: {os.getenv('NEO4J_DATABASE', 'neo4j')}")

# Seed initial memories for Gavin Wood
initial_memories = [
    "Gavin Wood is the founder of Polkadot and co-founder of Ethereum, known for his work on blockchain architecture and Web3 infrastructure.",
    "Gavin Wood created the Solidity programming language and wrote the Ethereum Yellow Paper.",
    "Gavin Wood is focused on building interoperable blockchain networks and advancing Web3 technology.",
]

async def seed_memories():
    """Seed initial memories, but only after model is ready."""
    try:
        # Wait for model to be ready first
        await ensure_model_ready()
        # Import locally to avoid circular import
        from utils.utils import add_memory
        
        logger.info("Starting memory seeding...")
        success_count = 0
        for i, memory in enumerate(initial_memories):
            try:
                result = add_memory(mem0_client, "gavinwood", memory, {"type": "persona_fact"})
                if result:
                    success_count += 1
                    logger.info(f"Successfully seeded memory {i+1}/{len(initial_memories)}")
                else:
                    logger.error(f"Failed to seed memory {i+1}: {memory[:50]}...")
            except Exception as e:
                logger.error(f"Error seeding memory {i+1}: {e}")
        
        logger.info(f"Memory seeding completed: {success_count}/{len(initial_memories)} memories added")
    except Exception as e:
        logger.error(f"Error in seed_memories function: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

@app.on_event("startup")
async def startup_event():
    """Initialize everything needed for the application."""
    # Get the current event loop
    loop = asyncio.get_event_loop()
    # Start model initialization in a background thread
    threading.Thread(target=initialize_model, args=(loop,), daemon=True).start()
    # Seed initial memories in background
    asyncio.create_task(seed_memories())
    logger.info("Application startup tasks initiated. Model loading and memory seeding in background.")