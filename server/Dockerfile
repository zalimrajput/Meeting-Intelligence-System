# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PORT=8000

# Install system dependencies including FFmpeg for audio preprocessing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency definitions
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --retries 10 --timeout 300 -r requirements.txt

# Copy application source code
COPY . .

# Create directory for local storage uploads
RUN mkdir -p /app/storage_uploads

# Expose server port
EXPOSE 8000

# Run FastAPI application with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
