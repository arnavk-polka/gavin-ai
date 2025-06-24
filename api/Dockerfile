FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install mem0ai[graph] separately
RUN pip install --no-cache-dir "mem0ai[graph]"
RUN pip install --no-cache-dir "chromadb"

COPY . .

CMD ["python", "-m", "main"]
