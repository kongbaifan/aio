---
name: aio
description: AIO Sandbox CLI for AI agents. Use when the user needs to interact with a sandbox environment, including executing shell commands, reading/writing files, searching code, browser automation, GUI interactions, or managing the sandbox. Triggers include requests to "run a command", "read a file", "write a file", "search for code", "take a screenshot", "navigate to a URL", "click a button", "list files", or any task requiring sandbox interaction.
allowed-tools: Bash(aio:*)
---

# AIO Sandbox CLI

## Core Workflow

The AIO CLI wraps the AIO Sandbox REST API into seven command groups:

```bash
aio bash <command>        # Shell execution
aio file <subcommand>     # File operations
aio browser <subcommand>  # Playwright browser automation
aio gui <subcommand>      # Low-level GUI (mouse/keyboard)
aio sandbox <subcommand>  # Environment info
aio skills <subcommand>   # Skill register/list/load/delete
aio mcp <subcommand>      # MCP server management
```

**Configuration priority:** `--api-url` flag > `AIO_BASE_URL` env var > `.aiorc` config > `http://localhost:8000`

## Essential Commands

### Shell Execution

```bash
# Execute a command (shorthand — no subcommand needed)
aio bash "ls -la /workspace"
aio bash "pip install requests"

# With options
aio bash exec "python train.py" --timeout 300 --async
aio bash exec "cd /app && npm test" --dir /app

# Session management
aio bash sessions                          # List active sessions
aio bash session-create --id dev --dir /workspace
aio bash view <session-id>                 # View session output
aio bash kill <session-id>                 # Kill running process
aio bash session-delete <session-id>       # Delete session
```

### File Operations

```bash
# Read files
aio file read /workspace/main.py
aio file read /workspace/main.py --start 10 --end 30    # Line range

# Write files
aio file write /workspace/output.txt --content "Hello"
aio file write /workspace/data.csv --stdin < local.csv
aio file write /workspace/log.txt --content "line" --append

# Search & replace
aio file replace /workspace/config.py --old "DEBUG=True" --new "DEBUG=False"
aio file search /workspace/app.py --regex "def\s+\w+"

# Find files
aio file find /workspace --glob "**/*.py"

# Grep across files (multi-file content search)
aio file grep "import torch" /workspace --include "*.py"
aio file grep "TODO|FIXME" /workspace -i --max-results 50
aio file grep "class\s+\w+Model" /workspace --include "*.py" -A 3 -B 1

# Glob pattern matching
aio file glob "**/*.ts" /workspace --metadata --sort modified --desc
aio file glob "src/**/*.test.js" /workspace --exclude node_modules dist

# List directory
aio file list /workspace --recursive --depth 3 --sort modified

# Upload / download
aio file upload ./local-file.txt --to /workspace/remote-file.txt
aio file download /workspace/result.csv -o ./result.csv
```

### Browser Automation (Playwright SDK)

```bash
# Navigate
aio browser navigate https://example.com
aio browser navigate https://app.com --wait-until networkidle

# Capture
aio browser screenshot                        # Save page-screenshot.png
aio browser screenshot --full -o page.png     # Full page

# Interact
aio browser click "button.submit"
aio browser fill "Login" -s "#username"
aio browser type "search query" --delay 50
aio browser press Enter
aio browser hotkey Control a
aio browser scroll --dir down --amt 500

# Content extraction
aio browser html                              # Get page HTML
aio browser text                              # Get visible text
aio browser markdown                          # Get as markdown
aio browser evaluate "document.title"         # Run JavaScript
aio browser console                           # Get console logs

# Tabs
aio browser tabs                              # List tabs
aio browser tab-new https://google.com        # Open new tab
aio browser tab-close 1                       # Close tab

# Wait for conditions
aio browser wait selector --selector ".loaded" --timeout 10
aio browser wait load                         # Wait for page load
aio browser wait url --url "**/dashboard"     # Wait for URL
aio browser wait network_idle                 # Wait for network

# Snapshot (accessibility tree)
aio browser snapshot                          # Get page elements

# Session
aio browser restart                           # Restart browser
aio browser restart --mode soft               # Soft restart
```

### GUI Actions (Low-level Mouse & Keyboard)

```bash
# Screenshot
aio gui screenshot                            # Desktop screenshot
aio gui screenshot -o desktop.png

# Mouse
aio gui tap 500 300                           # Click at (500, 300)
aio gui double-click 500 300                  # Double-click
aio gui right-click 500 300                   # Right-click
aio gui move 200 400                          # Move cursor
aio gui drag 800 600                          # Drag to position
aio gui scroll --dx 0 --dy -300              # Scroll

# Keyboard
aio gui type "Hello World"                    # Type text
aio gui press Enter                           # Press key
aio gui hotkey ctrl c                         # Key combination

# Utility
aio gui wait 2                                # Wait 2 seconds
aio gui info                                  # Get screen info
```

### Sandbox Info

```bash
aio sandbox info                              # Environment info
aio sandbox packages --python                 # Python packages
aio sandbox packages --nodejs                 # Node.js packages
```

### Skills

```bash
# Register skills from a sandbox directory
aio skills register --path /workspace/skills

# Register from a local zip file
aio skills register --zip ./skills.zip --to /workspace/skills

# List skills
aio skills list
aio skills list --names foo bar

# Load skill content
aio skills load foo
aio skills content foo

# Delete a skill
aio skills delete foo
```

### MCP Server Management

```bash
# List configured MCP servers
aio mcp list

# List tools from a specific server
aio mcp tools my-server

# Call a tool on a server
aio mcp call my-server tool_name --args '{"param": "value"}'
```

## Common Patterns

### Run a script and check output

```bash
aio file write /workspace/script.py --content "print('hello')"
aio bash "python /workspace/script.py"
```

### Search code, then edit

```bash
# Find all Python files with a pattern
aio file grep "def process_data" /workspace --include "*.py"
# Read the relevant file
aio file read /workspace/src/utils.py --start 40 --end 60
# Make a replacement
aio file replace /workspace/src/utils.py --old "def process_data(x):" --new "def process_data(x, validate=True):"
```

### Web scraping workflow

```bash
aio browser navigate https://example.com/data
aio browser wait load
aio browser text > page-content.txt
aio browser screenshot -o evidence.png
```

### Install packages and run tests

```bash
aio bash "pip install -r requirements.txt" --timeout 120
aio bash "cd /workspace && python -m pytest tests/ -v"
```

### Explore directory structure

```bash
aio file glob "**/*" /workspace --dirs --max-results 100
aio file list /workspace --recursive --depth 2
```

### Multi-file search with context

```bash
# Find all error handlers with surrounding context
aio file grep "except\s+\w+Error" /workspace --include "*.py" -B 2 -A 5
# Find TODO comments case-insensitively
aio file grep "todo|fixme|hack" /workspace -i --include "*.py" "*.js" "*.ts"
```

## Output Modes

- **TTY (terminal):** Human-readable text with colors and tables
- **Piped:** Automatic JSON output for scripting

Force a specific format with `--output`:

```bash
aio bash "ls" --output json          # JSON output
aio file list /workspace --output table   # Table output
```

## Global Options

| Option | Description |
|--------|-------------|
| `--api-url <url>` | Override API base URL |
| `--output <format>` | Output format: `json`, `table`, `text` |
| `-v, --verbose` | Show request/response details |
| `-q, --quiet` | Suppress non-essential output |

## Deep-Dive References

### Command References

| Reference | When to Use |
|-----------|-------------|
| [references/bash.md](references/bash.md) | Shell execution, sessions, async commands |
| [references/file.md](references/file.md) | File read/write, grep, glob, search, upload/download |
| [references/browser.md](references/browser.md) | Playwright browser automation, screenshots, element interaction |
| [references/gui.md](references/gui.md) | Low-level mouse/keyboard, desktop screenshots |
| [references/sandbox.md](references/sandbox.md) | Environment info, packages |
| [references/mcp.md](references/mcp.md) | MCP server management, tool execution, configuration |

### Topic Guides

| Reference | When to Use |
|-----------|-------------|
| [references/configuration.md](references/configuration.md) | Config files, env vars, output modes, piping, scripting |
| [references/file-search-patterns.md](references/file-search-patterns.md) | grep vs glob vs search, codebase exploration, refactoring |
| [references/browser-workflows.md](references/browser-workflows.md) | Form submission, web scraping, SPA, screenshot docs, testing |
| [references/shell-sessions.md](references/shell-sessions.md) | Async execution, long-running tasks, session reuse, pipelines |

## Ready-to-Use Templates

| Template | Description |
|----------|-------------|
| [templates/code-search-replace.sh](templates/code-search-replace.sh) | Search and replace across a codebase |
| [templates/web-scraping.sh](templates/web-scraping.sh) | Navigate, extract content, save results |
| [templates/dev-setup.sh](templates/dev-setup.sh) | Auto-detect project type and set up environment |

```bash
./templates/code-search-replace.sh "old_func" /workspace "*.py"
./templates/web-scraping.sh https://example.com ./output
./templates/dev-setup.sh /workspace
```
