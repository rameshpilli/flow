import asyncio

import pytest

from agentorchestrator.services.vector_store import (
    InMemoryVectorStore,
    VectorDocument,
    VectorStoreService,
)


@pytest.mark.asyncio
async def test_inmemory_vector_store_add_and_query():
    store = InMemoryVectorStore()
    await store.add_documents([
        VectorDocument(id="a", text="Use async await for IO"),
        VectorDocument(id="b", text="Index tables for SQL performance"),
    ])

    results = await store.query("async IO", top_k=2)
    assert len(results) == 2
    assert results[0].id in {"a", "b"}


@pytest.mark.asyncio
async def test_vector_store_service_defaults_to_memory():
    service = VectorStoreService()
    await service.upsert([
        VectorDocument(id="x", text="Caching with Redis helps performance"),
    ])
    matches = await service.query("Redis", top_k=1)
    assert matches
    assert matches[0].id == "x"

