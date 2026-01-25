# Documentation Restructure Plan

> Goal: Developer-friendly docs like LlamaIndex for 100+ user adoption

## Target Structure

```
docs/
├── index.md                    # Landing page with value prop
│
├── getting-started/
│   ├── installation.md         # pip, conda, source, docker
│   ├── quickstart.md           # First agent in 5 minutes
│   ├── first-chain.md          # Multi-step pipeline
│   └── environment.md          # Env vars, configuration
│
├── concepts/                   # Understanding (the "why")
│   ├── overview.md             # What is AgentOrchestrator?
│   ├── agents.md               # Agent lifecycle, types
│   ├── steps-and-chains.md     # DAG execution model
│   ├── context.md              # Scopes, state management
│   ├── tools.md                # Tool definition, schemas
│   ├── middleware.md           # Cross-cutting concerns
│   ├── multi-agent.md          # Routing, supervisor, handoffs
│   ├── memory.md               # Chat history, semantic memory
│   └── observability.md        # Tracing, logging, metrics
│
├── patterns/                   # How to build common things
│   ├── react-agent.md          # Thought→Action→Observation
│   ├── deep-research.md        # Multi-stage research workflow
│   ├── rag-pipeline.md         # Retrieval-augmented generation
│   ├── supervisor.md           # Team coordination
│   ├── human-in-loop.md        # Approval workflows
│   └── streaming.md            # Real-time responses
│
├── use-cases/                  # Problem → Solution
│   ├── chatbot.md              # Conversational agent
│   ├── document-qa.md          # Document question answering
│   ├── code-assistant.md       # Code generation/review
│   ├── data-analysis.md        # SQL/pandas agent
│   └── customer-support.md     # Multi-agent support bot
│
├── how-to/                     # Task-oriented guides
│   ├── custom-tools.md         # Adding your own tools
│   ├── custom-middleware.md    # Creating middleware
│   ├── external-apis.md        # Integrating services
│   ├── error-handling.md       # Retries, circuit breakers
│   ├── testing.md              # Unit and integration tests
│   └── deployment.md           # Production deployment
│
├── api/                        # Reference
│   ├── orchestrator.md         # AgentOrchestrator class
│   ├── context.md              # ChainContext API
│   ├── agents.md               # BaseAgent, ResilientAgent
│   ├── middleware.md           # Middleware classes
│   ├── services.md             # LLMGateway, VectorStore
│   ├── squad.md                # Multi-agent classes
│   └── cli.md                  # CLI commands
│
├── examples/                   # Runnable code
│   ├── basic/
│   │   ├── hello-world.py
│   │   ├── simple-chain.py
│   │   └── parallel-steps.py
│   ├── agents/
│   │   ├── react-agent.py
│   │   ├── research-agent.py
│   │   └── supervisor.py
│   ├── rag/
│   │   ├── basic-rag.py
│   │   └── agentic-rag.py
│   └── notebooks/
│       ├── quickstart.ipynb
│       └── deep-research.ipynb
│
└── contributing/
    ├── development.md          # Dev setup, testing
    ├── architecture.md         # Internals for contributors
    └── adding-tools.md         # Contributing tools
```

## Updated mkdocs.yml Navigation

```yaml
nav:
  - Home: index.md

  - Getting Started:
    - Installation: getting-started/installation.md
    - Quick Start: getting-started/quickstart.md
    - Your First Chain: getting-started/first-chain.md
    - Configuration: getting-started/environment.md

  - Concepts:
    - Overview: concepts/overview.md
    - Agents: concepts/agents.md
    - Steps & Chains: concepts/steps-and-chains.md
    - Context & State: concepts/context.md
    - Tools: concepts/tools.md
    - Middleware: concepts/middleware.md
    - Multi-Agent Systems: concepts/multi-agent.md
    - Memory: concepts/memory.md
    - Observability: concepts/observability.md

  - Patterns:
    - ReAct Agent: patterns/react-agent.md
    - Deep Research: patterns/deep-research.md
    - RAG Pipeline: patterns/rag-pipeline.md
    - Supervisor: patterns/supervisor.md
    - Human-in-Loop: patterns/human-in-loop.md
    - Streaming: patterns/streaming.md

  - Use Cases:
    - Chatbot: use-cases/chatbot.md
    - Document Q&A: use-cases/document-qa.md
    - Code Assistant: use-cases/code-assistant.md
    - Data Analysis: use-cases/data-analysis.md
    - Customer Support: use-cases/customer-support.md

  - How-To Guides:
    - Custom Tools: how-to/custom-tools.md
    - Custom Middleware: how-to/custom-middleware.md
    - External APIs: how-to/external-apis.md
    - Error Handling: how-to/error-handling.md
    - Testing: how-to/testing.md
    - Deployment: how-to/deployment.md

  - API Reference:
    - AgentOrchestrator: api/orchestrator.md
    - ChainContext: api/context.md
    - Agents: api/agents.md
    - Middleware: api/middleware.md
    - Services: api/services.md
    - Squad: api/squad.md
    - CLI: api/cli.md

  - Examples:
    - examples/index.md

  - Contributing:
    - Development: contributing/development.md
    - Architecture: contributing/architecture.md
```

## Key Principles

### 1. Progressive Disclosure
- Start simple (Hello World)
- Add complexity gradually
- Don't overwhelm new users

### 2. Task-Oriented
- "How do I...?" questions answered
- Real problems, real solutions
- Copy-pasteable code

### 3. Conceptual First
- Explain the "why" before the "how"
- Mental models before API details
- Diagrams and visualizations

### 4. Runnable Examples
- Every example should work
- Include imports and setup
- Test examples in CI

### 5. Search-Friendly
- Good headings and structure
- Keywords in natural places
- Cross-linking between pages

## Migration Path

### Phase 1: Reorganize Existing Content
1. Move existing docs into new structure
2. Update internal links
3. Add redirects for old URLs

### Phase 2: Fill Gaps
1. Write missing conceptual guides
2. Create pattern documentation
3. Add use case examples

### Phase 3: Examples Gallery
1. Create runnable examples
2. Add Jupyter notebooks
3. Include in CI testing

### Phase 4: Polish
1. Add diagrams (Mermaid)
2. Improve search
3. Add versioning (mike)
4. Deploy to GitHub Pages

## Success Metrics

- [ ] New developer can build first agent in < 10 minutes
- [ ] All core features have documentation
- [ ] Examples gallery with 10+ runnable examples
- [ ] Zero broken internal links
- [ ] Mobile-friendly navigation
