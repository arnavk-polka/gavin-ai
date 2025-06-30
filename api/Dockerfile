# Stage 1: Dependencies
FROM python:3.11-slim as dependencies

WORKDIR /app

# Set environment variables for optimal performance and better timeouts
ENV SPACY_LOGGING_LEVEL=ERROR \
    TOKENIZERS_PARALLELISM=false \
    HF_HUB_DOWNLOAD_TIMEOUT=900 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_RETRIES=3

# Install system dependencies in one layer
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy and install Python dependencies (this layer will be cached)
COPY requirements.txt .
RUN pip install --retries 3 -r requirements.txt

RUN pip install  "tf-keras"
# Install BLEURT with timeout handling (cached layer)
RUN pip install --timeout 1000 --retries 3 git+https://github.com/google-research/bleurt.git || echo "BLEURT install failed, continuing without it"

# Install spaCy models directly from wheels (cached layer)
RUN pip install  \
    "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl" || \
    echo "Small spaCy model install failed - will use basic extraction"

# Verify spaCy model installation (cached layer)
RUN python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('✅ SpaCy model verified')" || \
    echo "⚠️ SpaCy model verification failed - basic extraction will be used"

# Stage 2: Application
FROM dependencies as application

# Copy application code (only this layer rebuilds on code changes)
COPY . .

CMD ["python", "-m", "main"]
