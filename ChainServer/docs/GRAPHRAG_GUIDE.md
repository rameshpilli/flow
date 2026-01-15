# GraphRAG with Memgraph - Setup Guide

Complete guide for enabling relationship-based memory using Memgraph graph store.

## What is GraphRAG?

**GraphRAG** (Graph Retrieval Augmented Generation) stores memories as a knowledge graph, enabling:

- 🔗 **Relationship Discovery**: Understand how entities connect
- 🧠 **Multi-hop Reasoning**: Follow chains of relationships
- 📊 **Entity Recognition**: Automatic extraction of people, places, concepts
- 🔍 **Complex Queries**: Find patterns across memories

## Why Memgraph?

**Memgraph** is an open-source, high-performance graph database:

- ✅ **Open Source**: Apache 2.0 license, no vendor lock-in
- ✅ **Fast**: In-memory graph processing
- ✅ **Compatible**: Uses Bolt protocol (same as Neo4j)
- ✅ **Lightweight**: Easy to deploy and manage
- ✅ **Modern**: Built for streaming and real-time analytics

**vs Neo4j:**
- Memgraph: Fully open source
- Neo4j: Community edition limitations, enterprise features paywall

## Architecture with GraphRAG

```
Memory Store Service
       │
       ├─→ Cohere (Embeddings)
       │      ↓
       ├─→ Qdrant (Vector Search) ← Semantic similarity
       │      ↓
       └─→ Memgraph (Graph Store) ← Relationships
              ↓
      Knowledge Graph:
      
      (User)─[PREFERS]→(Python)
         │
         └─[ASKED_ABOUT]→(AAPL)─[IS_A]→(Stock)
                            │
                            └─[HAS_METRIC]→(Revenue)
```

## Setup Instructions

### Option 1: Docker Compose (Local Development)

**Enable Memgraph:**

```bash
cd memory_store

# Edit .env
cat >> .env <<EOF
# Enable GraphRAG
MEM0_GRAPH_STORE_ENABLED=true
MEM0_GRAPH_STORE_PROVIDER=memgraph

# Memgraph connection
MEMGRAPH_HOST=memgraph
MEMGRAPH_PORT=7687
EOF

# Start with Memgraph profile
docker-compose --profile graph up -d

# Or edit docker-compose.yml and remove the "profiles: - graph" line
# from the memgraph service, then:
docker-compose up -d
```

**Verify it's running:**

```bash
# Check containers
docker-compose ps

# Should show:
# - memory-store-service
# - memory-store-qdrant
# - memory-store-memgraph

# Test Memgraph connection
docker-compose exec memgraph mgconsole
```

### Option 2: Kubernetes

**Enable Memgraph:**

```bash
cd memory_store/k8s

# 1. Edit kustomization.yaml, uncomment:
# - memgraph-deployment.yaml

# 2. Edit configmap.yaml, set:
MEM0_GRAPH_STORE_ENABLED: "true"

# 3. Deploy
kubectl apply -k .

# 4. Verify
kubectl get pods -n memory-store | grep memgraph
kubectl logs -n memory-store -l app=memgraph
```

## Using GraphRAG

### Example: Building Knowledge Graph

```python
from memory_store.client import MemoryStoreClient

memory = MemoryStoreClient(
    base_url="http://localhost:8000",
    agent_id="research_agent"
)

# Add memories - entities and relationships extracted automatically
await memory.add_memory(
    "John Smith is the CEO of TechCorp. He previously worked at Microsoft.",
    metadata={"category": "people", "source": "linkedin"}
)

await memory.add_memory(
    "TechCorp is developing an AI assistant. The project is led by John Smith.",
    metadata={"category": "projects"}
)

await memory.add_memory(
    "Microsoft acquired GitHub in 2018 for $7.5 billion.",
    metadata={"category": "business"}
)
```

**Result in Graph:**

```cypher
(John Smith:Person)
    -[:IS_CEO_OF]→(TechCorp:Company)
    -[:WORKED_AT]→(Microsoft:Company)
    
(TechCorp)
    -[:DEVELOPS]→(AI Assistant:Product)
    
(AI Assistant)
    -[:LED_BY]→(John Smith)
    
(Microsoft)
    -[:ACQUIRED]→(GitHub:Company)
```

### Querying with Relationships

```python
# Regular semantic search
results = await memory.search_memories("Tell me about John Smith")

# GraphRAG automatically:
# 1. Finds John Smith entity
# 2. Traverses relationships
# 3. Returns connected information:
#    - CEO of TechCorp
#    - Previously at Microsoft
#    - Leads AI Assistant project
```

### Advanced Use Cases

#### 1. Entity-Centric Queries

```python
# Find everything about a company
await memory.search_memories(
    "What do we know about TechCorp?",
    limit=10
)

# Returns:
# - TechCorp develops AI Assistant
# - John Smith is CEO
# - Related projects and people
```

#### 2. Multi-Hop Relationships

```python
# Complex query spanning multiple entities
await memory.search_memories(
    "What connection exists between Microsoft and the AI Assistant?"
)

# Graph traversal finds:
# Microsoft → John Smith (worked there) → CEO of TechCorp → AI Assistant
```

#### 3. Temporal Relationships

```python
await memory.add_memory(
    "TechCorp raised Series A funding in 2023",
    metadata={"year": 2023, "event_type": "funding"}
)

await memory.add_memory(
    "TechCorp launched AI Assistant in 2024",
    metadata={"year": 2024, "event_type": "product_launch"}
)

# Query: "What happened at TechCorp over time?"
# Returns chronologically ordered events with relationships
```

## Querying Memgraph Directly

### Using mgconsole (CLI)

```bash
# Connect to Memgraph
docker-compose exec memgraph mgconsole

# Or from Kubernetes
kubectl exec -it -n memory-store deployment/memgraph -- mgconsole
```

### Cypher Queries

```cypher
-- See all nodes
MATCH (n) RETURN n LIMIT 25;

-- Find specific entity
MATCH (n {name: "John Smith"}) RETURN n;

-- Find all relationships for an entity
MATCH (n {name: "TechCorp"})-[r]->(m)
RETURN n, type(r), m;

-- Multi-hop query
MATCH path = (a:Person)-[:WORKED_AT*1..3]-(b:Company)
RETURN path;

-- Find patterns
MATCH (p:Person)-[:IS_CEO_OF]->(c:Company)-[:DEVELOPS]->(prod:Product)
RETURN p.name, c.name, prod.name;
```

## Monitoring & Maintenance

### Health Checks

```bash
# Docker
curl http://localhost:7444/metrics

# Check connection
docker-compose exec memory-store python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://memgraph:7687')
with driver.session() as session:
    result = session.run('RETURN 1')
    print('Connected:', result.single()[0])
"
```

### Storage Management

```bash
# Backup graph data
docker-compose exec memgraph \
  sh -c 'echo "DUMP DATABASE;" | mgconsole' > backup.cypher

# Restore
docker-compose exec -T memgraph mgconsole < backup.cypher
```

### Performance Tuning

```yaml
# In docker-compose.yml, add memory limits:
memgraph:
  environment:
    - MEMGRAPH_MEMORY_LIMIT=4GB
  deploy:
    resources:
      limits:
        memory: 8Gi
```

## Cost & Resource Usage

### Local Development
- CPU: ~0.5-1 core
- RAM: ~1-2GB
- Storage: ~5-10GB

### Production (Kubernetes)
- Minimum: 1 pod, 1GB RAM, 20GB storage
- Recommended: 1 pod, 4GB RAM, 50GB storage
- High Load: Scale vertically (more RAM)

### Comparison

| Aspect | Without GraphRAG | With GraphRAG |
|--------|------------------|---------------|
| **Storage** | ~1GB per 100K memories | ~1.5GB per 100K memories |
| **RAM** | 2GB | 4GB |
| **Query Speed** | Fast (vector only) | Fast+ (vector + graph) |
| **Capabilities** | Semantic search | Semantic + Relationships |

## Use Cases

### Best For:

1. **Research Agents**: Track papers, authors, citations
2. **Customer Service**: Customer history, product relationships
3. **Financial Analysis**: Companies, executives, transactions
4. **Knowledge Management**: Documents, topics, experts
5. **Team Collaboration**: Projects, people, dependencies

### Example: Financial Research Agent

```python
# Build knowledge graph of financial ecosystem
memories = [
    "Apple reported Q4 revenue of $89.5B",
    "Tim Cook is CEO of Apple",
    "Apple launched iPhone 15 in September 2023",
    "Morgan Stanley upgraded Apple to Overweight",
    "Apple's main competitor is Samsung",
]

for mem in memories:
    await memory.add_memory(mem, metadata={"domain": "finance"})

# Complex queries work better with graph
query = "What are the key factors affecting Apple's stock?"

# Returns connected information:
# - Leadership (Tim Cook)
# - Financial performance (Q4 revenue)
# - Product launches (iPhone 15)
# - Analyst opinions (Morgan Stanley)
# - Competitive landscape (Samsung)
```

## Troubleshooting

### Memgraph won't start

```bash
# Check logs
docker-compose logs memgraph

# Common issues:
# 1. Port 7687 already in use
docker-compose down
lsof -i :7687  # Find conflicting process

# 2. Volume permissions
docker-compose down -v
docker-compose up -d
```

### Graph queries slow

```cypher
-- Create indexes
CREATE INDEX ON :Person(name);
CREATE INDEX ON :Company(name);
CREATE INDEX ON :Product(name);
```

### Connection errors

```python
# Test connection manually
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("", "")  # No auth by default
)

with driver.session() as session:
    result = session.run("RETURN 1")
    print(result.single()[0])
```

## Disabling GraphRAG

To disable and go back to vector-only:

```bash
# Edit .env
MEM0_GRAPH_STORE_ENABLED=false

# Restart
docker-compose restart memory-store

# Optionally stop Memgraph
docker-compose stop memgraph
```

## Migration

### From Vector-Only to GraphRAG

Existing memories will:
1. Remain in Qdrant (vector store)
2. Be analyzed for entities/relationships when next accessed
3. Gradually populate the graph

No data migration needed!

### From Neo4j to Memgraph

```bash
# 1. Export from Neo4j
echo "MATCH (n) RETURN n;" | docker exec -i neo4j cypher-shell > export.cypher

# 2. Import to Memgraph
cat export.cypher | docker exec -i memgraph mgconsole

# 3. Update config
MEMGRAPH_HOST=memgraph
MEM0_GRAPH_STORE_PROVIDER=memgraph
```

## Advanced Configuration

### Memgraph Storage Options

```yaml
# In docker-compose.yml
memgraph:
  command:
    - --storage-properties-on-edges=true
    - --storage-snapshot-interval-sec=300
    - --storage-wal-enabled=true
    - --storage-recover-on-startup=true
```

### Relationship Types

Mem0 automatically extracts:
- `IS_A` - Type relationships
- `HAS` - Possession
- `WORKED_AT` - Employment
- `LOCATED_IN` - Location
- `RELATED_TO` - General relationships
- Custom types from context

## Resources

- **Memgraph Docs**: https://memgraph.com/docs
- **Cypher Query Language**: https://neo4j.com/docs/cypher-manual/
- **Mem0 Graph Store**: https://docs.mem0.ai/components/graph-store
- **GraphRAG Paper**: https://arxiv.org/abs/2404.16130

## Summary

**With GraphRAG Enabled:**
- ✅ Semantic search (vector) + Relationship traversal (graph)
- ✅ Entity and relationship extraction
- ✅ Multi-hop reasoning
- ✅ Better context understanding
- ✅ Open source (Memgraph)

**Trade-offs:**
- ⚠️ +50% storage
- ⚠️ +2GB RAM
- ⚠️ Slightly more complex setup

**Recommendation:**
- Start without GraphRAG (simpler)
- Enable when you need relationship-based queries
- Easy to enable/disable without data loss

---

**Questions? See [USER_GUIDE.md](USER_GUIDE.md) for general setup and [ARCHITECTURE.md](ARCHITECTURE.md) for technical details.**
