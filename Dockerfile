FROM python:3.11-slim

# Install system dependencies (C++ compiler for C extensions like scikit-network)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Increase network download timeout for large wheels (PyTorch/Torchvision)
ENV UV_HTTP_TIMEOUT=300

# Install uv inside the image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency configs first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies into container system
RUN uv sync --frozen --no-cache

# Copy application files
COPY . .

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "src/app.py", "--server.address=0.0.0.0", "--server.port=8501"]