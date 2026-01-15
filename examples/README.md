# Memory Store Examples

Example code demonstrating how to use the Memory Store client.

## Running Examples

### Prerequisites

1. **Start Memory Store**:
   ```bash
   cd memory_store
   docker-compose up -d
   ```

2. **Verify it's running**:
   ```bash
   curl http://localhost:8000/health
   ```

### Run All Examples

```bash
# Install dependencies
pip install -e .

# Run examples
python examples/basic_usage.py
```

### Run Individual Examples

```python
import asyncio
from memory_store.client import MemoryStoreClient

async def my_example():
    memory = MemoryStoreClient(
        base_url="http://localhost:8000",
        agent_id="my_agent"
    )
    
    # Add memory
    await memory.add_memory("Test memory")
    
    # Search
    results = await memory.search_memories("test")
    print(results)
    
    await memory.close()

asyncio.run(my_example())
```

## Examples Included

### 1. Basic Operations (`basic_usage.py`)
- Health checks
- Adding memories
- Searching memories
- Getting all memories

### 2. Context Manager Usage
- Automatic connection management
- Clean resource cleanup

### 3. Metadata and Organization
- Adding rich metadata
- Organizing memories by category
- Filtering results

### 4. Team Memory Sharing
- Personal agent memory
- Shared team memory
- Memory isolation between agents

### 5. Error Handling
- Robust error handling
- Graceful degradation
- Health check patterns

## Integration Examples

See [../INTEGRATION.md](../INTEGRATION.md) for complete integration guides with AgentOrchestrator.

## Troubleshooting

### Cannot connect to service

```bash
# Check service is running
docker-compose ps

# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs memory-store
```

### Operations failing

```bash
# Check Cohere API key is set
docker-compose exec memory-store env | grep COHERE

# Check Qdrant connection
docker-compose exec memory-store curl http://qdrant:6333/healthz
```

## Next Steps

1. Try the basic examples
2. Adapt code for your use case
3. Read [USER_GUIDE.md](../USER_GUIDE.md) for connection details
4. Read [INTEGRATION.md](../INTEGRATION.md) for AgentOrchestrator integration
