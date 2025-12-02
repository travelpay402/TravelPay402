# TravelPay402 - Production Dockerfile
# Update 5: With Redis client and cryptographic signing support

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
# libsodium is required for PyNaCl cryptographic operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition and install dependencies
COPY pyproject.toml .
COPY travelpay/ ./travelpay/

# Install the SDK package
RUN pip install --no-cache-dir .

# Create directories
RUN mkdir -p /app/logs /app/data

# Copy site files
COPY travelpay/site/ ./travelpay/site/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "travelpay.site.main:app", "--host", "0.0.0.0", "--port", "8000"]
