# AgentOrchestrator - Decision Tree Reference (Project Key Items)

> Tree-style walkthrough of the framework. Items are accurate to the repo unless marked [Partial] or [Planned].

Legend:
- `->` branch/decision
- `=>` recommended default
- `[Now]` implemented
- `[Partial]` exists but needs enhancement
- `[Planned]` on roadmap

---

## START HERE: Primary Execution Model

START -> What are you orchestrating?
-> Chain / Pipeline (DAG-based execution) [Now]
  -> How to define steps?
     -> Decorators (@ao.step / @ao.chain) [Now] => default
     -> Declarative DSL (dsl/pipeline.py) [Now]
  -> How are dependencies defined?
     -> Explicit deps=[...] [Now]
     -> Dataflow @produces / @consumes [Now]
     -> Dynamic steps (__dynamic_steps__) execute immediately when discovered [Now]
  -> Execution behavior?
     -> Parallelism (CHAIN_MAX_PARALLEL_STEPS) [Now]
     -> Timeout (CHAIN_DEFAULT_TIMEOUT_MS) [Now]
     -> Error handling (fail_fast / continue / retry) [Now]
     -> Retry jitter ±25% (core/dag.py) [Now]
     -> Resumable runs (launch_resumable / resume) [Now]

-> Event-driven workflow (EventBus) [Now]
  -> Backend?
     -> In-memory [Now] => dev
     -> Redis [Now] => production
  -> Handlers & event types?
     -> @ao.event_handler("EventType") [Now]
     -> EventTypes constants + emit_agent_event / emit_tool_event [Now]
  -> Run isolation?
     -> isolate_run=True (filters by run_id on shared buses) [Now]
  -> Persistence / resume?
     -> run_store + resume_event_loop() [Now]

-> Multi-agent system [Now]
  -> Single agent?
     -> BaseAgent or LLMGatewayAgent [Now]
     -> ResilientAgent wrapper (timeouts / retries / circuit breaker) [Now]
  -> Multiple agents? Choose coordination style
     -> Parallel delegation -> Squad / SupervisorAgent [Now] => default for teams
        -> Optional: validators, guardrails, max_concurrent_agents [Now]
     -> Intent routing (one agent per request) -> MultiAgentOrchestrator [Now]
        -> Classifier: LLM / embedding / keyword / custom [Now]
     -> Sequential pipeline -> FunctionAgent handoffs [Now]
     -> Tool-using reasoning -> ReAct agent + tool registry [Now]
  -> Shared memory?
     -> ChatStorage: InMemory / Redis [Now]
  -> Context isolation?
     -> None / Partial / Full [Now]
  -> Streaming?
     -> Token streaming (squad agents) [Now]

---

## CROSS-CUTTING DECISIONS (apply anywhere)

### State & Context
-> State access?
   -> Pydantic state_model (ctx.state, type-safe) [Now] => default
   -> Basic ctx.get / ctx.set [Now]
   -> Pydantic v1/v2 compatibility [Now]
-> Context scope?
   -> STEP / CHAIN / GLOBAL [Now]
-> Async safety?
   -> ctx.edit_state() for atomic updates [Now]
   -> ctx.async_set() for parallel steps [Now]
-> Context store backend?
   -> memory [Now] => dev
   -> redis [Now] => production
   -> mem0 [Now] => semantic memory

### Context Size Management
-> TokenManagerMiddleware (budget + warnings) [Now]
-> SummarizerMiddleware (stuff / map_reduce / refine / tree) [Now]
-> RollingSummaryMiddleware (incremental summarization) [Now]
-> OffloadMiddleware (Redis, store-by-reference) [Now]

### Quality & Critique Patterns
-> Self-critique -> Reflection middleware or @reflect [Now]
-> Peer critique -> SupervisorAgent + review step(s) [Now]
-> Rule-based critique -> Validators / guardrails [Now]
-> Evidence critique -> CitationMiddleware for RAG claims [Now]
-> Human approval -> @ao.approval_step() [Planned]

### Reliability & Safety
-> IdempotencyMiddleware (InMemory / Redis) [Now]
-> CacheMiddleware [Now]
-> RateLimiterMiddleware [Now]
-> CircuitBreaker utility [Now]
-> Resumable chains (launch_resumable / resume) [Now]
-> Retry jitter in DAG execution [Now]

### Knowledge & Memory
-> Need RAG?
   -> RAGAgent + VectorStoreService [Now]
      -> Providers: memory, cohere_compass [Now]
-> Long-term memory?
   -> Mem0Memory + MemoryLifecycleMiddleware [Now]
   -> Memory patterns (sliding window / summary / entity) [Planned]

### Tools & Integrations
-> Built-in tool registry (agents/tools.py) [Now]
-> Tool schemas/capabilities (plugins/capability.py, squad/types.py) [Now]
-> External tools -> MCPConnector (http / stdio / sse) [Now]
-> Custom connectors (connectors/base.py) [Now]

### Services & Configuration
-> LLM Gateway (OAuth or API key) [Now]
-> Structured output (Pydantic response models) [Now]
-> Secrets (Vault + env fallback) [Now]
-> ObservabilityService (OpenTelemetry) [Now]
-> Config via env vars (config.py) [Now]

### Observability
-> LoggerMiddleware + MetricsMiddleware [Now]
-> AnalyticsMiddleware [Now]
-> Tracing utilities (utils/tracing.py) [Now]

### Developer Experience
-> CLI: run / check / graph / debug / doctor / dev / new [Now]
-> Templates & scaffolding (templates/) [Now]
-> Examples: deep_research_agent.py, supervisor_in_chain.py [Now]

---

## ROADMAP / PARTIAL (call out explicitly)

-> Human-in-the-loop workflows (approval_step + Slack/UI) [Partial/Planned]
-> Workflow Debugger UI (web UI + breakpoints) [Partial/Planned]
-> Distributed execution support [Planned]
-> Plugin system via entry_points [Planned]
-> Test coverage expansion (EventBus / ReAct / Reflection) [Planned]

---

## KEY FILES (quick orientation)

-> core/: orchestrator.py, dag.py, context.py, state.py, event_bus.py, decorators.py, registry.py
-> middleware/: reflection.py, summarizer.py, token_manager.py, idempotency.py, citation.py, cache.py
-> agents/: base.py, react.py, tools.py
-> squad/: orchestrator.py, agents/supervisor.py, agents/function_agent.py, storage/
-> services/: llm_gateway.py, vector_store.py, mem0.py, secrets.py, observability.py
-> connectors/: mcp.py
-> dsl/: pipeline.py
-> plugins/: capability.py, discovery.py
-> templates/: scaffolding.py
-> utils/: tracing.py
