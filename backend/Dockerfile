FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

# Copy backend application files
COPY app ./app
COPY data ./data
COPY scripts ./scripts
COPY tests ./tests

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/storage/kg.db \
    ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000,http://localhost

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
