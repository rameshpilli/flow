1. Single-process only
No distributed execution
Roadmap item; limits scaling for large workloads


2. DAG implementation duplication
dag.py has both execute and _execute_step_original_implementation
Suggests incomplete refactor or dead code; needs cleanup


3. Orchestrator size
orchestrator.py is ~3,800 lines
Single large class handling registration, execution, events, CLI, etc.
Harder to maintain and test; could be split into focused modules
```
Migration Steps
    Create core/orchestrator/ package.
    Add definitions.py and move Definitions.
    Add base.py with __init__ and lifecycle.
    Add mixin modules one by one, moving methods from orchestrator.py.
    Add main.py with the composed AgentOrchestrator.
    Add orchestrator/__init__.py with re-exports.
    Remove core/orchestrator.py.
    Update core/__init__.py to import from core.orchestrator (path unchanged).
    Run tests and fix any import issues.
```



4. Config size
config.py is ~1,189 lines
Central config is useful, but a single large module is brittle
Could be split by domain (LLM, chain, context, etc.)


5. Two agent concepts
agents/base.py: BaseAgent, AgentResult (data agents)
squad/agents/: LLMGatewayAgent, SupervisorAgent (chat/LLM agents)
Relationship and integration between them is unclear; naming can confuse users


6. for deep Agents
Sub-agent spawning with isolated context windows
Deep Agents' task tool lets the agent spawn fully isolated sub-agents, each with their own context window. Our parallel search steps share the same ChainContext. For very long research tasks this could hit context limits.