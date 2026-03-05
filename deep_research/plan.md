Deep Research Agent — Build Plan

What We're Building

The system from deep_research_agent.md:

User → Research Planner → Multiple Searches (parallel) → Aggregate Sources → Cross-Verify → Final Report

This maps perfectly onto the framework's DAG execution engine with parallel groups, ReAct reasoning, MCP data source adapters, and reflection middleware.



Architecture

flowchart TD
    User["User Query"] --> API["FastAPI\nPOST /run/deep_research"]
    API --> AO["AgentOrchestrator\nDAG Executor"]

    subgraph dag [DAG Pipeline]
        plan["Step: plan_research\n(query decomposition)"]
        search["Parallel Step Group:\nsearch_news / search_sec /\nsearch_financial / search_web"]
        aggregate["Step: aggregate_sources\n(dedup + rank)"]
        verify["Step: cross_verify\n(ReflectionMiddleware)"]
        report["Step: generate_report\n(SummarizerMiddleware)"]

        plan --> search
        search --> aggregate
        aggregate --> verify
        verify --> report
    end

    AO --> dag

    subgraph tools [Tool Layer]
        mcpNews["MCPToolAdapter\nnews_mcp"]
        mcpSEC["MCPToolAdapter\nsec_mcp"]
        mcpFinancial["MCPToolAdapter\nfinancial_mcp"]
        webSearch["ToolRegistry\nweb_search"]
    end

    search --> tools

    subgraph middleware [Middleware Stack]
        logger["LoggerMiddleware"]
        cache["CacheMiddleware"]
        reflect["ReflectionMiddleware"]
        rolling["RollingSummaryMiddleware"]
        token["TokenManagerMiddleware"]
        citation["CitationMiddleware"]
    end

    AO --> middleware

    subgraph storage [Storage]
        redis["Redis\nchat + cache"]
        vectorStore["VectorStoreService\ndoc retrieval"]
        mem0["Mem0\nsemantic memory"]
    end

    aggregate --> storage
    verify --> storage



Files to Create

deep_research/
├── __init__.py
├── steps.py           # All @ao.step functions
├── chain.py           # @ao.chain definition + Pipeline DSL wiring
├── tools.py           # ToolRegistry definitions (web search, etc.)
├── react_searcher.py  # ReActAgent wrapping MCP adapters for iterative search
├── middleware.py      # Middleware stack composition
├── server.py          # FastAPI app with /run, /runs, /health endpoints
├── config.py          # Pydantic settings from env vars
├── README.md          # Service README with architecture diagram + usage
└── Dockerfile
kubernetes/
├── deployment.yaml
├── service.yaml
└── configmap.yaml     # env vars (non-secret)



Step-by-Step Design

1. DAG Steps (steps.py)

Five core steps wired through dsl/pipeline.py:





**plan_research** — LLMGatewayClient decomposes the user query into N sub-queries with source hints (news, SEC, financial). Produces ["sub_queries"].



**search_news / search_sec / search_financial / search_web** — Four parallel steps in parallel_groups. Each uses its MCPToolAdapter (or ReActAgent for iterative refinement). All consume ["sub_queries"], produce ["raw_results"].



**aggregate_sources** — Deduplicate and rank by recency + relevance. Uses VectorStoreService.upsert() for cross-source dedup. Applies cap_per_source() (from middleware/offload.py) to prevent context overflow.



**cross_verify** — ReActAgent loop: for each finding, checks at least one corroborating source. ReflectionMiddleware drives the self-critique cycle.



**generate_report** — SummarizerMiddleware with map_reduce strategy synthesizes a structured Markdown report. CitationMiddleware attaches source links.

2. Chain Definition (chain.py)

Uses the Pipeline DSL from dsl/pipeline.py:

pipe = (
    Pipeline("deep_research")
        .step("plan_research",      fn=plan_research)
        .step("search_news",        fn=search_news,       deps=["plan_research"])
        .step("search_sec",         fn=search_sec,        deps=["plan_research"])
        .step("search_financial",   fn=search_financial,  deps=["plan_research"])
        .step("search_web",         fn=search_web,        deps=["plan_research"])
        .step("aggregate_sources",  fn=aggregate_sources, deps=["search_news","search_sec","search_financial","search_web"])
        .step("cross_verify",       fn=cross_verify,      deps=["aggregate_sources"])
        .step("generate_report",    fn=generate_report,   deps=["cross_verify"], timeout_ms=120000)
)

The parallel group ["search_news", "search_sec", "search_financial", "search_web"] runs concurrently via the DAGExecutor.

3. ReAct Iterative Searcher (react_searcher.py)

For each data source, a ReActAgent wraps the MCPToolAdapter:

react = ReActAgent(llm_client=llm, config=ReActConfig(max_iterations=5))
react.register_tool(mcp_adapter.to_tool("search_news"))
result = await react.run(query=sub_query)

This gives iterative refinement: if the first search returns too few results, the agent retries with refined terms.

4. Middleware Stack (middleware.py)

ao.use(LoggerMiddleware())
ao.use(CacheMiddleware(ttl=300))          # cache repeated sub-queries
ao.use(TokenManagerMiddleware())          # enforce token budgets
ao.use(RollingSummaryMiddleware())        # prevent context overflow on large result sets
ao.use(ReflectionMiddleware(max_rounds=2))  # self-critique on verify step
ao.use(CitationMiddleware())              # auto-track all sources
ao.use(MetricsMiddleware())               # OTel metrics

5. README (README.md)

The service README will include:





Overview of the deep research pattern (iterative search, multi-source, verification, synthesis)



The architecture diagram (Mermaid flowchart — same as the one in this plan) rendered inline



Quick-start instructions (env vars to set, how to run locally, how to call the API)



Example request/response (POST /run/deep_research with an M&A query)



Kubernetes deployment notes

6. FastAPI Server (server.py)

Based on the scaffold template in templates/scaffolding.py:





POST /run/deep_research — accepts {"query": "...", "system_instructions": [...]}, returns run_id



GET /runs/{run_id} — poll status



GET /runs/{run_id}/output — final report



GET /health, GET /ready, GET /live — Kubernetes probes



Lifespan: MCPServiceManager.startup() / shutdown()

6. Kubernetes Deployment





Deployment: 2 replicas, resource limits, env vars from Secret + ConfigMap



Service: ClusterIP on port 8000



ConfigMap: LLM_SERVER_URL, REDIS_HOST, MCP_*_ENDPOINT, CHAIN_MAX_PARALLEL_STEPS=4



Secret: LLM_API_KEY or OAuth creds, MCP_*_SECRET



Probes: livenessProbe: GET /live, readinessProbe: GET /ready



Dockerfile: multi-stage, pip install agentorchestrator[mcp], uvicorn server:app



Key Configuration (.env / ConfigMap)





LLM_* — your existing LLM Gateway credentials



MCP_NEWS_ENDPOINT, MCP_NEWS_SECRET — news MCP server



MCP_SEC_ENDPOINT, MCP_SEC_SECRET — SEC/EDGAR MCP server



MCP_FINANCIAL_ENDPOINT, MCP_FINANCIAL_SECRET — financial data MCP



REDIS_HOST — for caching and run store



CHAIN_MAX_PARALLEL_STEPS=4 — controls search parallelism



SUMMARIZER_STRATEGY=map_reduce



CONTEXT_STORE_BACKEND=redis



What's Fully Supported vs. What to Wire Up

Already in framework (zero custom code):





DAG parallel execution, retries, timeouts



MCP adapter lifecycle, JWT auth, path/JSON-RPC routing



Reflection, summarization, citation, rolling summary middleware



ReActAgent iterative reasoning loop



FastAPI scaffold with health/run endpoints



Redis-backed run store and chat history

Custom code needed (this implementation):





The 5 step functions (steps.py) — LLM prompt templates for each phase



Chain wiring (chain.py) — Pipeline DSL



Kubernetes manifests



Dockerfile



config.py for Pydantic settings

This is roughly ~500 lines of focused application code on top of the existing framework.