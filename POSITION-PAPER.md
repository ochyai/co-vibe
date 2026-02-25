# co-vibe: A Multi-Provider Terminal Agent for Autonomous Research and Development

**Yoichi Ochiai**
University of Tsukuba / Digital Nature Group

*Position Paper — February 2026*

---

## Abstract

We present **co-vibe**, an open-source, pure-Python terminal agent designed for researchers who require transparent, debuggable, and extensible AI assistance across the full spectrum of research and development tasks. Unlike proprietary AI coding assistants that operate as opaque black boxes, co-vibe is a single-file, zero-dependency agent (10,500+ lines of Python) that routes requests across multiple LLM providers — Anthropic, OpenAI, Groq, and local Ollama models — with 3-tier smart routing, automatic failover, and full execution traceability. co-vibe is not merely a coding assistant: it is the foundation for an autonomous research partner that bridges local computation and cloud intelligence, monitors laboratory equipment, and enables long-running R&D sessions where the boundary between human researcher and AI collaborator dissolves. This paper articulates the design philosophy, architecture, and roadmap toward realizing co-vibe as a practical instrument for experiencing AGI and ASI — not as distant abstractions, but as daily research tools.

---

## 1. Introduction: Why Another Agent?

### 1.1 The Black-Box Problem

The current generation of AI coding assistants — Claude Code, Cursor, GitHub Copilot, Windsurf — are remarkable tools. They can read codebases, execute commands, edit files, and carry on multi-turn conversations with increasingly sophisticated reasoning. For software engineers, they represent a genuine productivity multiplier.

But for **researchers**, they present a fundamental problem: **opacity**.

When Claude Code selects a model, routes a request, retries after failure, or compacts a conversation context, the researcher cannot inspect, modify, or learn from these decisions. The agent is a service, not an instrument. You cannot attach a debugger to it. You cannot read its routing logic. You cannot modify its tool implementations to interface with your laboratory equipment. You cannot analyze its execution logs to understand *why* it chose a particular approach.

This is not a criticism of these tools — they are optimized for developer productivity, not research transparency. But it reveals a gap:

> **The gap between "AI coding assistant" and "AI research partner" is the gap between a black box and an inspectable instrument.**

### 1.2 What Researchers Need

A research-grade AI agent must satisfy requirements that commercial tools are not designed to address:

1. **Full auditability** — Every API call, every model selection decision, every tool invocation must be logged and inspectable. When an experiment fails, the researcher must be able to trace the agent's reasoning chain.

2. **Extensibility at the source level** — Researchers need to add new tools (equipment controllers, custom analyzers, domain-specific parsers) without navigating plugin APIs or extension marketplaces. The source code *is* the API.

3. **Provider independence** — Research budgets fluctuate. Hardware availability changes. A research tool cannot be locked to a single provider. It must gracefully route between cloud APIs and local models.

4. **Long-running autonomy** — Research sessions are not 5-minute chat interactions. They are 8-hour workdays where the agent monitors experiments, processes data, and reports anomalies. The agent must handle rate limits, context overflow, and provider outages without human intervention.

5. **Self-improvement** — The agent should learn from its own execution patterns. Which model tier works best for which task type? Which tool sequences lead to success? This data should be collected, analyzed, and fed back into the agent's decision-making.

co-vibe is built to satisfy these requirements.

---

## 2. Design Philosophy

### 2.1 Pure Python, Zero Dependencies

co-vibe uses **only Python standard library modules**. No `pip install`. No `requirements.txt`. No virtual environments. The entire agent runs on a fresh Python 3.8+ installation.

```python
# co-vibe.py — imports (complete list)
import json, os, sys, re, time, uuid, signal, argparse
import subprocess, fnmatch, platform, shutil, tempfile
import threading, unicodedata, urllib.request, urllib.error
import urllib.parse, hashlib, traceback, base64, atexit
import collections, concurrent.futures, ssl
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
```

This is a deliberate architectural constraint, not a limitation. It guarantees:

- **Reproducibility** — The agent behaves identically on any machine with Python 3.8+. No dependency version conflicts. No broken package installations.
- **Auditability** — Every line of behavior is in one file. There are no transitive dependencies hiding unexpected behaviors.
- **Portability** — Works on macOS, Linux, and Windows. Works in containers, on servers, on Raspberry Pi, on air-gapped laboratory machines.
- **Security** — No supply chain attacks through compromised packages. The attack surface is Python's stdlib and the agent's own code.

### 2.2 Single-File Architecture

co-vibe is one file: `co-vibe.py`, currently 10,578 lines. This sounds unwieldy but is, in practice, remarkably navigable:

```bash
# Find any class
grep -n "^class " co-vibe.py

# Find all tool implementations
grep -n "class.*Tool" co-vibe.py

# Find the routing logic
grep -n "def _select_model" co-vibe.py

# Find the complexity classifier
grep -n "def _classify_complexity" co-vibe.py
```

The single-file constraint enforces **locality of reference**. When debugging provider failover behavior, you do not need to navigate across 47 files in 12 directories. The provider client, the model registry, the retry logic, and the health tracker are all within scrolling distance of each other.

The internal structure follows a clear top-to-bottom layout:

```
Lines     Component
──────────────────────────────────────────────────────
1-120     Constants, thread-safe utilities, signal handlers
120-714   ANSI colors, ScrollRegion (TUI), terminal utilities
715-1426  Config (strategy, keys, env, CLI args, .claude/settings)
1427-2628 MultiProviderClient (API routing, SSE streaming, failover)
2629-3800 Core Tools (Bash, Read, Write, Edit, Glob, Grep, Web, Notebook)
3800-4600 Task Tools + SubAgent (task graph, autonomous sub-agents)
4600-5220 MCP Client (JSON-RPC 2.0, external tool servers)
5220-5520 GitCheckpoint, AutoTestRunner, FileWatcher
5520-5910 AgentBlackboard, ExecutionMemory, PersistentMemory
5910-6110 MultiAgentCoordinator (thread pool, work stealing)
6110-6830 ParallelAgentTool, ToolRegistry, Permission system
6830-7145 Orchestrator skill loader, DAG visualization
7145-8910 Session (history, compaction, persistence), TUI (input, output)
8910-10578 Agent (main loop, 3-tier routing, complexity classifier)
```

### 2.3 Multi-Provider by Design

co-vibe treats LLM providers as interchangeable resources in a pool, not as monolithic backends. The model registry maps every supported model to its provider, capability tier, and context window:

```python
MODELS = [
    # Strong tier — deep reasoning, complex architecture
    ("anthropic", "claude-opus-4-6",           "strong",   200000),
    ("openai",    "o3",                        "strong",   200000),
    ("groq",      "deepseek-r1-distill-llama-70b", "strong", 131072),
    # Balanced tier — everyday coding, moderate tasks
    ("anthropic", "claude-sonnet-4-6",         "balanced", 200000),
    ("openai",    "gpt-4.1",                   "balanced", 128000),
    ("groq",      "llama-3.3-70b-versatile",   "balanced", 131072),
    # Fast tier — simple tasks, quick answers
    ("anthropic", "claude-haiku-4-5-20251001", "fast",     200000),
    ("openai",    "gpt-5-mini",                "fast",     128000),
    ("groq",      "llama-3.1-8b-instant",      "fast",     131072),
    # Local models via Ollama
    ("ollama",    "qwen2.5-coder:32b",         "strong",   32768),
    ("ollama",    "deepseek-coder-v2:16b",     "balanced", 32768),
]
```

When a provider is rate-limited or unavailable, co-vibe automatically fails over to the next healthy provider in the same tier. Health tracking uses a 60-second cooldown window per provider, preventing cascade failures.

### 2.4 3-Tier Smart Routing

Not every task requires the most powerful model. co-vibe's orchestrator classifies incoming requests into three complexity tiers:

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Input                                  │
│  "Fix the race condition in the thread pool"                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  _classify_    │
              │  complexity()  │   regex + heuristic + memory
              └───┬────┬───┬──┘
                  │    │   │
         strong ──┘    │   └── fast
                       │
                  balanced
                       │
                       ▼
              ┌────────────────┐
              │ ExecutionMemory│   historical success rates
              │  .recommend_  │   per tier × task type
              │   tier()      │
              └───────┬───────┘
                      │
                      ▼
              ┌────────────────┐
              │  Model Pool    │   select from available
              │  + Failover    │   providers in target tier
              └────────────────┘
```

The classifier uses bilingual pattern matching (English and Japanese) to detect task complexity:

- **Strong triggers**: "architect", "refactor entire", "debug...complex", "design system", "セキュリティ監査"
- **Fast triggers**: short questions, "yes/no", typo fixes, simple formatting requests
- **Balanced**: everything else (the safe default)

Crucially, the `ExecutionMemory` system feeds historical performance data back into tier selection. If balanced-tier models consistently succeed at tasks the classifier marks as "strong", the system learns to route similar tasks to balanced — saving cost and latency without sacrificing quality.

### 2.5 Debug-First

Every architectural decision in co-vibe prioritizes debuggability:

```bash
# Enable debug mode
python3 co-vibe.py --debug

# Debug output includes:
# [orchestrator] tier=balanced (classified=balanced) -> anthropic/claude-sonnet-4-6
# [provider] POST https://api.anthropic.com/... status=200 latency=1.23s
# [tool:Bash] command="git status" exit_code=0 duration=0.05s
# [session] compaction triggered: 87% context used, preserving 30 messages
# [failover] anthropic rate-limited, trying openai (health: ok)
```

The `--debug` flag is not an afterthought bolted onto a release build. Debug logging is woven into every critical path: model selection, API calls, tool execution, session compaction, provider failover, and multi-agent coordination. The TUI debug mode (`CO_VIBE_DEBUG_TUI=1`) additionally logs raw ANSI escape sequences to `/tmp/co-vibe-tui-debug.log` for terminal rendering issues.

---

## 3. Architecture Overview

### 3.1 System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          co-vibe.py                                  │
│                     (single file, ~10.5K lines)                      │
│                                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────────┐   │
│  │  Config   │  │     TUI      │  │         Agent                │   │
│  │ strategy  │  │  ScrollRegion│  │  3-tier orchestrator         │   │
│  │ keys/env  │  │  streaming   │  │  complexity classifier       │   │
│  │ CLI args  │  │  ESC cancel  │  │  tool loop (max 50 iter)     │   │
│  └──────────┘  └──────────────┘  │  plan mode / act mode         │   │
│                                   └──────────┬───────────────────┘   │
│                                              │                       │
│  ┌───────────────────────────────────────────┼───────────────────┐   │
│  │              MultiProviderClient          │                   │   │
│  │  ┌──────────┬──────────┬──────────┬──────────┐               │   │
│  │  │Anthropic │ OpenAI   │  Groq    │ Ollama   │               │   │
│  │  │  Claude  │ GPT/o3   │  Llama   │  Local   │               │   │
│  │  └────┬─────┴────┬─────┴────┬─────┴────┬─────┘               │   │
│  │       │          │          │          │                       │   │
│  │  Health tracking + auto-failover + rate limit handling        │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │                     Tool Registry                             │   │
│  │  ┌──────┬──────┬───────┬──────┬──────┬────────┬───────────┐  │   │
│  │  │ Bash │ Read │ Write │ Edit │ Glob │  Grep  │  WebFetch │  │   │
│  │  │      │      │       │      │      │        │ WebSearch │  │   │
│  │  ├──────┴──────┴───────┴──────┴──────┴────────┴───────────┤  │   │
│  │  │ SubAgent │ ParallelAgents │ Task* │ NotebookEdit │ MCP │  │   │
│  │  └──────────┴────────────────┴───────┴──────────────┴─────┘  │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ Session          │  │ ExecutionMemory│  │ PersistentMemory   │   │
│  │ history/compact  │  │ tier learning  │  │ cross-session ctx  │   │
│  │ save/resume      │  │ pattern track  │  │ auto-summarize     │   │
│  └──────────────────┘  └────────────────┘  └────────────────────┘   │
│                                                                      │
│  ┌──────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ GitCheckpoint    │  │ AutoTestRunner │  │ FileWatcher        │   │
│  │ stash rollback   │  │ post-edit test │  │ mtime polling      │   │
│  └──────────────────┘  └────────────────┘  └────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Tool System

co-vibe implements 17 tools via a unified `Tool` abstract base class:

| Tool | Purpose | Safety |
|------|---------|--------|
| **Bash** | Command execution with timeout, background mode, security checks | Permission required |
| **Read** | File reading with line numbers, image/PDF/Jupyter support | Safe (read-only) |
| **Write** | Atomic file writing with undo stack | Permission required |
| **Edit** | String replacement with Unicode NFC normalization | Permission required |
| **Glob** | Pattern matching via `os.walk` (symlink-safe, OOM-protected) | Safe |
| **Grep** | Regex search with context lines, ReDoS defense | Safe |
| **WebFetch** | URL retrieval with SSRF protection, HTML-to-text | Safe |
| **WebSearch** | DuckDuckGo search with rate limiting | Safe |
| **NotebookEdit** | Jupyter notebook cell editing | Permission required |
| **SubAgent** | Autonomous sub-agent with isolated conversation | Configurable |
| **ParallelAgents** | 2-6 concurrent sub-agents with progress tracking | Configurable |
| **TaskCreate/List/Get/Update** | In-memory task graph with dependency tracking | Safe |
| **AskUserQuestion** | Structured user interaction | Safe |
| **MCP Tools** | External tool servers via JSON-RPC 2.0 | Configurable |

Tools that modify the filesystem or execute commands require explicit user permission (unless `--dangerously-skip-permissions` or `-y` is specified). Read-only tools execute without prompting.

### 3.3 Multi-Agent Orchestration

For complex tasks requiring parallel work, co-vibe provides a `MultiAgentCoordinator` that manages a thread-based execution pool:

```
┌─────────────────────────────────────────────────────┐
│              ParallelAgentTool                       │
│   "Run these 6 tasks concurrently"                  │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────┴────────┐
              │ MultiAgent      │
              │ Coordinator     │
              │ (thread pool)   │
              └───┬──┬──┬──┬───┘
                  │  │  │  │
         ┌────┐ ┌┴┐ ┌┴┐ ┌┴┐ ┌────┐
         │ A1 │ │A2│ │A3│ │A4│ │ A5 │   Sub-agents
         └──┬─┘ └┬─┘ └┬─┘ └┬─┘ └──┬─┘
            │    │    │    │      │
            └────┴────┼────┴──────┘
                      │
              ┌───────┴───────┐
              │ AgentBlackboard│   Thread-safe shared memory
              │ (key-value +   │   for cross-agent knowledge
              │  ordered log)  │   sharing
              └───────────────┘
```

Each sub-agent operates with its own conversation context but shares a `AgentBlackboard` for cross-agent knowledge exchange. The coordinator handles:

- Staggered launch (0.3s between agents) to avoid API rate limit bursts
- Heartbeat-based progress monitoring
- Cancellation via `threading.Event` (Ctrl+C propagation)
- Result aggregation with per-agent error isolation

### 3.4 Session Persistence and Context Compaction

Long research sessions generate conversation histories that exceed model context windows. co-vibe handles this through automatic context compaction:

1. **Threshold detection** — When conversation tokens reach 70% of the model's context window, compaction triggers.
2. **Sidecar summarization** — A fast-tier model (Haiku or GPT-mini) summarizes older messages into a condensed context block.
3. **Preservation window** — The most recent 30 messages are always preserved verbatim, ensuring the agent never loses immediate context.
4. **Session serialization** — Conversations are persisted as JSONL files, enabling `--resume` across process restarts.

This architecture supports the long-running autonomous sessions (8+ hours) that research workflows demand.

---

## 4. Self-Improvement Architecture

### 4.1 ExecutionMemory: Learning from Every Run

co-vibe records structured execution data for every task:

```json
{
  "task_type": "debug",
  "tier": "strong",
  "model": "claude-opus-4-6",
  "tools_used": ["Read", "Grep", "Edit", "Bash"],
  "duration_seconds": 45.2,
  "success": true,
  "timestamp": "2026-02-25T10:30:00Z"
}
```

Over time, `ExecutionMemory` accumulates enough data to recommend tier adjustments:

- If "debug" tasks succeed 95% of the time on balanced-tier models, demote future debug tasks to balanced (saving cost and latency).
- If "architecture" tasks fail 40% of the time on balanced, promote them to strong.
- Prevent 2-level demotions (strong tasks cannot drop directly to fast) to maintain a safety margin.

The memory persists to `.co-vibe-memory.json` in the project directory, surviving across sessions.

### 4.2 PersistentMemory: Cross-Session Context

`PersistentMemory` maintains a running record of key decisions, file modifications, and task states across sessions. When entries exceed 100, automatic summarization compresses older entries while preserving their semantic content. This enables:

- **Session resumption** — The agent recalls what was being worked on, even after a cold restart.
- **Sub-agent context injection** — Spawned sub-agents receive relevant project context without redundant exploration.
- **Pattern accumulation** — User preferences, common workflows, and project conventions are captured implicitly.

### 4.3 The Feedback Loop

```
┌──────────────────────────────────────────────────────────────────┐
│                    Self-Improvement Cycle                         │
│                                                                  │
│  Task Execution ──→ Log Recording ──→ Pattern Extraction         │
│       ↑                                        │                 │
│       │                                        ▼                 │
│  Tier Selection ←── Memory Query ←── Success/Failure Analysis    │
│                                                                  │
│  Every tool call, every API response, every user correction      │
│  feeds back into the agent's decision-making.                    │
└──────────────────────────────────────────────────────────────────┘
```

This is not hypothetical architecture — it is implemented and running in co-vibe v1.4.0 today. The `recommend_tier()` method actively adjusts model selection based on accumulated execution history.

---

## 5. ロードマップ: AGIへの道筋

co-vibeは単なるコーディングアシスタントではない。自律的な研究パートナーへの進化を目指すプロジェクトである。以下に、現在地からAGI的な研究協力者に至るまでのロードマップを示す。

### Phase 1: 基盤強化 (Foundation) — 現在進行中

現在のco-vibe v1.4.0は、11件の重大バグ修正と371のテストケースを経て、安定した基盤を確立しつつある。

**完了した取り組み:**
- スレッド安全性の確保（`_bg_tasks_lock`、`AgentBlackboard._lock`、並列ツール実行のロック）
- Glob OOM問題の解決（`os.walk(followlinks=False)` + イテレーション上限）
- SSEバッファの安全な成長制限
- レートリミット時の無限ループ防止（最大リトライ回数の導入）
- オーケストレータの誤分類修正（複雑なクエリがfast tierに落ちる問題）
- ターミナル状態の確実な復元（SIGTERM/SIGHUPハンドラ）

**今後の課題:**
- テストカバレッジの拡充（現在371件 → 目標1000件）
- エラーハンドリングの体系的改善（30箇所の`except Exception: pass`の精査）
- Windows環境での完全な動作保証
- CI/CDパイプラインの構築

### Phase 2: 知覚と対話の拡張 (Perception & Interaction)

研究パートナーとしてのAIに必要なのは、コードを読み書きする能力だけではない。研究者の「目」と「手」となる知覚・操作能力の拡張が不可欠である。

**Deep Research ツール:**
- マルチステップWeb調査（クエリ分解 → 並列検索 → 統合 → 引用付き出力）
- 論文検索とサーベイの自動生成（arXiv, Semantic Scholar, Google Scholar連携）
- 先行研究との差分分析と新規性の評価

**ストリーミングUI改善:**
- thinking表示（モデルの推論過程をリアルタイムで可視化）
- ツール実行のリアルタイムフィードバック（進捗バー、中間結果表示）
- マルチモーダル出力（画像、グラフ、3Dモデルのインライン表示）

**機器制御インターフェース:**
- 3Dプリンタ制御（G-codeの生成・送信・モニタリング）
- ラボ機器との通信（シリアルポート、GPIB、SCPI）
- IoTデバイス統合（MQTT、REST API）
- 製造プロセスの異常検知と自動停止

**カメラ・センサー統合:**
- USBカメラ / IPカメラからのリアルタイム映像取得
- Vision LLMによる視覚的モニタリング（「3Dプリンタのベッドレベリングは正常か？」）
- センサーデータの時系列解析（温度、湿度、振動、光学測定）

### Phase 3: 自律と自己改善 (Autonomy & Self-Improvement)

この段階では、co-vibeは単にユーザーの指示を実行するツールから、自ら学習し改善するエージェントへと進化する。

**実行ログの自動分析と知見抽出:**
- 全ツール呼び出し、全API応答、全ユーザー修正の構造化ログ
- 失敗パターンの自動検出（「このタイプのファイル編集は3回に1回失敗する」）
- 成功パターンのテンプレート化（「Pythonのリファクタリングは Grep → Read → Edit の順序が最適」）

**エージェントの自己改善ループ:**
- プロンプトの自動最適化（成功率の高い指示パターンの学習）
- ツール選択戦略の動的調整（ExecutionMemoryの拡張）
- エラー回復パターンの蓄積と自動適用

**長期記憶と知識グラフの構築:**
- プロジェクト固有の知識ベース（コードベースの構造、命名規則、設計方針）
- 研究ドメインの知識グラフ（論文間の関係、手法の比較、結果の蓄積）
- ユーザープリファレンスの学習（好みのコーディングスタイル、コミュニケーション言語）

**マルチセッション横断的な学習:**
- セッション間での知見の伝播（「昨日のデバッグで発見したパターンを今日の作業に適用」）
- プロジェクト横断的な共通パターンの抽出
- 時間経過に伴う知識の自動整理（重要度に基づく忘却と保持）

### Phase 4: 研究パートナーとしてのAGI (AGI as Research Partner)

最終的に目指すのは、co-vibeが研究者の対等なパートナーとして機能する世界である。

**仮説生成と実験設計の自動化:**
- 既存データからの仮説生成（「この変数を変化させると、出力にどのような影響があるか？」）
- 実験パラメータの最適化（ベイズ最適化、遺伝的アルゴリズム）
- 対照実験の自動設計と実行

**論文読解・サーベイの自律実行:**
- 新着論文の自動チェックと関連性評価
- 分野横断的なサーベイの生成（HCI × 材料科学 × 機械学習）
- 引用ネットワーク分析による重要論文の発見

**実験結果の解釈と次ステップの提案:**
- 統計的有意性の自動検定
- 予想外の結果の検出と解釈の提案
- 次の実験の優先順位付けと計画

**人間研究者との協調的意思決定:**
- 判断の根拠の透明な提示（「この手法を推奨する理由は以下の3点です」）
- 不確実性の明示（「この結論の信頼度は中程度です。追加実験を推奨します」）
- 研究者の直感とAIの分析の統合的な意思決定プロセス

---

## 6. Deep Research: The Next Critical Tool

### 6.1 The Problem

Current web search tools return a list of links. The researcher must then manually read each source, extract relevant information, cross-reference claims, and synthesize a coherent understanding. This is time-consuming but — more importantly — it is exactly the kind of structured, multi-step information processing that AI agents excel at.

### 6.2 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Deep Research Pipeline                         │
│                                                                  │
│  Research Query                                                  │
│  "Compare attention mechanisms for 3D point cloud processing"    │
│                                                                  │
│       │                                                          │
│       ▼                                                          │
│  ┌────────────────┐                                              │
│  │ Query Decomp.  │  Break into sub-queries:                     │
│  │                │  - "point cloud attention mechanisms 2024-26" │
│  │                │  - "transformer architectures 3D data"        │
│  │                │  - "PointNet++ attention variants"             │
│  └───────┬────────┘                                              │
│          │                                                       │
│          ▼                                                       │
│  ┌────────────────┐                                              │
│  │ Parallel Search│  WebSearch × N + arXiv API + Scholar         │
│  │ (SubAgents)    │  Each sub-agent fetches and summarizes       │
│  └───────┬────────┘                                              │
│          │                                                       │
│          ▼                                                       │
│  ┌────────────────┐                                              │
│  │ Source Ranking  │  Deduplicate, rank by relevance,            │
│  │ & Filtering    │  filter by date/venue/citation count         │
│  └───────┬────────┘                                              │
│          │                                                       │
│          ▼                                                       │
│  ┌────────────────┐                                              │
│  │ Deep Reading   │  WebFetch key papers, extract methods,       │
│  │                │  results, limitations                        │
│  └───────┬────────┘                                              │
│          │                                                       │
│          ▼                                                       │
│  ┌────────────────┐                                              │
│  │ Synthesis      │  Strong-tier model synthesizes findings      │
│  │ + Citation     │  with proper citations and comparison table  │
│  └────────────────┘                                              │
│                                                                  │
│  Output: Structured report with citations, comparison tables,    │
│          identified gaps, and suggested research directions       │
└──────────────────────────────────────────────────────────────────┘
```

### 6.3 Why This Matters for co-vibe

Deep Research is not just another tool — it is the bridge between "coding assistant" and "research partner." A system that can autonomously survey literature, identify methodological gaps, and propose novel approaches transforms the researcher's workflow from manual information gathering to strategic decision-making.

The implementation leverages co-vibe's existing infrastructure:
- **ParallelAgents** for concurrent search execution
- **AgentBlackboard** for sharing discovered sources across sub-agents
- **ExecutionMemory** for learning which search strategies yield the best results
- **3-tier routing** for using strong models on synthesis, fast models on search

---

## 7. The Vision: Feel AGI and ASI

co-vibe's ultimate goal is not to build AGI. That is a problem for the research community at large. co-vibe's goal is more immediate and more practical:

> **To create a local terminal agent that operates all kinds of equipment while advancing research and development as an autonomous agent.**

This means:

- **Developing new research methods** — The agent proposes, implements, and evaluates novel algorithms, not just transcribes the researcher's ideas into code.
- **Monitoring fabrication equipment** — A 3D printer running an overnight job should be watched by the agent, which can detect anomalies (via camera + sensors), pause the print, and alert the researcher.
- **Drug discovery workflows** — Molecular design, docking simulation orchestration, result analysis, and iteration — all within a single long-running agent session.
- **Algorithm optimization** — The agent profiles code, identifies bottlenecks, proposes optimizations, benchmarks them, and reports results — a complete optimization loop without human intervention.
- **Daily autonomous R&D** — The researcher starts a session in the morning, provides high-level goals, and the agent works throughout the day, asking questions only when genuinely stuck.

To achieve this, the architecture must support:

1. **Debugging one's own log data** — The agent must be able to read its own execution logs, identify failure patterns, and adjust its behavior. co-vibe's `ExecutionMemory` is the first step; the full vision includes the agent analyzing its own source code to fix its own bugs.

2. **Accessing smarter LLMs dynamically** — When the agent encounters a task beyond its current model's capability, it should automatically escalate to a stronger model. co-vibe's 3-tier routing implements this today; the roadmap extends it to cross-session model selection learning.

3. **Self-improvement based on collected information** — Every failure is a learning opportunity. Every user correction is training data. The agent that ran 1000 sessions should be meaningfully better than the one that ran 10.

4. **Transparent, inspectable agent behavior** — No black boxes. Every decision traceable. This is not just an engineering principle — it is an epistemic requirement for research. If the agent's behavior cannot be understood, its outputs cannot be trusted.

The spirit is to **"Feel AGI and ASI"** — not as speculative futurism, but as a tangible daily experience. When a researcher sits down with co-vibe and accomplishes in one day what would have taken a week alone, when the agent catches an error the researcher missed, when it suggests a methodology the researcher had not considered — that is what "feeling AGI" means in practice.

---

## 8. 計算機自然における位置づけ

### 計算機と自然の境界の溶解

落合陽一が提唱する「計算機自然」（Digital Nature）とは、計算機（コンピュータ）と自然（物理世界）の境界が溶解し、両者が不可分に融合した世界観である。波動関数と計算過程、物質とデータ、生態系とアルゴリズムが区別なく混在する環境。

co-vibeは、この計算機自然の思想を研究ツールのレイヤーで実践するプロジェクトである。

### ローカルとクラウドの融合

co-vibeのマルチプロバイダアーキテクチャは、ローカル（Ollama）とクラウド（Anthropic、OpenAI、Groq）のLLMをシームレスに統合する。これは計算機自然における「場所の融解」の実装である。

計算がどこで実行されるか — ローカルのGPU上か、サンフランシスコのデータセンター内か — は、研究者にとって透過的であるべきだ。重要なのは計算の質と速度であり、物理的な所在ではない。co-vibeの3-tier routingは、タスクの性質に応じて最適な計算資源を自動的に選択する。プライバシーが必要ならローカル。深い推論が必要ならクラウド。速度が必要ならGroq。この選択はインフラの制約ではなく、タスクの意味論に基づいて行われる。

### 透明性 = 自然との対話可能性

自然科学の根本原理は観測可能性である。観測できないものは理解できない。同様に、AIエージェントの行動が観測できなければ、研究者はそのエージェントを信頼することも、改善することもできない。

co-vibeの「debug-first」設計思想は、計算機自然における「自然との対話可能性」の実装である。全てのAPI呼び出し、全てのモデル選択判断、全てのツール実行がトレース可能であること。これはエンジニアリング的な美徳であると同時に、科学的な必要条件である。

ブラックボックスのAIエージェントは「超自然的」(supernatural) な存在である。その振る舞いは神託のように受け取るしかなく、なぜそう判断したかを問うことができない。co-vibeは「自然的」(natural) な存在であることを目指す。その振る舞いは観測可能であり、理解可能であり、修正可能である。

### 長時間の自律稼働 = 計算機的な生態系

生態系は24時間365日稼働する。森は眠らない。海流は止まらない。研究室のAIエージェントもまた、そうあるべきだ。

co-vibeが目指す長時間自律稼働は、研究室に「計算機的な生態系」を構築することに等しい。エージェントは実験を監視し、データを分析し、異常を検知し、次のステップを提案する — 研究者が眠っている間も。これはSFではなく、3Dプリンタの長時間ジョブ監視という極めて具体的なユースケースから始まる技術的ロードマップである。

計算機自然の世界では、研究者のエージェントは研究室の生態系の一部となる。センサーからデータを受け取り、アクチュエータを制御し、他のエージェントと協調し、人間研究者と対話する。co-vibeはその最初の一歩である。

### 自己改善する自然

自然は進化する。環境に適応し、より効率的な形態を発見し、多様性を生み出す。co-vibeの`ExecutionMemory`と`PersistentMemory`は、この「進化」の計算機的実装である。エージェントは自らの実行履歴から学び、より効率的な行動パターンを発見し、研究者の好みに適応する。

これは現時点では素朴な実装 — 成功率に基づくtier推奨、パターンマッチによるタスク分類 — に過ぎない。しかし、この方向性こそが計算機自然の本質的な要請である。自然が静的でないように、研究ツールも静的であってはならない。

---

## 9. Conclusion

co-vibe is not just a tool. It is a research methodology embodied in code.

**What it is today:**
- A 10,500-line, single-file, pure-Python terminal agent
- Multi-provider LLM routing with automatic failover across Anthropic, OpenAI, Groq, and Ollama
- 17 tools covering file I/O, code search, web research, sub-agent orchestration, and MCP integration
- 3-tier smart routing with self-improving model selection
- Session persistence enabling multi-hour autonomous operation
- Debug-first architecture with full execution traceability

**What it will become:**
- A perceptual agent that monitors laboratory equipment through cameras and sensors
- A research partner that conducts literature surveys and proposes experiments
- A self-improving system that learns from every interaction
- A node in the Digital Nature ecosystem, bridging computation and physical reality

**What it represents:**
- The principle that research tools must be transparent, not opaque
- The belief that AGI and ASI will first be felt through practical daily tools, not through benchmarks
- The conviction that a single researcher, armed with the right AI partner, can accomplish what once required a team

co-vibe is open-source under the MIT License. Its entire implementation — every class, every method, every constant — is visible in a single file. There are no hidden layers, no proprietary backends, no opaque decision-making. This transparency is not a limitation but a feature: the defining feature of a research instrument, as opposed to a consumer product.

The path from coding assistant to research partner to AGI collaborator is long. But it is a path that can be walked one commit at a time, one tool at a time, one session at a time. co-vibe walks it in the open.

---

**Repository:** [github.com/ochyai/co-vibe](https://github.com/ochyai/co-vibe)
**License:** MIT
**Version:** 1.4.0 (February 2026)
**Author:** Yoichi Ochiai — University of Tsukuba / Digital Nature Group
