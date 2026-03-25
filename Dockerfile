FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 celerygroup \
    && useradd -u 1000 -g celerygroup celeryuser \
    && mkdir /app \
    && chown -R celeryuser:celerygroup /app

WORKDIR /app

# Copy dependencies
COPY requirements.txt /app/

# Upgrade pip and install Python packages
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . /app
RUN chown -R celeryuser:celerygroup /app

# Switch to non-root user
USER celeryuser

# Default command
CMD ["sh", "-c", "uvicorn src:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
