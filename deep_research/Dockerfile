# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for compiling Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the package definition first (layer-cache friendly)
COPY agentorchestrator/setup.py agentorchestrator/setup.cfg* agentorchestrator/pyproject.toml* ./agentorchestrator/
COPY agentorchestrator/ ./agentorchestrator/

# Install the framework with MCP extras, plus the web server
RUN pip install --no-cache-dir --prefix=/install \
    "./agentorchestrator[mcp]" \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "httpx>=0.27.0" \
    "pyjwt>=2.8.0"


# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="Deep Research Agent"
LABEL org.opencontainers.image.description="AgentOrchestrator-based multi-source research agent"

# Non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY deep_research/ ./deep_research/

# Ownership
RUN chown -R appuser:appgroup /app
USER appuser

# Expose the service port
EXPOSE 8000

# Health check — maps to the /live endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/live || exit 1

# Default command — override WORKERS in your Kubernetes env
CMD ["uvicorn", "deep_research.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
