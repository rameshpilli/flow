# Mem0 - Project Structure

Clean, organized folder structure following Python packaging standards.

## Directory Layout

```
mem0/
│
├── 📦 app/                       # Source code package (6 files)
│   ├── __init__.py               # Package initialization & exports
│   ├── api.py                    # FastAPI REST API
│   ├── service.py                # Core mem0 business logic
│   ├── config.py                 # Configuration management
│   ├── client.py                 # Python client library
│   └── cli.py                    # Command-line interface
│
├── 📚 docs/                      # Documentation (11 files)
│   ├── README.md                 # Documentation index
│   ├── QUICKSTART.md             # 5-minute setup guide
│   ├── USER_GUIDE.md             # API usage & client examples
│   ├── INTEGRATION.md            # AgentOrchestrator integration
│   ├── CORPORATE_DEPLOYMENT.md   # Helm + Helios deployment ⭐
│   ├── DEPLOYMENT.md             # Kubernetes deployment (standard)
│   ├── DEPLOYMENT_ARCHITECTURE.md # Pod/container layout
│   ├── ARCHITECTURE.md           # System design & data flow
│   ├── GRAPHRAG_GUIDE.md         # Memgraph GraphRAG setup
│   ├── FEATURES.md               # Complete feature list
│   └── PROJECT_SUMMARY.md        # Technical overview
│
├── 🐳 Dockerfile                 # Corporate container image (RBC)
├── 🐳 docker-compose.yml         # Local development stack
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
│       ├── deployment.yaml       # Mem0 deployment
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
├── 📝 examples/                  # Code examples
│   ├── README.md                 # Examples guide
│   └── basic_usage.py            # Working examples
│
├── 📄 Root Files
│   ├── README.md                 # Main project readme ⭐
│   ├── pyproject.toml            # Python project config
│   ├── Makefile                  # Development commands
│   ├── HELM_QUICKSTART.md        # Quick Helm reference
│   ├── .env.example              # Environment template
│   ├── .dockerignore             # Docker build exclusions
│   └── .gitignore                # Git exclusions
│
└── STRUCTURE.md                  # This file
```

## File Count

- **Source Code**: 6 files (app/)
- **Documentation**: 11 files (docs/)
- **Deployment**: 3 files (Dockerfile, docker-compose.yml, .dockerignore)
- **Helm Chart**: 16 files (helm/)
- **Helios**: 2 files (helios/)
- **Examples**: 2 files (examples/)
- **Config**: 6 files (pyproject, Makefile, .env.example, .gitignore, HELM_QUICKSTART, STRUCTURE)

**Total**: ~46 files across 6 directories

## Key Principles

### 1. **Separation of Concerns**
- Source code in `app/`
- Documentation in `docs/`
- Deployment at root level (Dockerfile, docker-compose.yml)
- Examples in `examples/`

### 2. **Standard Python Package**
- Follows PEP 518 (pyproject.toml)
- Importable as: `from app import MemoryStoreClient`
- Installable via: `pip install -e .`

### 3. **Clear Entry Points**
- Main README at root
- Documentation index at `docs/README.md`
- Examples at `examples/README.md`

### 4. **Production Ready**
- Corporate Dockerfile at root
- Helm chart for Kubernetes
- Helios deployment automation

## Common Commands

### Development
```bash
# Install
pip install -e .

# Run locally
python -m app.cli --reload

# Or with Makefile
make dev
```

### Docker
```bash
# Build (corporate Dockerfile)
make docker-build

# Run with compose (local development)
make docker-compose-up

# View logs
make docker-compose-logs
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
helm install mem0 ./helm/ \
  --values ./helm/environments/dev/values.yaml \
  --namespace isa0-dev
```

### Testing
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (when available)
pytest

# Lint code
make lint

# Format code
make format
```

## Import Structure

### From Source
```python
# Import from package
from app import MemoryStoreClient
from app.config import get_config
from app.service import MemoryStoreService
```

### CLI Usage
```bash
# Installed CLI command
mem0 --help

# Or via Python module
python -m app.cli --help
```

## Documentation Organization

### For Users
1. **Getting Started**: `docs/QUICKSTART.md`
2. **Using the Client**: `docs/USER_GUIDE.md`
3. **Integration**: `docs/INTEGRATION.md`

### For Operators
1. **Corporate Deployment**: `docs/CORPORATE_DEPLOYMENT.md` ⭐
2. **Understanding Architecture**: `docs/DEPLOYMENT_ARCHITECTURE.md`
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

## Navigation Tips

### Finding Things
- **Need to deploy?** → Check `Dockerfile`, `helm/`, and `helios/`
- **Need docs?** → Check `docs/` folder
- **Need code?** → Check `app/` package
- **Need examples?** → Check `examples/` folder

### Reading Documentation
1. Start with root `README.md`
2. Quick setup: `docs/QUICKSTART.md`
3. Corporate deployment: `docs/CORPORATE_DEPLOYMENT.md`
4. Full docs index: `docs/README.md`
5. Specific topics: Browse `docs/` folder

### Working with Code
1. Source: `app/` package
2. Config: `pyproject.toml`
3. Build: `Makefile`
4. Examples: `examples/` folder

## Maintainers

When adding new content:
- **New source file** → Add to `app/`
- **New documentation** → Add to `docs/`
- **New deployment** → Update `helm/` or `helios/`
- **New example** → Add to `examples/`
- **New test** → Create `tests/` folder and use pytest

Update this file when structure changes!

---

**Last Updated**: 2026-01-15  
**Version**: 0.1.0  
**Structure**: Standard Python Package Layout
