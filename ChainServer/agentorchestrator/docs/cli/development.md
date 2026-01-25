# Development & Debugging Commands

Commands for development workflow and debugging.

## dev

Run in development mode with optional hot reloading.

```bash
ao dev [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--watch` | `-w` | Watch for file changes and auto-reload |

### Examples

```bash
# Basic development mode
ao dev

# With hot reloading
ao dev --watch
```

### What It Does

1. **Initial validation** - Runs `check` and `list` on startup
2. **File watching** (with `--watch`) - Monitors `.py` files in current directory
3. **Auto-reload** - When files change:
   - Clears registries
   - Reimports modified modules
   - Re-validates definitions

### Requirements

Hot reloading requires the `watchdog` package:

```bash
pip install watchdog
```

Without `watchdog`, the command runs initial validation but won't watch for changes.

### Output

```
Starting AgentOrchestrator development server...

--- Initial Validation ---
[chain validation output]
[component listing]

Watching for changes in /path/to/project
Press Ctrl+C to stop...

--- File changed: /path/to/project/chains.py ---
Reloading definitions...

--- Validation ---
[updated validation output]
```

---

## debug

Run a chain in debug mode with context snapshots after each step.

```bash
ao debug <chain_name> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--entity` | `-e` | Entity name (shortcut for `entity_name` in data) |
| `--data` | `-d` | JSON input data |
| `--snapshot-dir` | `-s` | Directory for snapshots (default: `.agentorchestrator/snapshots`) |
| `--verbose` | `-v` | Show full tracebacks |

### Examples

```bash
# Debug a chain
ao debug my_chain --data '{"key": "value"}'

# Custom snapshot directory
ao debug my_chain --snapshot-dir ./debug_output/

# With verbose error output
ao debug my_chain --data '{"key": "value"}' --verbose
```

### What It Creates

For each debug run, creates a timestamped directory:

```
.agentorchestrator/snapshots/
└── my_chain_20240115_103045/
    ├── 00_summary.json      # Overall run summary
    ├── 01_step_1.json       # Snapshot after step 1
    ├── 02_step_2.json       # Snapshot after step 2
    ├── 03_step_3.json       # Snapshot after step 3
    └── 99_error.json        # Error details (if failed)
```

### Snapshot Contents

**Step snapshots** (`01_step_name.json`):

```json
{
  "step_number": 1,
  "step_name": "step_1",
  "timestamp": "2024-01-15T10:30:46.123456",
  "result": {
    "success": true,
    "output": {"processed": true},
    "duration_ms": 1023.45,
    "error": null,
    "error_type": null
  },
  "context": {
    "request_id": "req_abc123",
    "total_tokens": 150,
    "data": {
      "key": "value",
      "step_1_result": {"processed": true}
    }
  },
  "results_so_far": [
    {"step": "step_1", "success": true, "duration_ms": 1023.45}
  ]
}
```

**Summary** (`00_summary.json`):

```json
{
  "chain_name": "my_chain",
  "run_id": "20240115_103045",
  "success": true,
  "total_duration_ms": 5234.56,
  "total_steps": 5,
  "input_data": {"key": "value"},
  "final_result": {
    "success": true,
    "results": [...]
  }
}
```

**Error snapshot** (`99_error.json`, if failed):

```json
{
  "chain_name": "my_chain",
  "run_id": "20240115_103045",
  "error": "Connection timeout",
  "error_type": "TimeoutError",
  "traceback": "Traceback (most recent call last):\n...",
  "duration_ms": 3456.78,
  "input_data": {"key": "value"}
}
```

### Console Output

```
════════════════════════════════════════════════════════════════
  DEBUG MODE: my_chain
  Snapshots: .agentorchestrator/snapshots/my_chain_20240115_103045
════════════════════════════════════════════════════════════════

  [✓] step_1 (1023.45ms) → 01_step_1.json
  [✓] step_2 (856.23ms) → 02_step_2.json
  [✓] step_3 (2134.67ms) → 03_step_3.json
  [✓] step_4 (789.01ms) → 04_step_4.json
  [✓] step_5 (431.20ms) → 05_step_5.json

════════════════════════════════════════════════════════════════
  Result: SUCCESS
  Duration: 5234.56ms
  Snapshots: .agentorchestrator/snapshots/my_chain_20240115_103045
════════════════════════════════════════════════════════════════

  ✓ step_1: 1023.45ms
  ✓ step_2: 856.23ms
  ✓ step_3: 2134.67ms
  ✓ step_4: 789.01ms
  ✓ step_5: 431.20ms
```

### Use Cases

- **Debugging failures** - See exactly which step failed and the context state
- **Understanding data flow** - Track how context evolves through steps
- **Performance analysis** - Identify slow steps
- **Regression testing** - Compare snapshots between runs
- **Documentation** - Generate execution traces for docs
