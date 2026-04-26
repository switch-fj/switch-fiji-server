FROM python:3.13-slim

# -------------------------
# System dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# Install uv
# -------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh

# -------------------------
# Create user
# -------------------------
RUN groupadd -g 1000 appgroup \
    && useradd -u 1000 -g appgroup -m appuser \
    && mkdir /app \
    && chown -R appuser:appgroup /app

WORKDIR /app

# =========================================================
# 1. COPY ONLY DEPENDENCY FILES (CACHE LAYER OPTIMIZATION)
# =========================================================
COPY pyproject.toml uv.lock /app/

# Install dependencies (this layer is cached unless lockfile changes)
RUN uv sync --frozen --no-dev

# =========================================================
# 2. COPY SOURCE CODE (SEPARATE LAYER)
# =========================================================
COPY . /app

RUN chown -R appuser:appgroup /app

USER appuser

# -------------------------
# Runtime command
# -------------------------
CMD ["sh", "-c", "uvicorn src:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]