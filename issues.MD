Multi-Agent Orchestrator System - Requirements & Issues
Issue #2: SupervisorAgent with Agents Coordination
Overview
Implement a SupervisorAgent that enables sophisticated team coordination between multiple specialized agents using an "agent-as-tools" architecture.

Core Features
Parallel Processing - Execute multiple agent queries simultaneously
Smart Context Management - Maintain conversation history across all team members (Agents have Lead Agent Memory & Team Memory)
Dynamic Delegation - Intelligently distribute subtasks to appropriate team members
Integration Methods
Direct Usage - Call directly for dedicated team coordination (linear chains: SEC + CapIQ + News etc.)
Classifier Integration - Add as an agent within classifier for hierarchical systems with multiple specialized teams and intelligent routing
Process Flow
User asks a question
Supervisor analyzes using its own LLM to understand intent
Decides which specialist agent is best suited
Routes to specialist agent for processing
Receives response and returns to user
Additional Requirements (from @sema)
Custom LLM and embedding model from LLM Gateway
RAG as a service integration with subagents (via MCP connectors)
Supervisor creates variable number of subagents based on request
Allow customizations/configurations for different subagent types
Pluggable interfaces (memory store, Redis, etc.)
Dynamic resource allocation based on number of subagents needed
Application logs and OpenTelemetry span tracing
LLM as a judge and guardrails for all agents
Claude skills capability
Validation layer for agent outputs
Issue #3: Multi-Agent Orchestrator
Overview
Flexible framework for managing multiple AI agents and handling complex conversations with intelligent query routing and context maintenance.

Architecture Flow
User input → Classifier analysis
Classifier uses Agents' Characteristics + Conversation history
Select most appropriate agent
Agent processes user input
Orchestrator saves conversation (updates history)
Response delivered to user
Core Features
Intelligent Intent Classification - Dynamic routing based on context and content
Flexible Agent Responses - Support for streaming and non-streaming responses
Context Management - Maintain conversation context across multiple agents
Extensible Architecture - Easy integration of new/custom agents
Pre-built Components - Ready-to-use agents and classifier implementations
Technical Constraints
Agent Squad package won't work in corporate environment (routes directly to Anthropic/OpenAI APIs)
Solution: Build native SupervisorAgent with AgentOrchestrator that:
Uses existing LLMGateway Client with OAuth
Works behind corporate proxy
Follows same patterns as Agent Squad
Issue #4: Memory & Context Management
Memory Management Types
Short-term Memory - Conversation context within sessions
Long-term Memory - User preferences, historical interactions
Working Memory - Task state, intermediate results
Context Management Requirements
Context window optimization
Smart context pruning and summarization
Multi-turn conversation handling
Cross-agent context sharing
Issue #5: Generic YAML-based Entry Points for Workflows (Lower Priority)
Overview
Allow users to define AI agent workflows through YAML configuration or visual UI, with standardized YAML format, DAG construction at runtime, and full observability.

Dual Workflow Definition Methods
A. Direct YAML Authoring (Technical Users)
Standardized YAML schema
Version control integration (Git)
Schema validation with immediate feedback
IDE support (syntax highlighting, auto-completion)
Template library for common patterns
Linting and best practices validation
B. UI-Based Configuration (Non-Technical Users)
Drag-and-drop visual workflow builder
Node-based interface (similar to n8n, Dify, Windmill, Temporal)
Real-time YAML preview
Form-based node configuration
Visual validation and error indicators
Bidirectional sync: UI ↔ YAML
Open-Source Options to Evaluate
n8n - Self-hosted, extensive integrations, node-based
Windmill - Developer-first, scripts as workflows, TypeScript/Python support
Prefect - Python-native, data pipeline focus
Temporal Workflow UI - Durable execution, state management
Argo Workflows - Kubernetes-native, container orchestration
Apache Airflow - Mature, Python DAGs, extensive plugins
Dagster - Data-aware orchestration, asset-based
Flyte - ML/data workflows, type-safe
TODO: Evaluate n8n or Windmill for fastest integration with customization capabilities

Dynamic DAG Construction
YAML Parsing
Validate YAML syntax
Load workflow definition
Resolve variable references and expressions
Validate against schema
DAG Building
Create node objects from agent definitions
Establish edges based on dependencies
Validate graph structure (no cycles, valid references)
Optimization
Topological sorting for execution order
Identify parallel execution opportunities (nodes with no dependencies run concurrently)
Calculate critical path (longest path = minimum execution time)
Optimize execution plan (batch parallel operations, minimize wait times)
DAG Node Types
Agent Nodes - LLM inference, RAG retrieval, fine-tuned models, multi-agent collaboration, skill invocation
Conditional Nodes - Evaluate expressions, route to different paths, skip nodes, multi-way branching
Parallel Nodes - Fan-out to multiple agents, concurrent API calls, synchronization points
Context Propagation
Each node accesses workflow context
Previous node outputs available via ${nodes.node_id.outputs.field}
Shared memory for cross-node communication
Workflow inputs accessible throughout execution
Recovery Mechanisms
Automatic retry with exponential backoff (1s, 2s, 4s, 8s...)
Configurable retry attempts per node
Jitter to prevent thundering herd
Retry on specific error types
Issue #8: Prompt Optimization
Overview
LLM-driven prompt optimization - system that helps figure out the best prompt for given tasks.

Key Bottlenecks to Address (Cross-Cutting Concerns)
1. Session Management
Track conversation history so each agent knows prior context
Ensure session state is accessible across agent handoffs
2. Context Window Limits
Implement summarization strategy for older conversation parts
Prevent out-of-memory issues from context overflow
Smart pruning without losing critical information
3. Coordination Between Agents
Clear handoff protocols between agents
Define when agents should step in vs. defer to another
Avoid conflicts or duplicate responses
4. Response Consistency
Maintain consistent tone and quality across different agents
Ensure smooth user experience regardless of which agent responds
Unified response formatting
5. Performance Overhead
System must stay fast as more agents are added
Monitor latency and resource usage
Optimize parallel execution to reduce bottlenecks
Priority Order (Suggested)
Issue #2 + #3 - Core SupervisorAgent and Multi-Agent Orchestrator (foundational)
Issue #4 - Memory & Context Management (required for coherent multi-agent conversations)
Issue #8 - Prompt Optimization (quality improvement)
Issue #5 - YAML-based Workflows (advanced feature, lower priority)
