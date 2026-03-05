# Execution Commands

Commands for running chains and managing executions.

## run

Run a chain with optional input data.

```bash
ao run <chain_name> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--data` | `-d` | JSON input data |
| `--entity` | `-e` | Entity name (shortcut for `entity_name` in data) |
| `--output` | `-o` | Output file for results (JSON) |
| `--verbose` | `-v` | Verbose output |
| `--resumable` | `-r` | Enable checkpointing for resume capability |
| `--run-id` | | Custom run ID (for resumable runs) |
| `--dry-run` | | Simulate execution without running steps |
| `--step` | `-s` | Run only a specific step in isolation |

### Examples

**Basic execution:**

```bash
# Run a chain with JSON data
ao run my_chain --data '{"name": "Test", "value": 42}'

# Run with entity shorthand
ao run my_chain --entity "my_entity"

# Save results to file
ao run my_chain --data '{"key": "value"}' --output results.json
```

**Resumable runs (checkpointing):**

```bash
# Run with checkpointing enabled
ao run my_chain --resumable --data '{"key": "value"}'

# Run with custom run ID
ao run my_chain --resumable --run-id my_custom_id --data '{"key": "value"}'
```

**Dry run (simulation):**

```bash
# See what would happen without executing
ao run my_chain --dry-run --data '{"key": "value"}'
```

The dry run shows:
- Execution order and parallel groups
- Steps that would run
- Dependencies between steps
- Validation status
- Input data preview

**Testing single steps:**

```bash
# Run just one step in isolation (dependencies not executed)
ao run my_chain --step context_builder --data '{"key": "value"}'
```

This is useful for:
- Testing individual steps during development
- Debugging specific step behavior
- Validating step input/output contracts

---

## resume

Resume a failed or partial chain run.

```bash
ao resume <run_id> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--rerun-all` | | Rerun all steps (don't skip completed) |
| `--output` | `-o` | Output file for results (JSON) |
| `--verbose` | `-v` | Verbose output |

### Examples

```bash
# Resume from last checkpoint
ao resume run_abc123

# Rerun all steps (ignore completed status)
ao resume run_abc123 --rerun-all

# Save resumed run results
ao resume run_abc123 --output resumed_results.json
```

### How Resume Works

1. Loads the checkpoint from the run store
2. Identifies completed and pending steps
3. Skips completed steps (unless `--rerun-all`)
4. Continues execution from the failure point
5. Updates the run record with new results

---

## runs

List chain runs with optional filters.

```bash
ao runs [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--chain` | `-c` | Filter by chain name |
| `--status` | `-s` | Filter by status (completed, failed, partial, running) |
| `--limit` | `-n` | Maximum runs to show (default: 20) |
| `--resumable-only` | | Show only resumable runs |
| `--verbose` | `-v` | Verbose output |

### Examples

```bash
# List all recent runs
ao runs

# Filter by chain name
ao runs --chain my_chain

# Show only failed runs
ao runs --status failed

# Show resumable runs only
ao runs --resumable-only

# Limit results
ao runs --limit 50
```

### Output

```
══════════════════════════════════════════════════════════════════════════════════
  Chain Runs
══════════════════════════════════════════════════════════════════════════════════

  Run ID               Chain                Status     Steps        Created
  -------------------- -------------------- ---------- ------------ --------------------
  run_abc123           my_chain             completed  5/5          2024-01-15 10:30:00
  run_def456           my_chain             failed     3/5          2024-01-15 10:25:00
  run_ghi789           other_chain          partial    2/4          2024-01-15 10:20:00

══════════════════════════════════════════════════════════════════════════════════
  Total: 3 runs
══════════════════════════════════════════════════════════════════════════════════
```

---

## run-info

Show detailed information about a specific run.

```bash
ao run-info <run_id> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--json` | `-j` | Output as JSON |

### Examples

```bash
# Show run details
ao run-info run_abc123

# Get JSON output
ao run-info run_abc123 --json
```

### Output

```
════════════════════════════════════════════════════════════════
  Run Details: run_abc123
════════════════════════════════════════════════════════════════

  Chain: my_chain
  Status: completed
  Created: 2024-01-15T10:30:00
  Updated: 2024-01-15T10:30:05
  Completed: 2024-01-15T10:30:05
  Duration: 5234.56ms
  Steps: 5/5
  Resumable: Yes
  Last Completed: final_step

  Steps:
    ✓ step_1: completed (1023.45ms)
    ✓ step_2: completed (856.23ms)
    ✓ step_3: completed (2134.67ms)
    ✓ step_4: completed (789.01ms)
    ✓ step_5: completed (431.20ms)

════════════════════════════════════════════════════════════════
```

---

## run-output

Get partial outputs from a run (useful for failed/partial runs).

```bash
ao run-output <run_id> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--json` | `-j` | Output as JSON |

### Examples

```bash
# Get outputs from completed steps
ao run-output run_abc123

# Get JSON output
ao run-output run_abc123 --json
```

### Output

```
════════════════════════════════════════════════════════════════
  Partial Outputs: run_abc123
  Chain: my_chain
  Status: partial
  Completed: 3/5 steps
════════════════════════════════════════════════════════════════

  step_1:
    result: processed
    count: 42

  step_2:
    data: [item1, item2, item3]
    status: success

  step_3:
    summary: Analysis complete
    score: 0.95
```

This is particularly useful when:
- A run failed partway through and you need the partial results
- You want to inspect intermediate outputs for debugging
- You need to extract data from a long-running chain that was interrupted
