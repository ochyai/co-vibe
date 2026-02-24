# co-vibe ツール拡充サーベイ

> 調査日: 2026-02-24
> 対象: `/Users/yoichiochiai/co-vibe/co-vibe.py`

---

## 1. co-vibe 現在のツール一覧

### 1.1 コアツール (LLM function calling で使用)

| # | ツール名 | クラス | 行番号 | 概要 |
|---|----------|--------|--------|------|
| 1 | **Bash** | `BashTool` | L2266 | コマンド実行。タイムアウト、バックグラウンド実行、セキュリティチェック付き |
| 2 | **Read** | `ReadTool` | L2547 | ファイル読み取り（行番号付き、画像base64、PDF、Jupyter対応）|
| 3 | **Write** | `WriteTool` | L2811 | ファイル書き込み（アトミック書き込み、undo対応、10MB制限）|
| 4 | **Edit** | `EditTool` | L2902 | 文字列置換によるファイル編集（Unicode NFC正規化、diff表示）|
| 5 | **Glob** | `GlobTool` | L3063 | ファイルパターンマッチング（os.walk + fnmatch、mtime順）|
| 6 | **Grep** | `GrepTool` | L3190 | コンテンツ検索（正規表現、コンテキスト行、ReDoS防御）|
| 7 | **WebFetch** | `WebFetchTool` | L3387 | URL取得（SSRF防御、HTML→テキスト変換）|
| 8 | **WebSearch** | `WebSearchTool` | L3522 | DuckDuckGo検索（レート制限、CJKロケール対応）|
| 9 | **NotebookEdit** | `NotebookEditTool` | L3656 | Jupyter ノートブック編集（replace/insert/delete）|
| 10 | **TaskCreate** | `TaskCreateTool` | L3799 | タスク作成 |
| 11 | **TaskList** | `TaskListTool` | L3851 | タスク一覧 |
| 12 | **TaskGet** | `TaskGetTool` | L3874 | タスク詳細取得 |
| 13 | **TaskUpdate** | `TaskUpdateTool` | L3910 | タスク更新（依存関係、サイクル検出付き）|
| 14 | **AskUserQuestion** | `AskUserQuestionTool` | L4021 | ユーザーへの質問（選択肢対応）|
| 15 | **SubAgent** | `SubAgentTool` | L4088 | サブエージェント起動（独立会話コンテキスト、権限制御）|
| 16 | **MCP Tools** | `MCPTool` | L4449 | 外部MCPサーバーのツールラッパー |
| 17 | **ParallelAgents** | `ParallelAgentTool` | L4953 | 並列サブエージェント（2-6並列、進捗バー）|

### 1.2 補助システム (ツールではないが統合機能)

| # | 機能名 | クラス | 行番号 | 概要 |
|---|--------|--------|--------|------|
| A | **GitCheckpoint** | `GitCheckpoint` | L4547 | git stash ベースのチェックポイント & ロールバック |
| B | **AutoTestRunner** | `AutoTestRunner` | L4623 | 編集後の自動テスト/リント実行 |
| C | **FileWatcher** | `FileWatcher` | L4701 | ファイル変更のポーリング監視 |
| D | **MultiAgentCoordinator** | `MultiAgentCoordinator` | L4828 | 並列エージェント調整 |
| E | **Skills** | `_load_skills()` | L4510 | SKILL.md ファイルの読み込み |
| F | **Undo** | `_undo_stack` | L3796 | Write/Edit の取り消し(最大20件) |

---

## 2. Claude Code との比較

### 2.1 Claude Code が持つツール

| ツール | co-vibe に存在？ | 差異 |
|--------|-----------------|------|
| Read | YES | ほぼ同等。画像・PDF・Jupyter対応済み。ページ指定(pages param)はco-vibeの方がシンプル実装 |
| Write | YES | ほぼ同等。アトミック書き込み対応済み |
| Edit | YES | ほぼ同等。Unicode NFC正規化はco-vibeの方が優れている |
| Glob | YES | ほぼ同等。ripgrep 未使用(stdlib のみ)だが実用上問題なし |
| Grep | YES | ほぼ同等。ripgrep 未使用だが Python re で十分なパフォーマンス |
| Bash | YES | ほぼ同等。バックグラウンド実行、セキュリティチェック対応済み |
| WebFetch | YES | Claude Code は AI処理付きだが co-vibe は生テキスト返却。差は小さい |
| WebSearch | YES | Claude Code は独自 API、co-vibe は DuckDuckGo。実用上同等 |
| NotebookEdit | YES | 同等 |
| Task/TodoWrite | YES | co-vibe は TaskCreate/List/Get/Update の4ツール。Claude Code の TodoWrite と同等 |
| AskUserQuestion | YES | 同等 |
| SubAgent/Task(agent) | YES | SubAgent + ParallelAgents で同等以上 |
| MCP連携 | YES | stdio JSON-RPC 2.0 で実装済み |
| **EnterPlanMode** | **NO** | 計画モード(実行前に計画を立てるモード) |
| **EnterWorktree** | **NO** | git worktree による分離作業環境 |
| **SendMessage** | **NO** | マルチエージェント間通信 |
| **Skill** | **PARTIAL** | Skills読み込みはあるが、ツールとしての起動は未実装 |

### 2.2 差分サマリ

Claude Code との主要な差分:
1. **EnterPlanMode** — 計画/実行の切り替え (LOW: Bash で代替可能)
2. **EnterWorktree** — git worktree 管理 (LOW: Bash で代替可能)
3. **SendMessage** — エージェント間通信 (MEDIUM: マルチエージェント強化に必要)
4. **Skill ツール化** — スキルをツールとして呼び出す (LOW: 既に部分的に対応)

**結論: Claude Code のツールセットとの差は小さい。co-vibe は既にほぼ全てのコアツールを実装済み。**

---

## 3. 不足ツール一覧（「なんでもできる」ために必要なもの）

### [優先度 HIGH] ScreenshotTool — スクリーンショット取得

- **概要**: 画面全体またはウィンドウのスクリーンショットを取得し、マルチモーダルLLMで画像認識させる
- **Claude Code での実装**: Read ツールで画像ファイルを読むことはできるが、スクリーンショット取得自体のツールはない
- **co-vibe での実装方針**:
  - macOS: `screencapture -x /tmp/screenshot.png`
  - Linux: `import -window root /tmp/screenshot.png` (ImageMagick) or `gnome-screenshot`
  - Windows: PowerShell の `[System.Windows.Forms.Screen]`
  - 取得した画像を base64 エンコードして返却 → 次のターンでマルチモーダル分析可能
  - Bash で `screencapture` を呼ぶだけなので、専用ツール化のメリットは「LLMが自然に使える」こと
- **工数見積もり**: S (50行程度)

### [優先度 HIGH] BrowserTool — ブラウザ操作

- **概要**: Webページの操作（クリック、フォーム入力、JavaScript実行、スクリーンショット取得）
- **Claude Code での実装**: なし（WebFetchは静的取得のみ）
- **co-vibe での実装方針**:
  - Playwright (推奨) または Selenium を `subprocess` で起動
  - シングルファイル制約: Playwright の Python バインディングは pip install 必要
  - **代替案A**: `playwright` CLI をBashで呼ぶラッパー
  - **代替案B**: CDP (Chrome DevTools Protocol) を直接 WebSocket で叩く（stdlib の `websocket` は非標準だが `http.client` で WebSocket ハンドシェイクは可能）
  - **代替案C (推奨)**: Playwright MCP サーバーを co-vibe の MCP 連携で接続。これなら co-vibe.py 自体の変更ゼロ
  - アクション: `navigate(url)`, `click(selector)`, `type(selector, text)`, `screenshot()`, `evaluate(js)`, `get_text(selector)`
- **工数見積もり**: M (CDP直接) / S (MCP連携)

### [優先度 HIGH] ClipboardTool — クリップボード操作

- **概要**: クリップボードの読み書き。大きなテキストブロックの受け渡しやコピーペースト操作に使用
- **Claude Code での実装**: なし（Bash で `pbcopy`/`pbpaste` は可能）
- **co-vibe での実装方針**:
  - macOS: `subprocess.run(["pbpaste"])` / `subprocess.Popen(["pbcopy"]).communicate(input=text)`
  - Linux: `xclip` or `xsel`
  - Windows: `powershell Get-Clipboard` / `Set-Clipboard`
  - 画像クリップボードも対応可能（macOS: `osascript -e 'the clipboard as «class PNGf»'`）
- **工数見積もり**: S (30行程度)

### [優先度 HIGH] ProcessManagerTool — プロセス管理

- **概要**: 実行中プロセスの一覧、特定プロセスの停止、ポート使用の確認
- **Claude Code での実装**: なし（Bash で `ps`, `kill`, `lsof` は可能）
- **co-vibe での実装方針**:
  - `list_processes(filter)`: `psutil` なしでも `subprocess.run(["ps", "aux"])` で実装可
  - `kill_process(pid, signal)`: `os.kill(pid, signal)`
  - `check_port(port)`: `socket.socket().connect_ex(("localhost", port))`
  - **BashTool の拡張でも十分**だが、専用ツール化すると「デバッグ中にポートが空いてるか確認」等をLLMが自然にやれる
- **工数見積もり**: S (60行程度)

### [優先度 MEDIUM] DatabaseTool — データベース操作

- **概要**: SQLite/PostgreSQL/MySQL への接続、クエリ実行、スキーマ取得
- **Claude Code での実装**: なし（Bash でCLIクライアントは使える）
- **co-vibe での実装方針**:
  - SQLite: `sqlite3` (Python 標準ライブラリ) で完結
  - PostgreSQL/MySQL: `subprocess.run(["psql", ...])` or `subprocess.run(["mysql", ...])`
  - アクション: `query(sql, db_path)`, `schema(db_path)`, `tables(db_path)`
  - SQLインジェクション防御: パラメータ化クエリ推奨、SELECT only モードオプション
  - **SQLite なら完全にstdlibのみで実装可能**
- **工数見積もり**: S (SQLite only) / M (マルチDB)

### [優先度 MEDIUM] DockerTool — Docker/コンテナ管理

- **概要**: Dockerコンテナの起動/停止/ログ取得、イメージ管理
- **Claude Code での実装**: なし（Bash で `docker` コマンドは使える）
- **co-vibe での実装方針**:
  - Docker CLI のラッパー: `subprocess.run(["docker", ...])`
  - アクション: `ps()`, `run(image, cmd)`, `stop(container)`, `logs(container)`, `build(path)`, `exec(container, cmd)`
  - セキュリティ: `--privileged`, `--network=host` のブロック
  - **Bash で十分**だが、専用ツールにすると LLM が構造化された結果を受け取れる（JSON出力 `docker ps --format '{{json .}}'`）
- **工数見積もり**: S-M (80行程度)

### [優先度 MEDIUM] SSHTool — リモート接続

- **概要**: SSH経由でリモートサーバーにコマンド実行
- **Claude Code での実装**: なし（Bash で `ssh` は使えるが対話的セッションは不可）
- **co-vibe での実装方針**:
  - `subprocess.run(["ssh", "-o", "BatchMode=yes", host, command])`
  - 非対話モード限定（パスワード認証は不可、鍵認証のみ）
  - アクション: `exec(host, command)`, `copy_to(host, local_path, remote_path)`, `copy_from(host, remote_path, local_path)`
  - `scp`/`rsync` のラッパーも含む
  - セキュリティ: ホストキー検証必須、内部IP制限オプション
- **工数見積もり**: S (50行程度)

### [優先度 MEDIUM] EmailTool — メール送受信

- **概要**: メール送信（通知、レポート送付）
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - `smtplib` (Python 標準ライブラリ) で SMTP 送信
  - `imaplib` (Python 標準ライブラリ) で IMAP 受信
  - 設定: `.co-vibe/email.json` に SMTP/IMAP サーバー情報
  - アクション: `send(to, subject, body, attachments)`, `inbox(limit)`, `read(message_id)`
  - セキュリティ: 送信先ホワイトリスト、1日の送信上限
- **工数見積もり**: M (100行程度)

### [優先度 MEDIUM] GUIAutomationTool — GUI操作

- **概要**: マウス移動・クリック、キーボード入力、ウィンドウ操作
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - macOS: `osascript` (AppleScript) / `cliclick` (Homebrew)
  - Linux: `xdotool`
  - Windows: PowerShell `SendKeys` / `AutoHotkey`
  - **シングルファイル制約**: `pyautogui` は外部依存。代わりに各OS のCLIツールを `subprocess` で呼ぶ
  - アクション: `click(x, y)`, `type_text(text)`, `key_press(key)`, `move_mouse(x, y)`, `find_window(title)`
  - スクリーンショットと組み合わせて「画面を見て操作する」ループが可能
- **工数見積もり**: M (OS分岐が多い、100行程度)

### [優先度 MEDIUM] AudioTool — 音声入出力

- **概要**: テキスト読み上げ(TTS)、音声ファイル再生、音声録音
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - TTS: macOS `say` コマンド、Linux `espeak`、Windows `PowerShell SpeechSynthesizer`
  - 再生: macOS `afplay`、Linux `aplay`/`paplay`
  - 録音: macOS `rec` (SoX)、ffmpeg
  - Whisper API 連携で音声→テキスト変換も可能
- **工数見積もり**: S (TTS のみ) / M (録音+STT含む)

### [優先度 LOW] ImageGenerationTool — 画像生成

- **概要**: テキストから画像を生成（DALL-E、Stable Diffusion等のAPI呼び出し）
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - OpenAI DALL-E API: `urllib.request` で REST API 呼び出し
  - ローカル SD: `subprocess` で `comfyui` CLI / `stable-diffusion-webui` API
  - 結果画像を `/tmp` に保存 → Read ツールで確認
- **工数見積もり**: S (API呼び出しのみ)

### [優先度 LOW] CronSchedulerTool — スケジュール実行

- **概要**: 定期実行タスクの設定・管理
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - `crontab -l` / `crontab -e` のラッパー
  - または Python の `sched` モジュールでインプロセス実行
  - アクション: `add(schedule, command)`, `list()`, `remove(id)`
- **工数見積もり**: S (40行程度)

### [優先度 LOW] APIClientTool — 汎用REST API呼び出し

- **概要**: 任意のREST APIへのリクエスト（GET/POST/PUT/DELETE、ヘッダー、認証）
- **Claude Code での実装**: なし（WebFetch は GET のみ）
- **co-vibe での実装方針**:
  - `urllib.request.Request` に method, headers, body を指定
  - WebFetchTool を拡張して POST/PUT/DELETE 対応にする方がシンプル
  - JSON レスポンスの自動パース
  - 認証: Bearer token, Basic auth ヘッダー対応
- **工数見積もり**: S (WebFetch 拡張で30行追加)

### [優先度 LOW] EnvironmentTool — 環境変数管理

- **概要**: 環境変数の安全な読み書き（.env ファイル管理含む）
- **Claude Code での実装**: なし
- **co-vibe での実装方針**:
  - `get(key)`: `os.environ.get(key)` (ただしセンシティブキーはマスク)
  - `set(key, value)`: 現セッションのみ / `.env` ファイルに永続化
  - `list()`: 非センシティブ変数のみ一覧
- **工数見積もり**: S (40行程度)

### [優先度 LOW] ArchiveTool — アーカイブ操作

- **概要**: ZIP/tar.gz の作成・展開
- **Claude Code での実装**: なし（Bash で可能）
- **co-vibe での実装方針**:
  - `zipfile`, `tarfile` (Python 標準ライブラリ)
  - アクション: `create(output, paths, format)`, `extract(archive, dest)`, `list(archive)`
  - セキュリティ: zip bomb 防御 (展開後サイズ制限)、path traversal 防御
- **工数見積もり**: S (50行程度)

---

## 4. 優先度別実装ロードマップ

### Phase 1: すぐに実装すべき (HIGH) — 工数合計: S-M

| ツール | 工数 | 外部依存 | 理由 |
|--------|------|----------|------|
| ScreenshotTool | S | なし (OS標準) | マルチモーダルLLMとの相乗効果大。画面を「見て」操作可能に |
| ClipboardTool | S | なし (OS標準) | ユーザーとのデータ受け渡しが格段に楽に |
| ProcessManagerTool | S | なし (OS標準) | デバッグ・開発ワークフローの基盤 |
| BrowserTool (MCP) | S | Playwright MCP | 既存MCP連携で追加コード不要。設定例を文書化するだけ |

### Phase 2: 次に実装すべき (MEDIUM) — 工数合計: M-L

| ツール | 工数 | 外部依存 | 理由 |
|--------|------|----------|------|
| DatabaseTool (SQLite) | S | なし (stdlib) | データ分析・開発でよく使う |
| DockerTool | S-M | Docker CLI | コンテナ開発は現代の必須スキル |
| SSHTool | S | ssh CLI | リモート操作で活用範囲が大きく広がる |
| GUIAutomationTool | M | OS CLI tools | スクリーンショットとの組み合わせで「PC操作エージェント」が実現 |
| EmailTool | M | なし (stdlib) | 通知・レポートの自動化 |
| AudioTool | S-M | OS CLI tools | アクセシビリティ向上、音声インターフェース |

### Phase 3: あると便利 (LOW) — 工数合計: S

| ツール | 工数 | 外部依存 | 理由 |
|--------|------|----------|------|
| APIClientTool | S | なし | WebFetch 拡張で対応可能 |
| ArchiveTool | S | なし (stdlib) | Bash で代替可能だがLLMが使いやすい |
| ImageGenerationTool | S | API key | ニッチだが創造的タスクに有用 |
| CronSchedulerTool | S | なし | 自律エージェントの基盤 |
| EnvironmentTool | S | なし | セキュリティ向上 |

---

## 5. WebFetch の拡張提案 (APIClientTool の代替)

現在の WebFetch は GET のみ。以下の拡張で汎用API呼び出しが可能になる:

```python
# 追加パラメータ
"method": {"type": "string", "description": "HTTP method: GET, POST, PUT, DELETE, PATCH"},
"headers": {"type": "object", "description": "Custom request headers"},
"body": {"type": "string", "description": "Request body (for POST/PUT/PATCH)"},
"content_type": {"type": "string", "description": "Content-Type header shortcut"},
```

これにより APIClientTool を別途作る必要がなくなる。工数: S (30行追加)。

---

## 6. MCP 活用による「ゼロコード拡張」

co-vibe は既に MCP (Model Context Protocol) 連携を実装済み。以下のツールは **MCP サーバー経由で追加可能** であり、co-vibe.py の変更が不要:

| MCP サーバー | 提供機能 | 備考 |
|-------------|---------|------|
| [Playwright MCP](https://github.com/anthropics/mcp-playwright) | ブラウザ操作 | 最有力。navigate, click, screenshot, evaluate |
| [Filesystem MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | 高度なファイル操作 | co-vibe の既存ツールで十分 |
| [GitHub MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/github) | GitHub API | Issues, PRs, Reviews |
| [Slack MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/slack) | Slack 通信 | メッセージ送受信 |
| [Google Drive MCP](https://github.com/anthropics/mcp-google-drive) | Google Drive | ドキュメント読み書き |
| [PostgreSQL MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/postgres) | DB操作 | クエリ実行 |
| [Memory MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | 長期記憶 | セッション間の知識保持 |
| [Puppeteer MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer) | ブラウザ操作 | Playwright の代替 |

**推奨**: README に MCP サーバーの設定例(`~/.config/co-vibe/mcp.json`)を追加し、ユーザーが簡単に機能拡張できるようにする。

---

## 7. 総合評価

### co-vibe の現状

- **Claude Code のコアツール17種のうち15種をカバー** (88%)
- 不足は EnterPlanMode, EnterWorktree, SendMessage の3つだが、いずれも Bash で代替可能
- **MCP 連携が既にあるため、拡張性は高い**
- セキュリティ対策（SSRF防御、シンボリックリンク検出、危険コマンドブロック等）は Claude Code と同等以上

### 「なんでもできる」ために最も効果的な追加

1. **Screenshot + GUIAutomation** = 「画面を見て操作する」AIエージェント (Computer Use 相当)
2. **Browser (MCP)** = Web自動化（スクレイピング、フォーム入力、テスト）
3. **Database (SQLite)** = データ分析・管理の基盤
4. **WebFetch POST拡張** = 外部API連携（通知、デプロイ、CI/CD トリガー）
5. **Clipboard** = ユーザーとの自然なデータ交換

### 実装の優先順位(コスト対効果)

```
最高効率: WebFetch POST拡張 (30行で大きな機能追加)
         ClipboardTool (30行)
         ScreenshotTool (50行)
         DatabaseTool/SQLite (60行)
         ProcessManagerTool (60行)
         Browser = MCP設定のみ (0行)
```

合計: **約230行の追加** で、主要な不足機能をほぼカバー可能。
シングルファイル制約を維持しつつ、「なんでもできるAIエージェント」に大きく近づく。
