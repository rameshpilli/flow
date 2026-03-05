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


4. Config size
config.py is ~1,189 lines
Central config is useful, but a single large module is brittle
Could be split by domain (LLM, chain, context, etc.)


5. Two agent concepts
agents/base.py: BaseAgent, AgentResult (data agents)
squad/agents/: LLMGatewayAgent, SupervisorAgent (chat/LLM agents)
Relationship and integration between them is unclear; naming can confuse users