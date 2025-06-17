import logging
import os
import asyncio
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI
from mem0 import MemoryClient
from utils import add_memory
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import threading

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
mem0_api_key = os.getenv("MEM0_API_KEY", None)
if not mem0_api_key:
    logger.error("MEM0_API_KEY environment variable not set.")
    raise ValueError("MEM0_API_KEY environment variable not set.")

mem0_client = MemoryClient(api_key=mem0_api_key)

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

# Configure Mem0 with async-aware embedder  
mem0_config = {
    "vector_store": {
        "provider": "in_memory",
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o",
    },
    "embedder": {
        "provider": "custom",
        "model": async_embedder
    }
}

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
        for memory in initial_memories:
            add_memory(mem0_client, "gavinwood", memory, {"type": "persona_fact"})
        logger.info("Seeded initial memories for Gavin Wood.")
    except Exception as e:
        logger.error(f"Error seeding memories: {e}")

@app.on_event("startup")
async def startup_event():
    """Initialize everything needed for the application."""
    # Get the current event loop
    loop = asyncio.get_event_loop()
    # Start model initialization in a background thread
    threading.Thread(target=initialize_model, args=(loop,), daemon=True).start()
    # Skip memory seeding for faster startup - memories will be created as needed
    logger.info("Application startup tasks initiated. Model loading in background.")