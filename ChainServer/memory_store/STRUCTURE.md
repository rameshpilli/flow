# Memory Store - Project Structure

Clean, organized folder structure following Python packaging standards.

## Directory Layout

```
memory_store/
│
├── 📦 memory_store/              # Source code package
│   ├── __init__.py               # Package initialization & exports
│   ├── api.py                    # FastAPI REST API
│   ├── service.py                # Core mem0 business logic
│   ├── config.py                 # Configuration management
│   ├── client.py                 # Python client library
│   ├── cli.py                    # Command-line interface
│   └── llm_adapter.py            # LLM Gateway integration
│
├── 📚 docs/                      # Documentation
│   ├── README.md                 # Documentation index
│   ├── QUICKSTART.md             # 5-minute setup guide
│   ├── USER_GUIDE.md             # Connection & troubleshooting
│   ├── INTEGRATION.md            # AgentOrchestrator integration
│   ├── DEPLOYMENT.md             # Complete deployment guide
│   ├── DEPLOYMENT_ARCHITECTURE.md # Pod/container layout
│   ├── ARCHITECTURE.md           # System design & data flow
│   ├── GRAPHRAG_GUIDE.md         # Memgraph GraphRAG setup
│   ├── FEATURES.md               # Complete feature list
│   └── PROJECT_SUMMARY.md        # Technical overview
│
├── 🐳 deployments/               # Docker & container configs
│   ├── Dockerfile.corporate      # Corporate container image (RBC)
│   ├── docker-compose.yml        # Local development stack
│   └── .dockerignore             # Docker build exclusions
│
├── ⎈ helm/                       # Helm chart (Corporate K8s)
│   ├── Chart.yaml                # Chart metadata
│   ├── values.yaml               # Base configuration
│   ├── .helmignore               # Helm ignore patterns
│   ├── environments/
│   │   ├── dev/values.yaml       # DEV environment
│   │   ├── qat/values.yaml       # QAT environment
│   │   └── prod/values.yaml      # PROD environment
│   └── templates/                # K8s manifest templates
│       ├── _helpers.tpl          # Template helpers
│       ├── deployment.yaml       # Memory Store deployment
│       ├── service.yaml          # Service definition
│       ├── configmap.yaml        # Configuration
│       ├── ingress.yaml          # External access
│       ├── hpa.yaml              # Auto-scaling
│       ├── serviceaccount.yaml   # Service account
│       ├── qdrant-deployment.yaml    # Qdrant vector DB
│       ├── memgraph-deployment.yaml  # Memgraph graph DB
│       └── NOTES.txt             # Post-install notes
│
├── 🚀 helios/                    # Helios deployment (RBC)
│   ├── env-config.yml            # Environment targets
│   └── deploy.sh                 # Deployment script
│
├── 🧪 tests/                     # Test suite
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── test_config.py            # Configuration tests
│   └── test_service.py           # Service logic tests
│
├── 📝 examples/                  # Code examples
│   ├── README.md                 # Examples guide
│   └── basic_usage.py            # Working examples
│
├── 📄 Root Files
│   ├── README.md                 # Main project readme
│   ├── pyproject.toml            # Python project config
│   ├── Makefile                  # Development commands
│   ├── env.example               # Environment template
│   └── .gitignore                # Git exclusions
│
└── STRUCTURE.md                  # This file
```

## File Count

- **Source Code**: 7 files
- **Documentation**: 11 files (10 guides + 1 index)
- **Deployment**: 3 files (Dockerfile, compose, ignore)
- **Helm Chart**: 16 files (chart, values, templates)
- **Helios**: 2 files (config, deploy script)
- **Tests**: 4 files
- **Examples**: 2 files
- **Config**: 5 files (pyproject, Makefile, env, structure, quickstart)

**Total**: 50 files across 8 directories

## Key Principles

### 1. **Separation of Concerns**
- Source code in `memory_store/`
- Documentation in `docs/`
- Deployment configs in `deployments/`
- Tests in `tests/`

### 2. **Standard Python Package**
- Follows PEP 518 (pyproject.toml)
- Importable as: `from memory_store import MemoryStoreClient`
- Installable via: `pip install -e .`

### 3. **Clear Entry Points**
- Main README at root
- Documentation index at `docs/README.md`
- Examples at `examples/README.md`

### 4. **Self-Contained Deployments**
- Docker configs in `deployments/`
- Kubernetes manifests in `k8s/`
- Clear separation from source code

## Common Commands

### Development
```bash
# Install
pip install -e .

# Run locally
python -m memory_store.cli --reload

# Or with Makefile
make dev
```

### Docker
```bash
# Build (corporate Dockerfile)
make docker-build

# Run with compose (local development)
docker-compose -f deployments/docker-compose.yml up -d

# Or with Makefile
make docker-compose-up
```

### Kubernetes (Helm - Corporate)
```bash
# Template chart
make helm-template-dev

# Deploy
make helm-install ENVIRONMENT=dev

# Upgrade
make helm-upgrade ENVIRONMENT=dev

# Or direct Helm
helm install memory-store ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev
```

### Testing
```bash
# Run tests
pytest tests/

# Or with Makefile
make test
```

## Import Structure

### From Source
```python
# Import from package
from memory_store import MemoryStoreClient
from memory_store.config import get_config
from memory_store.service import MemoryStoreService
```

### CLI Usage
```bash
# Installed CLI command
memory-store --help

# Or via Python module
python -m memory_store.cli --help
```

## Documentation Organization

### For Users
1. **Getting Started**: `docs/QUICKSTART.md`
2. **Using the Client**: `docs/USER_GUIDE.md`
3. **Integration**: `docs/INTEGRATION.md`

### For Operators
1. **Understanding Architecture**: `docs/DEPLOYMENT_ARCHITECTURE.md`
2. **Deploying**: `docs/DEPLOYMENT.md`
3. **Advanced Features**: `docs/GRAPHRAG_GUIDE.md`

### For Developers
1. **Architecture**: `docs/ARCHITECTURE.md`
2. **Features**: `docs/FEATURES.md`
3. **Technical Summary**: `docs/PROJECT_SUMMARY.md`

## Benefits of This Structure

### ✅ Clean & Professional
- No clutter at root level
- Clear organization
- Easy to navigate

### ✅ Standard Compliant
- Follows Python packaging standards
- Compatible with PyPI
- Works with standard tools

### ✅ Easy to Maintain
- Logical grouping
- Clear file purposes
- Simple to find things

### ✅ Scales Well
- Can add more docs easily
- Can add more modules
- Can add more deployments

### ✅ Tool-Friendly
- IDEs recognize structure
- Linters work correctly
- Type checkers happy

## Comparison

### Before (Flat Structure - Original)
```
memory_store/
├── __init__.py
├── api.py
├── service.py
├── config.py
├── client.py
├── README.md
├── QUICKSTART.md
├── USER_GUIDE.md
├── INTEGRATION.md
├── DEPLOYMENT.md
├── ARCHITECTURE.md
├── Dockerfile
├── docker-compose.yml
├── ... (38 files at root!)
└── Overwhelming! 😵
```

### After (Organized Structure - Current)
```
memory_store/
├── memory_store/       # Source code package
├── docs/               # Documentation (11 files)
├── deployments/        # Docker configs (standard + corporate)
├── helm/               # Helm chart (corporate K8s)
├── helios/             # Helios deployment (RBC)
├── tests/              # Tests
├── examples/           # Examples
├── README.md           # Main readme
├── pyproject.toml      # Project config
├── Makefile            # Build commands
└── Clean & Professional! ✨
```

## Navigation Tips

### Finding Things
- **Need to deploy?** → Check `deployments/` and `k8s/`
- **Need docs?** → Check `docs/` folder
- **Need code?** → Check `memory_store/` package
- **Need examples?** → Check `examples/` folder

### Reading Documentation
1. Start with root `README.md`
2. Quick setup: `docs/QUICKSTART.md`
3. Full docs index: `docs/README.md`
4. Specific topics: Browse `docs/` folder

### Working with Code
1. Source: `memory_store/` package
2. Tests: `tests/` folder
3. Config: `pyproject.toml`
4. Build: `Makefile`

## Maintainers

When adding new content:
- **New source file** → Add to `memory_store/`
- **New documentation** → Add to `docs/`
- **New deployment** → Add to `deployments/` or `k8s/`
- **New test** → Add to `tests/`
- **New example** → Add to `examples/`

Update this file when structure changes!

---

**Last Updated**: 2026-01-14  
**Version**: 0.1.0  
**Structure**: Standard Python Package Layout
