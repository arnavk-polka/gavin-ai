FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir git+https://github.com/google-research/bleurt.git

# Set longer timeout for HuggingFace downloads
ENV HF_HUB_DOWNLOAD_TIMEOUT=900

COPY . .

CMD ["python", "-m", "main"]
