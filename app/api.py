"""
Memory Store REST API

FastAPI-based REST API for multi-agent memory operations.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_config
from app.service import MemoryStoreService

logger = logging.getLogger(__name__)

# Global service instance
_memory_service: MemoryStoreService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global _memory_service

    # Startup
    logger.info("Starting Memory Store API...")
    config = get_config()
    _memory_service = MemoryStoreService(config)
    logger.info("Memory Store API started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Memory Store API...")
    _memory_service = None


# Create FastAPI app
app = FastAPI(
    title="Memory Store API",
    description="Multi-agent memory management service with mem0 and Cohere Compass",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
config = get_config()
if config.service.cors_enabled:
    origins = (
        config.service.cors_origins.split(",")
        if config.service.cors_origins != "*"
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
#                              REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class AddMemoryRequest(BaseModel):
    """Request to add a memory."""

    agent_id: str = Field(..., description="Unique agent identifier")
    messages: str | list[dict[str, str]] = Field(..., description="Messages to remember")
    metadata: dict[str, Any] | None = Field(
        None, description="Optional metadata"
    )


class GetMemoriesRequest(BaseModel):
    """Request to get memories."""

    agent_id: str = Field(..., description="Unique agent identifier")
    query: str | None = Field(None, description="Optional semantic search query")
    limit: int | None = Field(None, description="Maximum number of results")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata filters")


class UpdateMemoryRequest(BaseModel):
    """Request to update a memory."""

    agent_id: str = Field(..., description="Unique agent identifier")
    memory_id: str = Field(..., description="Memory ID to update")
    data: str | dict[str, Any] = Field(..., description="New memory data")


class DeleteMemoryRequest(BaseModel):
    """Request to delete a memory."""

    agent_id: str = Field(..., description="Unique agent identifier")
    memory_id: str = Field(..., description="Memory ID to delete")


class DeleteAllMemoriesRequest(BaseModel):
    """Request to delete all memories for an agent."""

    agent_id: str = Field(..., description="Unique agent identifier")


class MemoryHistoryRequest(BaseModel):
    """Request to get memory history."""

    agent_id: str = Field(..., description="Unique agent identifier")
    memory_id: str = Field(..., description="Memory ID")


class HealthResponse(BaseModel):
    """Health check response."""

    service: str
    status: str
    components: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                              API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/", tags=["General"])
async def root():
    """Root endpoint."""
    return {
        "service": "Memory Store API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """Health check endpoint."""
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        health_status = await _memory_service.health_check()
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "service": "memory_store",
                "status": "unhealthy",
                "error": str(e),
            },
        )


@app.post("/memories", tags=["Memory Operations"])
async def add_memory(request: AddMemoryRequest):
    """
    Add a memory for a specific agent.

    This creates a new memory entry that can be semantically searched later.
    """
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        result = _memory_service.add_memory(
            agent_id=request.agent_id,
            messages=request.messages,
            metadata=request.metadata,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add memory: {str(e)}",
        )


@app.post("/memories/search", tags=["Memory Operations"])
async def get_memories(request: GetMemoriesRequest):
    """
    Search or retrieve memories for a specific agent.

    Supports both semantic search (with query) and retrieval of all memories.
    """
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        memories = _memory_service.get_memories(
            agent_id=request.agent_id,
            query=request.query,
            limit=request.limit,
            metadata=request.metadata,
        )
        return {"success": True, "memories": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to get memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memories: {str(e)}",
        )


@app.put("/memories", tags=["Memory Operations"])
async def update_memory(request: UpdateMemoryRequest):
    """Update an existing memory."""
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        result = _memory_service.update_memory(
            agent_id=request.agent_id,
            memory_id=request.memory_id,
            data=request.data,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to update memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory: {str(e)}",
        )


@app.delete("/memories", tags=["Memory Operations"])
async def delete_memory(request: DeleteMemoryRequest):
    """Delete a specific memory."""
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        result = _memory_service.delete_memory(
            agent_id=request.agent_id, memory_id=request.memory_id
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}",
        )


@app.delete("/memories/all", tags=["Memory Operations"])
async def delete_all_memories(request: DeleteAllMemoriesRequest):
    """Delete all memories for a specific agent."""
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        result = _memory_service.delete_all_memories(agent_id=request.agent_id)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to delete all memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete all memories: {str(e)}",
        )


@app.get("/memories/{agent_id}/{memory_id}/history", tags=["Memory Operations"])
async def get_memory_history(agent_id: str, memory_id: str):
    """Get the version history of a memory."""
    if not _memory_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service not initialized",
        )

    try:
        history = _memory_service.get_memory_history(
            agent_id=agent_id, memory_id=memory_id
        )
        return {"success": True, "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Failed to get memory history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory history: {str(e)}",
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config.service.host,
        port=config.service.port,
        log_level=config.service.log_level.lower(),
    )
