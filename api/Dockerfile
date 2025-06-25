FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install mem0ai[graph] separately
RUN pip install --no-cache-dir "mem0ai[graph]"
RUN pip install --no-cache-dir "chromadb"
# Install git for BLEURT dependency
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install BLEURT dependencies
RUN pip install --no-cache-dir "evaluate"
RUN pip install --no-cache-dir "tf-keras"
RUN pip install --no-cache-dir git+https://github.com/google-research/bleurt.git

# Set longer timeout for HuggingFace downloads
ENV HF_HUB_DOWNLOAD_TIMEOUT=900

COPY . .

CMD ["python", "-m", "main"]
