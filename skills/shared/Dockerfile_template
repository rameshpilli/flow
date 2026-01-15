FROM innersource-docker.artifactory.fg.rbc.com/container-hub/python:3.12-linux-amd64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Switch to root to install Redis server
USER root

# Install Redis server
RUN apt-get update && \
    apt-get install -y redis-server && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m pip install --no-cache-dir uv

COPY pyproject.toml /app/
COPY artifacts/ ./artifacts/

ENV UV_INDEX_URL="https://artifactory.fg.rbc.com/artifactory/api/pypi/oss-pypi/simple"

RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN uv pip install -r pyproject.toml

RUN uv pip install \
    https://rbcartifactory.fg.rbc.com/artifactory/pypi-tg40/rbc_security/RBC_Security-2.3.0-py2.py3-none-any.whl

COPY . /app

# Expose both MCP server and Redis ports
EXPOSE 8000 6379

# Start Redis in background, then start MCP server in foreground
CMD ["/bin/sh", "-c", "\
    set -e && \
    echo 'Starting Redis server...' && \
    redis-server --daemonize yes \
        --maxmemory 256mb \
        --maxmemory-policy allkeys-lru \
        --save '' \
        --appendonly no && \
    echo 'Waiting for Redis to start...' && \
    sleep 3 && \
    redis-cli ping > /dev/null 2>&1 && \
    echo 'Redis is ready!' && \
    echo 'Starting Databricks SQL MCP server...' && \
    exec python -m app.main \
    "]
