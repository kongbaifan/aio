# Bash Commands Reference

## Overview

Shell execution and session management via tmux backend. Supports multiple concurrent sessions, async execution, and process lifecycle management.

## Commands

### `aio bash [command...]` (shorthand)

Execute a shell command directly without the `exec` subcommand.

```bash
aio bash "ls -la"
aio bash "python main.py"
aio bash "echo hello && echo world"
```

### `aio bash exec <command>`

Execute a shell command with full options.

| Option | Description | Default |
|--------|-------------|---------|
| `--timeout <seconds>` | Execution timeout | 30 |
| `--async` | Run asynchronously (returns session ID immediately) | false |
| `--dir <path>` | Working directory | `/` |
| `--id <session>` | Session ID to execute in | auto-generated |

```bash
aio bash exec "python train.py" --timeout 300
aio bash exec "npm test" --dir /app
aio bash exec "long-running-task" --async
aio bash exec "make build" --id my-session
```

**Output behavior:**
- **Text mode (TTY):** Prints stdout directly, sets exit code on failure
- **JSON mode (piped):** Returns full response with `output`, `exit_code`, `id`

### `aio bash view <session-id>`

View output of a running or completed command in a session.

```bash
aio bash view abc123
```

### `aio bash kill <session-id>`

Terminate a running process in a session.

```bash
aio bash kill abc123
```

### `aio bash sessions`

List all active shell sessions.

```bash
aio bash sessions
```

### `aio bash session-create`

Create a new shell session.

| Option | Description |
|--------|-------------|
| `--id <id>` | Custom session ID |
| `--dir <path>` | Working directory |

```bash
aio bash session-create --id dev --dir /workspace
```

### `aio bash session-delete <id>`

Delete a shell session.

```bash
aio bash session-delete dev
```

## Patterns

### Long-running tasks

```bash
# Start async, then poll
aio bash exec "python train.py" --async --id training
# Check later
aio bash view training
# Kill if needed
aio bash kill training
```

### Dedicated work sessions

```bash
aio bash session-create --id build --dir /workspace
aio bash exec "npm install" --id build
aio bash exec "npm run build" --id build
aio bash exec "npm test" --id build
aio bash session-delete build
```
