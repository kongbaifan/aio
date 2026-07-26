# Sandbox Commands Reference

## Overview

Query sandbox environment information and installed packages.

## Commands

### `aio sandbox info`

Get sandbox environment information including version, home directory, and runtime details.

```bash
aio sandbox info
```

### `aio sandbox packages`

List installed packages.

| Option | Description |
|--------|-------------|
| `--python` | List Python packages (default) |
| `--nodejs` | List Node.js packages |

```bash
aio sandbox packages --python
aio sandbox packages --nodejs
```
