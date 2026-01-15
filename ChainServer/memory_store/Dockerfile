# ═══════════════════════════════════════════════════════════════════════════════
#                       Memory Store Service - Production Image
# ═══════════════════════════════════════════════════════════════════════════════

# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY memory_store/ ./memory_store/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e .

# Create non-root user
RUN useradd -m -u 1000 memorystore && \
    chown -R memorystore:memorystore /app

# Switch to non-root user
USER memorystore

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the service
CMD ["memory-store", "--host", "0.0.0.0", "--port", "8000"]
