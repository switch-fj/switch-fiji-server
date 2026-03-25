FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    make \                
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 celerygroup \
    && useradd -u 1000 -g celerygroup celeryuser \
    && mkdir /app \
    && chown -R celeryuser:celerygroup /app

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy source code
COPY . /app
RUN chown -R celeryuser:celerygroup /app

# Switch to non-root user
USER celeryuser

# Default command
CMD ["make", "prod"]