FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    make \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv system wide
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# Create non-root user
RUN groupadd -g 1000 celerygroup \
    && useradd -u 1000 -g celerygroup -m celeryuser \
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
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]