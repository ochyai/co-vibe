# 🤖⚡ Ｃ Ｏ - Ｖ Ｉ Ｂ Ｅ ⚡🤖

```
     ██████╗ ██████╗        ██╗   ██╗██╗██████╗ ███████╗
    ██╔════╝██╔═══██╗       ██║   ██║██║██╔══██╗██╔════╝
    ██║     ██║   ██║ █████╗██║   ██║██║██████╔╝█████╗
    ██║     ██║   ██║ ╚════╝╚██╗ ██╔╝██║██╔══██╗██╔══╝
    ╚██████╗╚██████╔╝        ╚████╔╝ ██║██████╔╝███████╗
     ╚═════╝ ╚═════╝          ╚═══╝  ╚═╝╚═════╝ ╚══════╝
```

> 🌴✨ **Multi-Provider AI Coding Agent** ✨🌴
>
> Pure Python. Zero dependencies. Feel AGI.

**日本語** Anthropic・OpenAI・Groq・Ollamaの4プロバイダを横断するマルチプロバイダAIコーディングエージェント。タスク複雑度に応じた3段オーケストレーション。Deep Research・マルチエージェント・セッション永続化。研究開発のための透明でデバッグ可能なターミナルエージェント。

**English** Multi-provider AI coding agent that routes across Anthropic, OpenAI, Groq, and Ollama with 3-tier smart orchestration. Deep Research, multi-agent parallel execution, session persistence. A transparent, debuggable terminal agent built for research and development.

**中文** 跨 Anthropic、OpenAI、Groq 和 Ollama 四个供应商的多供应商AI编程代理。具有三层智能编排、深度研究、多代理并行执行和会话持久化功能。为研究开发而构建的透明可调试终端代理。

---

## 日本語 | [やさしい にほんご](#やさしい-にほんご) | [English](#english) | [中文](#中文)

### これは何？

ターミナルから自然言語でAIに指示を出し、コーディング・ファイル操作・Web調査・マルチエージェント実行を行う **Pure Python 単一ファイルエージェント**。外部パッケージ不要。

4つのAIプロバイダを動的に切り替え、タスクの複雑さに応じて最適なモデルを自動選択する。

### インストール (3ステップ)

**1.** ターミナルを開く

**2.** 以下をコピペしてEnter：

```bash
git clone https://github.com/ochyai/co-vibe.git && cd co-vibe
```

**3.** セットアップウィザードを実行：

```bash
python3 setup.py
```

APIキーを入力したら起動：

```bash
python3 co-vibe.py
```

### 使い方

```bash
# 対話モード（AIと会話しながらコーディング）
python3 co-vibe.py

# ワンショット（1回だけ質問）
python3 co-vibe.py -p "Pythonでソートアルゴリズムを比較して"

# 戦略を指定（strong/fast/cheap/auto）
python3 co-vibe.py --strategy strong

# モデルを直接指定
python3 co-vibe.py -m claude-opus-4-6

# 自動許可モード（毎回の確認不要・上級者向け）
python3 co-vibe.py -y

# セッション復元
python3 co-vibe.py --resume

# デバッグモード（全APIコール・判断をトレース）
python3 co-vibe.py --debug
```

### スラッシュコマンド

| コマンド | 説明 |
|----------|------|
| `/help` | ヘルプ表示 |
| `/model <名前>` | モデル切替 |
| `/strategy <名前>` | ルーティング戦略変更 |
| `/compact` | コンテキスト圧縮 |
| `/cost` | トークン使用量・コスト表示 |
| `/undo` | 最後のファイル変更を元に戻す |
| `/clear` | 会話クリア |
| `/plan` | プランモード切替 |
| `/bg` | バックグラウンドタスク一覧 |
| `/mcp` | MCPサーバーステータス |

### 3段オーケストレーション

| 戦略 | 動作 | モデル優先度 |
|------|------|-------------|
| `auto` | タスク複雑度で自動ルーティング | 🏆 **推奨** |
| `strong` | 常に最強モデル | Opus > o3 > Llama-70b |
| `fast` | 最速レスポンス | Groq > Haiku > GPT-mini |
| `cheap` | コスト最小化 | Haiku > GPT-mini > Groq |

### 対応プロバイダ

| プロバイダ | モデル | 特徴 |
|-----------|--------|------|
| Anthropic | Opus 4.6, Sonnet 4.6, Haiku 4.5 | 🏆 品質・推論 |
| OpenAI | GPT-4o, GPT-4o-mini, o3 | ⭐ 幅広い互換性 |
| Groq | Llama 3.3 70B, DeepSeek | ⚡ 超高速推論 |
| Ollama | 任意のローカルモデル | 🔒 プライバシー・オフライン |

### トラブルシューティング

<details>
<summary>💡 よくある問題と解決法</summary>

**"No API providers available"**
```bash
# .env にAPIキーを設定
cp .env.example .env
nano .env  # ANTHROPIC_API_KEY=sk-ant-... を追加
```

**"model not found"**
```bash
# 利用可能なモデル一覧を確認
python3 co-vibe.py --debug  # バナーにモデル一覧が表示される
```

**Ollamaを使いたい**
```bash
# Ollamaインストール → モデルをpull → co-vibeが自動検出
ollama pull qwen2.5-coder:7b
python3 co-vibe.py  # Ollamaが自動的にプロバイダに追加される
```

**セッションを復元したい**
```bash
python3 co-vibe.py --list-sessions   # セッション一覧
python3 co-vibe.py --resume           # 最後のセッションを復元
python3 co-vibe.py --session-id <id>  # 特定セッションを復元
```

**UIがおかしい（文字化け・レイアウト崩れ）**
```bash
CO_VIBE_DEBUG_TUI=1 python3 co-vibe.py  # TUIデバッグログを有効化
# ログ: /tmp/co-vibe-tui-debug.log
```

</details>

---

## やさしい にほんご

### これは なに？

ターミナルで、AI（えーあい）に プログラムを かいて もらう どうぐ です。
いろいろな AI（Anthropic、OpenAI、Groq、Ollama）を つかいわけて、
いちばん いい AI を えらんで くれます。

### いれかた（3つの ステップ）

**1.** ターミナルを ひらく（`Cmd+Space` → 「ターミナル」で けんさく）

**2.** したの もじを コピーして、はりつけて、Enterを おす：

```bash
git clone https://github.com/ochyai/co-vibe.git && cd co-vibe
```

**3.** セットアップを する：

```bash
python3 setup.py
```

おわったら、これで きどう：

```bash
python3 co-vibe.py
```

### つかいかた

```bash
# AIと はなしながら プログラムを つくる
python3 co-vibe.py

# 1かいだけ しつもんする
python3 co-vibe.py -p "Pythonで じゃんけんゲームを つくって"

# デバッグモード（くわしい じょうほうを みる）
python3 co-vibe.py --debug
```

### きをつけること

> **⚠️ だいじ：AIは まちがえることが あります！**

AIが うごかそうとする コマンド（めいれい）を よく みてください。
わからない コマンドは、**ぜったいに `y`（はい）を おさないで ください。**

| きけんな キーワード | なぜ あぶない？ |
|---|---|
| `sudo` で はじまる | パソコンの だいじな せっていが かわる |
| `rm -rf` | ファイルが ぜんぶ きえる（もどせない！） |
| `chmod` が はいっている | ファイルの まもりが なくなる |
| いみが わからない ながい コマンド | なにが おきるか わからない！ |

**あんぜんに つかう ほうほう：**

- はじめて つかうときは、`-y` を **つけないで** ください（あんぜんモード）
- AIが コマンドを うつまえに、「これを うっていい？」と きいてきます
- わからない コマンドは **ぜったいに ゆるさないで ください**
- こまったら、`Ctrl+C`（コントロール と C を いっしょに おす）で とまります

---

## English

### What is this?

A single-file, pure Python AI coding agent that talks to 4 providers (Anthropic, OpenAI, Groq, Ollama) and picks the best model for each task. No pip install needed. No external dependencies.

### Install (3 steps)

**1.** Open Terminal

**2.** Clone and enter:

```bash
git clone https://github.com/ochyai/co-vibe.git && cd co-vibe
```

**3.** Run the setup wizard:

```bash
python3 setup.py
```

Then launch:

```bash
python3 co-vibe.py
```

### Usage

```bash
# Interactive mode (chat with AI while coding)
python3 co-vibe.py

# One-shot (ask once)
python3 co-vibe.py -p "Compare sorting algorithms in Python"

# Choose strategy (strong/fast/cheap/auto)
python3 co-vibe.py --strategy strong

# Specify model directly
python3 co-vibe.py -m claude-opus-4-6

# Auto-approve all tool calls (advanced users)
python3 co-vibe.py -y

# Resume last session
python3 co-vibe.py --resume

# Debug mode (trace every API call and decision)
python3 co-vibe.py --debug
```

### 3-Tier Orchestration

| Strategy | Behavior | Model Priority |
|----------|----------|----------------|
| `auto` | Smart routing based on task complexity | 🏆 **Recommended** |
| `strong` | Always use most capable model | Opus > o3 > Llama-70b |
| `fast` | Fastest response time | Groq > Haiku > GPT-mini |
| `cheap` | Minimize cost | Haiku > GPT-mini > Groq |

### Supported Providers

| Provider | Models | Strengths |
|----------|--------|-----------|
| Anthropic | Opus 4.6, Sonnet 4.6, Haiku 4.5 | 🏆 Quality, reasoning |
| OpenAI | GPT-4o, GPT-4o-mini, o3 | ⭐ Broad compatibility |
| Groq | Llama 3.3 70B, DeepSeek | ⚡ Ultra-fast inference |
| Ollama | Any local model | 🔒 Privacy, offline |

### Troubleshooting

<details>
<summary>💡 Common issues and solutions</summary>

**"No API providers available"**
```bash
cp .env.example .env
nano .env  # Add ANTHROPIC_API_KEY=sk-ant-...
```

**"model not found"**
```bash
python3 co-vibe.py --debug  # Banner shows available models
```

**Want to use Ollama?**
```bash
ollama pull qwen2.5-coder:7b
python3 co-vibe.py  # Ollama auto-detected as a provider
```

**Resume a session**
```bash
python3 co-vibe.py --list-sessions
python3 co-vibe.py --resume
```

</details>

---

## 中文

### 这是什么？

一个纯Python单文件AI编程代理，可连接4个供应商（Anthropic、OpenAI、Groq、Ollama），为每个任务自动选择最佳模型。无需pip安装，零外部依赖。

### 安装（3步）

**1.** 打开终端

**2.** 克隆并进入：

```bash
git clone https://github.com/ochyai/co-vibe.git && cd co-vibe
```

**3.** 运行设置向导：

```bash
python3 setup.py
```

然后启动：

```bash
python3 co-vibe.py
```

### 使用方法

```bash
# 交互模式（与AI对话编程）
python3 co-vibe.py

# 单次执行
python3 co-vibe.py -p "用Python比较排序算法"

# 选择策略
python3 co-vibe.py --strategy strong

# 自动批准模式（仅限高级用户）
python3 co-vibe.py -y

# 恢复上次会话
python3 co-vibe.py --resume

# 调试模式
python3 co-vibe.py --debug
```

### 三层编排

| 策略 | 行为 | 模型优先级 |
|------|------|-----------|
| `auto` | 根据任务复杂度智能路由 | 🏆 **推荐** |
| `strong` | 始终使用最强模型 | Opus > o3 > Llama-70b |
| `fast` | 最快响应时间 | Groq > Haiku > GPT-mini |
| `cheap` | 最小化成本 | Haiku > GPT-mini > Groq |

### 支持的供应商

| 供应商 | 模型 | 优势 |
|--------|------|------|
| Anthropic | Opus 4.6, Sonnet 4.6, Haiku 4.5 | 🏆 质量、推理 |
| OpenAI | GPT-4o, GPT-4o-mini, o3 | ⭐ 广泛兼容 |
| Groq | Llama 3.3 70B, DeepSeek | ⚡ 超快推理 |
| Ollama | 任意本地模型 | 🔒 隐私、离线 |

<details>
<summary>💡 常见问题及解决方法</summary>

**"No API providers available"**
```bash
cp .env.example .env
nano .env  # 添加 ANTHROPIC_API_KEY=sk-ant-...
```

**想使用Ollama？**
```bash
ollama pull qwen2.5-coder:7b
python3 co-vibe.py  # 自动检测Ollama作为供应商
```

</details>

---

## 🔧 Architecture

```
User ←→ TUI (scroll region, streaming, ESC cancel)
          ↓
        Agent (3-tier task classifier)
          ↓
    MultiProviderClient (health tracking, auto-failover)
          ↓
   ┌──────┼──────┬──────────┐
   ↓      ↓      ↓          ↓
Anthropic OpenAI  Groq     Ollama
 (Claude) (GPT)  (Llama)  (local)
          ↓
    ToolRegistry
   ┌──┬──┬──┬──┬──┬──┬──┬──┐
   │Ba│Rd│Wr│Ed│Gl│Gr│WF│WS│  ... + 10 more tools
   │sh│  │it│it│ob│ep│et│ea│
   └──┴──┴──┴──┴──┴──┴──┴──┘
   SubAgent │ DeepResearch │ MCP │ Notebook │ Parallel
```

### Key Features

| Feature | Description |
|---------|-------------|
| 🧠 **3-Tier Routing** | simple → fast model, normal → balanced, complex → strong |
| 🔬 **Deep Research** | Multi-step web research: decompose → parallel search → synthesize |
| 🤖 **Multi-Agent** | Parallel sub-agents with work-stealing thread pool |
| 💭 **Thinking Display** | Shows model reasoning (`<think>` blocks) in real-time, dimmed |
| 💾 **Session Persistence** | Save/resume with automatic context compaction |
| 🔌 **MCP Support** | Connect external tools via Model Context Protocol |
| 🛡️ **Permission System** | Confirm/auto-approve/skip modes for tool execution |
| 📊 **Cost Tracking** | Per-turn token usage and estimated cost |

---

## 🚨 Security / セキュリティ / 安全须知

### 日本語

> **⚠️ AIが実行するコマンドには注意が必要です。自己責任でご利用ください。**

co-vibe はAIエージェントとして **ファイルの読み書き・コマンド実行・Web通信** を行います。

#### 注意すべきコマンド

| 注意すべきキーワード | リスク |
|---|---|
| `sudo` で始まるコマンド | システム全体に影響する管理者権限での操作 |
| `rm -rf` | ファイルやディレクトリの不可逆な削除 |
| `chmod` / `chown` | ファイルの権限やセキュリティ設定が変わる |
| `dd` / `mkfs` / `/dev/` | ディスクやパーティションを直接操作する |
| `--force` / `--no-verify` | 安全確認をスキップして強制実行する |
| 意味がわからない長いコマンド | 何が起きるかわからない＝許可してはいけない |

#### 安全に使うためのルール

1. **初回は通常モード（確認あり）で起動する** — `-y` フラグなしで開始
2. **わからないコマンドは `n` で拒否する**
3. **大事なファイルがあるフォルダでは新しいブランチで作業する**
4. **`Ctrl+C` で いつでも停止できる（2回で終了）**
5. **`--debug` で全てのAPIコール・ツール実行をトレース可能**

```bash
python3 co-vibe.py          # 通常モード（推奨）：毎回確認あり
python3 co-vibe.py -y       # 自動許可モード（上級者向け・自己責任）
```

### English

> **⚠️ Pay attention to the commands the AI executes. Use at your own risk.**

co-vibe is an AI agent that can **read/write files, execute commands, and make web requests**.

#### Watch for these keywords

| Keyword | Risk |
|---|---|
| Commands starting with `sudo` | Runs with admin privileges |
| `rm -rf` | Irreversible file/directory deletion |
| `chmod` / `chown` | Changes file permissions |
| `dd` / `mkfs` / `/dev/` | Directly modifies disks |
| `--force` / `--no-verify` | Skips safety checks |
| Long commands you don't understand | If you can't read it, don't allow it |

#### Rules for safe usage

1. **Start in normal mode (no `-y` flag)** — approve each action
2. **Reject commands you don't understand**
3. **Work in a git branch when modifying important files**
4. **`Ctrl+C` to stop at any time (press twice to exit)**
5. **Use `--debug` to trace every API call and tool execution**

```bash
python3 co-vibe.py          # Normal mode (recommended)
python3 co-vibe.py -y       # Auto-approve (advanced, at your own risk)
```

### 中文

> **⚠️ 请注意AI执行的命令。使用本工具风险自负。**

co-vibe 是一个AI代理，可以 **读写文件、执行命令、发起网络请求**。

| 需注意的关键词 | 风险 |
|---|---|
| 以 `sudo` 开头 | 以管理员权限运行 |
| `rm -rf` | 不可逆的文件删除 |
| `chmod` / `chown` | 更改文件权限 |
| `--force` | 跳过安全检查 |
| 看不懂的长命令 | 看不懂 = 不能允许 |

```bash
python3 co-vibe.py          # 普通模式（推荐）
python3 co-vibe.py -y       # 自动批准（仅限高级用户）
```

---

## ⚙️ Configuration

All settings via `.env` file or environment variables. See `.env.example` for full list.

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | (required) |
| `OPENAI_API_KEY` | OpenAI API key | (optional) |
| `GROQ_API_KEY` | Groq API key | (optional) |
| `CO_VIBE_STRATEGY` | Routing strategy | `auto` |
| `CO_VIBE_MODEL` | Force specific model | (auto) |
| `CO_VIBE_DEBUG` | Debug output | `0` |

---

## 🧪 Tests

```bash
# Run all 840 tests
python3 -m pytest tests/ -v

# Run specific test
python3 -m pytest tests/test_config.py -v

# With output
python3 -m pytest tests/ -v -s
```

---

## 📁 Project Structure

```
co-vibe/
  co-vibe.py           # Main agent — 11K lines, single file, pure Python
  co-vibe.sh           # Shell launcher (loads .env, runs co-vibe.py)
  co-vibe-proxy.py     # OpenAI-compatible proxy server
  setup.py             # Interactive setup wizard (vaporwave TUI)
  install.sh           # System-wide installer
  .env.example         # Configuration template
  tests/               # 840 tests (config, client, tools, session, UI, integration)
  POSITION-PAPER.md    # Research position paper
  VISION-ROADMAP.md    # Vision & development roadmap
  LICENSE              # MIT
```

---

## 📜 Disclaimer / 免責事項 / 免责声明

### 日本語

> **本プロジェクトは Anthropic・OpenAI・Groq 各社とは一切関係ありません。**
> 各社が提供・推奨・保証するものではありません。
> 各社名・モデル名は各社の商標です。本プロジェクトは非公式のコミュニティツールです。
>
> 本ソフトウェアは現状有姿（AS IS）で提供され、明示的・暗示的を問わず、いかなる保証もありません。
> 使用によって生じたいかなる損害についても、著者は一切責任を負いません。
> **すべて自己責任でご利用ください。**

### English

> **This project is NOT affiliated with Anthropic, OpenAI, or Groq.**
> Not endorsed or guaranteed by any provider. All trademarks belong to their respective owners.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
> The authors are not liable for any damages arising from the use of this software.
> **Use entirely at your own risk.**

### 中文

> **本项目与 Anthropic、OpenAI、Groq 无任何关联。**
> 非各公司提供、推荐或担保。各商标归其各自所有者所有。
>
> 本软件按"原样"提供，不提供任何保证。
> 作者不对因使用本软件而产生的任何损害承担责任。
> **使用本工具风险完全自负。**

---

## 📄 License

MIT License. Copyright (c) 2026 Yoichi Ochiai.
