# Mem0 - Production AI Agent Memory Service

Production-ready memory management service for AI agents, powered by mem0, Qdrant, and Memgraph.

## 🎯 Overview

Mem0 provides a centralized, scalable memory service for AI agents with:

- **Multi-Agent Isolation**: Each agent gets its own memory space
- **Semantic Search**: Find relevant memories using vector similarity
- **Graph Memory** (Optional): Knowledge graphs for complex reasoning with Memgraph
- **Production Ready**: Kubernetes-native with Helm + Helios deployment
- **Corporate Integration**: Built for RBC corporate environment

## ✨ Key Features

- 🧠 **Persistent Agent Memory** - Long-term memory across sessions
- 🔍 **Semantic Search** - Context-aware memory retrieval
- 🌐 **Multi-Agent Support** - Isolated memory spaces per agent
- 📊 **Vector + Graph Storage** - Qdrant + Memgraph
- 🚀 **Auto-Scaling** - HPA for production workloads
- 🔐 **Secure** - Vault integration for secrets
- 📈 **Observable** - Health checks, logging, metrics

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Mem0 Service                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Mem0 │  │   Qdrant     │  │  Memgraph    │  │
│  │   (FastAPI)  │──│ (Vector DB)  │  │ (Graph DB)   │  │
│  │              │  │              │  │  (Optional)   │  │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  │
│         │                                                │
│         ├─► LLM Gateway (Corporate)                     │
│         └─► Cohere (Embeddings)                         │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### For Corporate Deployment (Helm + Helios)

**See: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md)** for complete guide

```bash
# 1. Build corporate Docker image
make docker-build-corporate

# 2. Template Helm chart for DEV
make helm-template-dev

# 3. Deploy via Helios
# (Follow helios/deploy.sh instructions)
```

### For Local Development

```bash
# 1. Copy environment file
cp env.example .env

# 2. Edit .env with your credentials
vim .env

# 3. Start with Docker Compose
make docker-compose-up

# 4. Verify
curl http://localhost:8000/health
```

## 📚 Documentation

### Getting Started
- **[Quick Start (5 min)](docs/QUICKSTART.md)** - Get running locally
- **[User Guide](docs/USER_GUIDE.md)** - Connect agents and use the API
- **[Integration Guide](docs/INTEGRATION.md)** - Integrate with AgentOrchestrator

### Corporate Deployment
- **[Corporate Deployment](docs/CORPORATE_DEPLOYMENT.md)** - Helm + Helios deployment (⭐ Start here for corp env)
- **[Deployment Architecture](docs/DEPLOYMENT_ARCHITECTURE.md)** - Pod/container layout
- **[Standard Deployment](docs/DEPLOYMENT.md)** - Kubernetes deployment (non-corporate)

### Technical Details
- **[Architecture](docs/ARCHITECTURE.md)** - System design and data flow
- **[Features](docs/FEATURES.md)** - Complete feature list
- **[GraphRAG Guide](docs/GRAPHRAG_GUIDE.md)** - Graph memory setup
- **[Project Summary](docs/PROJECT_SUMMARY.md)** - Technical overview

### Structure
- **[Project Structure](STRUCTURE.md)** - Folder organization explained

## 💻 Python Client

```python
from app import MemoryStoreClient

# Create client
client = MemoryStoreClient(
    base_url="https://mem0.cfk.devfg.rbc.com",  # Corporate URL
    agent_id="trading-agent-001"
)

# Add memory
client.add("Execute buy order for 1000 shares of AAPL at $150")

# Search memories
results = client.search("What trades did I execute?")
for memory in results:
    print(memory["memory"])

# Get all memories
memories = client.get_all()
```

**See: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for complete client documentation

## 🏢 Corporate Deployment

### Helm Chart

```bash
# Lint chart
make helm-lint

# Template for specific environment
make helm-template-dev    # DEV environment
make helm-template-qat    # QAT environment
make helm-template-prod   # PROD environment

# Install
make helm-install ENVIRONMENT=dev

# Upgrade
make helm-upgrade ENVIRONMENT=dev
```

### Helios Deployment

The `helios/` directory contains corporate deployment configuration:

- **`env-config.yml`** - Environment targets (dev/qat/prod)
- **`deploy.sh`** - Deployment script with Vault integration

**See: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md)** for step-by-step guide

### Environments

| Environment | URL | Namespace | Pods | Storage |
|-------------|-----|-----------|------|---------|
| DEV | mem0.cfk.devfg.rbc.com | isa0-dev | 1-3 | 5Gi |
| QAT | mem0.cfkqa.saifg.rbc.com | isa0-qat | 2-5 | 10Gi |
| PROD | mem0.cfkprod.fg.rbc.com | isa0-prod | 3-10 | 50Gi |

## 🐳 Docker

### Corporate Dockerfile
```bash
# Build with corporate base image
make docker-build

# Run with compose (local development)
make docker-compose-up

# Uses RBC Artifactory registry:
# - innersource-docker.artifactory.fg.rbc.com
# - artifactory.fg.rbc.com for Python packages
```

## ☸️ Kubernetes (Corporate - Helm)

### Helm Deployment
```bash
# Lint chart
make helm-lint

# Template for DEV
make helm-template-dev

# Install to DEV
make helm-install ENVIRONMENT=dev

# Upgrade DEV
make helm-upgrade ENVIRONMENT=dev

# Or use Helm directly
helm install mem0 ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev \
  --create-namespace
```

**See: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md)** for complete deployment guide

## 🔧 Configuration

### Environment Variables

**Core Settings:**
```bash
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8000
SERVICE_WORKERS=4
SERVICE_LOG_LEVEL=INFO
```

**LLM Gateway (Corporate):**
```bash
LLM_GATEWAY_BASE_URL=https://llm-gateway.fg.rbc.com
LLM_GATEWAY_AUTH_TYPE=oauth
LLM_GATEWAY_CLIENT_ID=<from-vault>
LLM_GATEWAY_CLIENT_SECRET=<from-vault>
```

**Cohere (Embeddings):**
```bash
COHERE_API_KEY=<from-vault>
COHERE_MODEL=embed-english-v3.0
```

**Qdrant (Vector DB):**
```bash
QDRANT_HOST=mem0-qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=agent_memories
```

**Memgraph (Optional Graph DB):**
```bash
MEM0_GRAPH_STORE_ENABLED=true
MEM0_GRAPH_STORE_PROVIDER=memgraph
MEMGRAPH_HOST=mem0-memgraph
MEMGRAPH_PORT=7687
```

### Vault Secrets (Corporate)

Secrets are managed in Vault at:
```
appcodes/ISA0/<ENV>/MEMORY-STORE/
├── COHERE_API_KEY
├── LLM_GATEWAY_CLIENT_ID
├── LLM_GATEWAY_CLIENT_SECRET
└── LLM_GATEWAY_API_KEY
```

**See: [docs/CORPORATE_DEPLOYMENT.md#vault-secrets-management](docs/CORPORATE_DEPLOYMENT.md#vault-secrets-management)**

## 📊 Monitoring

### Health Check
```bash
curl https://mem0.cfk.devfg.rbc.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "components": {
    "qdrant": "connected",
    "memgraph": "connected",
    "llm_gateway": "connected"
  }
}
```

### Kubernetes
```bash
# Check pods
kubectl get pods -l app.kubernetes.io/name=mem0

# Check HPA
kubectl get hpa mem0

# View logs
kubectl logs -f deployment/mem0

# Port forward for local access
kubectl port-forward svc/mem0 8000:80
```

## 🧪 Testing

```bash
# Run tests
make test

# Run with coverage
make test-cov

# Lint
make lint

# Format
make format
```

## 📁 Project Structure

```
mem0/
├── app/                  # Source code package
│   ├── api.py            # FastAPI application
│   ├── service.py        # Core memory logic
│   ├── config.py         # Configuration
│   ├── client.py         # Python client
│   └── ...
├── docs/                 # Documentation (11 guides)
├── helm/                 # Helm chart (Corporate K8s)
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── environments/     # DEV/QAT/PROD configs
│   └── templates/        # K8s manifests
├── helios/               # Helios deployment (Corporate)
│   ├── env-config.yml    # Environment targets
│   └── deploy.sh         # Deployment script
├── tests/                # Test suite
├── examples/             # Code examples
├── Dockerfile            # Corporate Dockerfile (RBC)
├── docker-compose.yml    # Local development stack
└── .env.example          # Environment template
```

**See: [STRUCTURE.md](STRUCTURE.md)** for detailed explanation

## 🤝 Integration Examples

### With AgentOrchestrator

```python
from agentorchestrator import Agent
from app import MemoryStoreClient

class MemoryAugmentedAgent(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.memory = MemoryStoreClient(
            base_url="https://mem0.cfkprod.fg.rbc.com",
            agent_id=self.agent_id
        )
    
    async def execute(self, context):
        # Add to memory
        self.memory.add(f"Processed: {context.input}")
        
        # Search relevant memories
        past_context = self.memory.search(context.input, limit=5)
        
        # Use in execution
        result = await self.process(context, past_context)
        return result
```

**See: [docs/INTEGRATION.md](docs/INTEGRATION.md)** for more patterns

## 🚦 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/memories` | POST | Add memory |
| `/memories` | GET | Get all memories |
| `/memories/search` | POST | Search memories |
| `/memories/{memory_id}` | PUT | Update memory |
| `/memories/{memory_id}` | DELETE | Delete memory |
| `/memories/history` | GET | Get memory history |
| `/docs` | GET | API documentation |

## 🔍 Troubleshooting

### Common Issues

**Image Pull Failures:**
```bash
# Check Artifactory credentials
kubectl get secret artifactory-docker-isa0-dev-secret -o yaml
```

**Qdrant Connection Issues:**
```bash
# Check Qdrant pod
kubectl get pod -l app.kubernetes.io/name=mem0-qdrant

# Test connectivity
kubectl exec -it <mem0-pod> -- curl http://mem0-qdrant:6333/
```

**Health Check Failures:**
```bash
# View logs
kubectl logs <pod-name>

# Check configuration
kubectl get configmap mem0-cfgmap -o yaml
```

**See: [docs/CORPORATE_DEPLOYMENT.md#troubleshooting](docs/CORPORATE_DEPLOYMENT.md#troubleshooting)** for detailed debugging

## 📖 Additional Resources

- **[mem0.ai Documentation](https://docs.mem0.ai/)** - Memory framework
- **[Qdrant Documentation](https://qdrant.tech/documentation/)** - Vector database
- **[Memgraph Documentation](https://memgraph.com/docs)** - Graph database
- **[Helios Documentation](https://rbcgithub.fg.rbc.com/pages/rbc-to/a0d0-helios-docs)** - RBC deployment platform

## 📝 License

Internal - RBC Use Only

## 👥 Support

- **ChainServer Team** - For application issues
- **RBC TO Helios** - For deployment issues
- **Platform Team** - For infrastructure issues

---

**Quick Links:**
- **Corporate Deployment**: [docs/CORPORATE_DEPLOYMENT.md](docs/CORPORATE_DEPLOYMENT.md) ⭐
- **Get Started Locally**: [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Integration Guide**: [docs/INTEGRATION.md](docs/INTEGRATION.md)
- **API Documentation**: `/docs` endpoint
- **Project Structure**: [STRUCTURE.md](STRUCTURE.md)

---

**Version**: 0.1.0  
**Last Updated**: 2026-01-14  
**Status**: Production Ready
