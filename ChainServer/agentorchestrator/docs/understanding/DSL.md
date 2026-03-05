# Declarative DSL (Preview)

You can define pipelines declaratively and register them with `Pipeline.register(ao)`.

## YAML example
```yaml
pipeline: research_report
steps:
  - name: expand
    fn: expand_query            # your callable name
  - name: fetch_web
    fn: fetch_web
    deps: [expand]
    timeout_ms: 20000
  - name: summarize
    fn: summarize_docs
    deps: [fetch_web]
events:
  - on: ToolCallResult
    handler: log_tool
```

## Loading from YAML (optional)
```python
import yaml
from agentorchestrator import Pipeline

def load_pipeline_from_yaml(path, fn_registry, handler_registry):
    """
    fn_registry / handler_registry map names in YAML to callables.
    Requires PyYAML (`pip install pyyaml`).
    """
    data = yaml.safe_load(open(path))
    pipe = Pipeline(data["pipeline"])
    for s in data.get("steps", []):
        pipe.step(
            s["name"],
            fn=fn_registry[s["fn"]],
            deps=s.get("deps", []),
            timeout_ms=s.get("timeout_ms"),
        )
    for e in data.get("events", []):
        pipe.on(e["on"], handler_registry[e["handler"]])
    return pipe

# Example usage
ao = AgentOrchestrator()
pipe = load_pipeline_from_yaml(
    "research.yaml",
    fn_registry={"expand_query": expand_query, "fetch_web": fetch_web, "summarize_docs": summarize_docs},
    handler_registry={"log_tool": log_tool},
)
pipe.register(ao)
```

Notes:
- YAML loading is optional and requires `pyyaml`.
- The DSL builder (`Pipeline`) is stable; loader shape may evolve as we add caching/serialization options.
