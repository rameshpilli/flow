# Getting Started Examples

Start here if you're new to AgentOrchestrator.

## Examples

### 1. Hello World

The simplest possible chain - just one step.

```bash
python hello_world.py
```

**What you'll learn:**
- Creating an AgentOrchestrator instance
- Defining a step with `@ao.step()`
- Defining a chain with `@ao.chain()`
- Running a chain with `ao.launch()`

### 2. Simple Chain

A multi-step pipeline with dependencies.

```bash
python simple_chain.py
```

**What you'll learn:**
- Step dependencies with `deps=["step_name"]`
- Passing data between steps via context
- Chain execution order

### 3. Parallel Steps

Steps without dependencies run in parallel.

```bash
python parallel_steps.py
```

**What you'll learn:**
- Parallel execution optimization
- Multiple steps feeding into one
- Performance benefits of DAG execution

### 4. AI Workflow DAG

A tiny AI workflow with parallel research branches.

```bash
python ai_workflow_dag.py
```

**What you'll learn:**
- DAG-style AI workflows in a few steps
- Parallel branches with shared dependencies
- Clear data flow via context

### 5. Conditional Workflow

DAG workflows with conditional execution paths and routing.

```bash
python conditional_workflow.py
python conditional_workflow.py --query "simple question"
python conditional_workflow.py --query "complex analysis needed"
```

**What you'll learn:**
- Conditional step execution based on context
- Dynamic routing between workflow branches
- Error handling in production DAG workflows
- Early termination patterns

## Next Steps

After completing these examples:

1. [Memory examples](../memory/) - Add conversation storage
2. [RAG examples](../rag/) - Retrieval-augmented generation
3. [Agent examples](../agents/) - Multi-agent orchestration
