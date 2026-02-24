# co-vibe

Multi-provider AI coding agent. Pure Python, zero dependencies.

Route requests across **Anthropic** (Claude), **OpenAI** (GPT-4o/o3), **Groq** (Llama 3.3), and **Ollama** (local LLMs) with strategy-based 3-tier orchestration.

## Features

- **3-Tier Smart Routing** -- Automatically classifies tasks as simple/normal/complex and routes to the appropriate model tier
- **4 Providers** -- Anthropic, OpenAI, Groq, Ollama (local). Fallback across providers on failure
- **Full Tool Suite** -- Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch, Notebook, Sub-Agents, MCP
- **Multi-Agent Orchestration** -- Parallel sub-agent execution with work-stealing thread pool
- **Session Persistence** -- Save/resume conversations with automatic context compaction
- **Interactive TUI** -- Scroll region, real-time streaming, ESC to cancel, slash commands
- **Pure Python** -- No pip install required. Runs on Python 3.8+

## Quick Start

```bash
# 1. Clone
git clone git@github.com:ochyai/co-vibe.git && cd co-vibe

# 2. Setup (interactive wizard)
python3 setup.py

# 3. Launch
python3 co-vibe.py
```

Or manually:

```bash
cp .env.example .env
# Edit .env and add at least one API key
python3 co-vibe.py
```

## Usage

```bash
# Interactive mode (default)
python3 co-vibe.py

# One-shot prompt
python3 co-vibe.py -p "Explain this function"

# Specify model
python3 co-vibe.py -m claude-opus-4-6

# Strategy override
python3 co-vibe.py --strategy fast

# Auto-approve all tool calls
python3 co-vibe.py -y

# Resume last session
python3 co-vibe.py --resume

# Resume specific session
python3 co-vibe.py --session-id <id>

# List saved sessions
python3 co-vibe.py --list-sessions

# Debug mode (verbose logging)
python3 co-vibe.py --debug

# Skip permission prompts (use with caution)
python3 co-vibe.py --dangerously-skip-permissions

# Combine flags
python3 co-vibe.py --debug -y -m claude-sonnet-4-6
```

### Debug Mode

Debug mode prints detailed information to stderr:

```bash
# CLI flag
python3 co-vibe.py --debug

# Environment variable
CO_VIBE_DEBUG=1 python3 co-vibe.py

# TUI-specific debug (logs escape sequences to file)
CO_VIBE_DEBUG_TUI=1 python3 co-vibe.py
# Log file: /tmp/co-vibe-tui-debug.log
```

Debug output includes:
- API request/response details
- Model selection decisions
- Tool execution traces
- Provider health status
- Streaming SSE events
- Context compaction details

### Slash Commands (Interactive Mode)

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/model <name>` | Switch model |
| `/strategy <name>` | Switch routing strategy |
| `/compact` | Force context compaction |
| `/cost` | Show token usage and cost |
| `/undo` | Undo last file write/edit |
| `/clear` | Clear conversation |
| `/plan` | Toggle plan mode |
| `/bg` | List background tasks |
| `/mcp` | Show MCP server status |
| `/skills` | List loaded skills |
| `/dag` | Show task dependency graph |

## Strategies

| Strategy | Behavior | Model Priority |
|----------|----------|----------------|
| `auto` | Smart routing based on task complexity | Adapts per request |
| `strong` | Always use the most capable model | Opus > o3 > Llama-70b |
| `fast` | Prefer fastest response time | Groq > Haiku > GPT-4o-mini |
| `cheap` | Minimize cost per request | Haiku > GPT-4o-mini > Groq |

## Supported Providers

| Provider | Models | Strengths |
|----------|--------|-----------|
| Anthropic | Opus 4.6, Sonnet 4.6, Haiku 4.5 | Quality, reasoning |
| OpenAI | GPT-4o, GPT-4o-mini, o3 | Broad compatibility |
| Groq | Llama 3.3 70B | Speed, low latency |
| Ollama | Any local model | Privacy, offline |

## Configuration

All settings via `.env` file or environment variables. See `.env.example` for full list.

Key settings:
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` -- Provider API keys
- `CO_VIBE_STRATEGY` -- Routing strategy (`auto`, `strong`, `fast`, `cheap`)
- `CO_VIBE_MODEL` -- Force a specific model (overrides strategy)
- `CO_VIBE_MODEL_STRONG` / `CO_VIBE_MODEL_BALANCED` / `CO_VIBE_MODEL_FAST` -- Per-tier model overrides
- `CO_VIBE_DEBUG` -- Enable debug output (`1`)

## Architecture

```
User Input
    |
    v
+-------------------+
|    co-vibe.py     |  10K lines, single-file agent
|  Task Classifier  |  simple / normal / complex
+--------+----------+
         |
    +----+----+--------+---------+
    |         |        |         |
    v         v        v         v
Anthropic  OpenAI    Groq     Ollama
 (Claude)  (GPT-4o) (Llama)  (local)
```

## Running Tests

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_config.py -v

# Run with debug output
python3 -m pytest tests/ -v -s
```

## Project Structure

```
co-vibe/
  co-vibe.py          # Main agent (single-file, pure Python)
  co-vibe.sh           # Shell launcher (loads .env, runs co-vibe.py)
  co-vibe-proxy.py     # OpenAI-compatible proxy server
  setup.py             # Interactive setup wizard
  install.sh           # System-wide installer
  .env.example         # Configuration template
  tests/               # Test suite
  LICENSE              # MIT
```

## License

MIT License. Copyright (c) 2026 Yoichi Ochiai.
