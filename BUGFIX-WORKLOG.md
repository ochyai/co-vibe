# co-vibe.py バグ修正ワークログ

**日時**: 2026-02-24
**対象ファイル**: `/Users/yoichiochiai/co-vibe/co-vibe.py` (8198行)
**発端**: 実行中にターミナルがクラッシュ。速度測定ツールの結果が不正確。
**最終ステータス**: **全24タスク完了** (2026-02-24)
- フェーズ1: バグ修正 11/11 + サーベイ 3/3 = 14件完了
- フェーズ2: 新ツール 4件 + テスト 3件 + マルチエージェント 3件 + Quick Wins = 10件完了
- テスト合計: 371テスト (test_core 108 + test_tools_unit 149 + test_integration 31 + test_ui 83)
- co-vibe.py: 8198行 → 9577+行
- チーム: 15+エージェント (memory-keeper 含む)

---

## 発見されたバグ一覧

### [BUG-1] CRITICAL: Glob ツールの `**` パターンがシンボリックリンクを追跡 → OOM クラッシュ
- **行**: 3080-3108
- **原因**: `pathlib.Path.glob("**/pattern")` は Python < 3.13 でシンボリックリンクをたどる
- **影響**: ホームディレクトリで `**/co-vibe*` を実行 → シンボリックリンク経由で巨大ディレクトリツリーを走査 → メモリ枯渇 → OOM kill
- **証拠**: ターミナルログの最後の操作が `Glob → **/co-vibe* in /Users/yoichiochiai` で直後にクラッシュ
- **非`**`ブランチ（行3113）** は `os.walk(followlinks=False)` を正しく使用
- **修正方針**: `pathlib.glob` を `os.walk(followlinks=False)` + 手動パターンマッチに置換。イテレーション上限（100,000ファイル）を追加。

### [BUG-2] CRITICAL: Bash ツールの stdout/stderr 混合 → ツール出力が壊れる
- **行**: 2489-2502
- **原因**: stdout（バイナリデータ含む）の後に stderr を結合。30KB制限でトランケート時に stderr の有用データが切り捨てられる
- **影響**: `curl -o /dev/null -w "%{speed_download}"` の速度情報が見えなくなる
- **修正方針**: stderr を stdout の前に配置。または分離して返す。`curl -o` パターンでは stdout をスキップ。

### [BUG-3] HIGH: オーケストレータの fast tier 誤判定
- **行**: 6825-6842
- **原因**: `^(?:what|where|how|why|when|which|who|...)` で始まる入力を全て "fast" に分類
- **影響**: 「システムの回線速度調べてください」→ haiku に振られる。複雑な質問でも fast に落ちる
- **修正方針**: fast パターンを保守的に。複雑さインジケータ（動詞の数、文字数、技術用語）があれば balanced に昇格。

### [BUG-4] HIGH: レートリミット時の無限リトライループ
- **行**: 2089-2137
- **原因**: `while True` + `tried_providers.discard(provider)` → 同じプロバイダを永遠にリトライ
- **修正方針**: 最大リトライ回数（例: 5回）を追加。超過時はエラーを返す。

### [BUG-5] MEDIUM: ターミナル状態がクラッシュ時に復元されない
- **行**: 84-98, 598-607
- **原因**: `atexit` は OOM kill / SIGKILL で呼ばれない。`tty.setcbreak` が復元されない。
- **修正方針**: SIGTERM/SIGSEGV ハンドラを追加。復元コマンドを try-finally でラップ。

### [BUG-6] MEDIUM: SSE バッファが実質無制限に成長
- **行**: 2026-2046
- **原因**: `MAX_BUF` チェックは `\n` が無い場合のみ有効。SSE は常に `\n` を含むので発動しない。
- **修正方針**: 行単位で処理後に buf をクリアする安全策を追加。

### [BUG-7] MEDIUM: Config と Client の二重 tier マッピング
- **行**: Config 934-941 vs Client 1316-1328
- **原因**: Config が "strong" → "gpt-4o" に解決した後、Client 側で "gpt-4o" は "balanced" 扱い
- **修正方針**: tier 名を直接渡す。または Client 側で Config の tier マッピングを参照する。

### [BUG-8] LOW: 並列ツール実行のスレッドセーフティ
- **行**: 7152-7194
- **原因**: `_parallel_durations` dict がロックなしで複数スレッドから書き込み
- **修正方針**: `threading.Lock` を追加。

### [BUG-9] LOW: `_enforce_max_messages` で不正なメッセージシーケンス
- **行**: 5398-5419
- **原因**: tool_calls 付き assistant メッセージが対応する tool 結果なしで残る可能性
- **修正方針**: `compact_if_needed` と同じ孤立チェックを追加。

### [BUG-10] LOW: ターミナル復帰時のゴミ表示
- **行**: 93
- **原因**: `\033[1;999r` でスクロールリージョンをリセットするが、ステータスバーのテキストはクリアされない
- **修正方針**: `\033[2J` (画面クリア) を追加。

---

## 修正優先順位

1. **BUG-1** (Glob OOM) — クラッシュの直接原因
2. **BUG-2** (Bash stdout/stderr) — ツール精度に直結
3. **BUG-3** (Orchestrator tier) — タスク品質に影響
4. **BUG-4** (Rate limit loop) — ハングの原因
5. **BUG-5** (Terminal restore) — UX に影響
6. **BUG-6** (SSE buffer) — メモリ安全性
7. **BUG-7〜10** — 低優先度

---

## 修正状況

| Bug | 担当 | 状態 | 完了日 |
|-----|------|------|--------|
| BUG-1 | fixer-glob | 完了 | 2026-02-24 |
| BUG-2 | fixer-bash | 完了 | 2026-02-24 |
| BUG-3 | fixer-orchestrator | 完了 | 2026-02-24 |
| BUG-4 | fixer-ratelimit | 完了 | 2026-02-24 |
| BUG-5 | fixer-terminal | 完了 | 2026-02-24 |
| BUG-6 | fixer-terminal | 完了 | 2026-02-24 |
| BUG-7 | fixer-misc | 完了 | 2026-02-24 |
| BUG-8 | fixer-misc | 完了 | 2026-02-24 |
| BUG-9 | fixer-misc | 完了 | 2026-02-24 |
| BUG-10 | fixer-terminal | 完了 (BUG-5に含む) | 2026-02-24 |
| BUG-11 | fixer-markdown | 完了 | 2026-02-24 |

---

## 修正詳細ログ

### BUG-2 完了 (fixer-bash, 2026-02-24)
**変更箇所**:
1. **行 2410** (`_run_bg` バックグラウンドタスク): `out = (stderr or "") + ("\n" + stdout if stdout else "")` — stderr を先に結合
2. **行 2489-2502** (メイン `execute`): stderr を先に結合し、stdout を後に追加。コメント追加で意図を明確化

**検証**: コード確認済み。両箇所で stderr が先頭に配置され、30KB トランケーション時に stderr が保持される。

### BUG-3 完了 (fixer-orchestrator, 2026-02-24)
**変更箇所**: 行 6835-6897
1. **複雑さインジケータ追加** (行 6842-6868): アクション動詞・技術用語・ファイルパス・複数動詞を検出する `is_complex_signal` フラグ
2. **fast 判定フロー改善** (行 6889-6893): fast パターンマッチ後、`is_complex_signal` or 50文字以上なら balanced に昇格
3. **短文閾値を 30→15 文字に変更** (行 6895-6897): かつ `not is_complex_signal` 条件追加
4. **`修正して$` を fast パターンから除去**: アクション指示は `_action_or_tech` で balanced に誘導

**検証**: コード確認済み。テストケース（"fix the memory leak"→balanced, "what is python?"→fast 等）がロジック上正しく動作する。

### BUG-1 完了 (fixer-glob, 2026-02-24)
**変更箇所**: 行 3080-3142 (GlobTool.execute)
1. **`pathlib.glob` を `os.walk(followlinks=False)` に置換** (行 3107): シンボリックリンク追跡を防止
2. **`MAX_SCAN = 100,000` イテレーション上限追加** (行 3099, 3120-3121, 3139-3140): 巨大ディレクトリ走査を制限
3. **`seen_dirs` による symlink ループ検出** (行 3101, 3109-3116): realpath で重複ディレクトリをスキップ
4. **bounded heap (`MAX_RESULTS = 200`)** (行 3081, 3094, 3135-3138): 結果セットのメモリ制限
5. **Python < 3.12 フォールバック** (行 3105, 3127-3128): `PurePath.match` が `**` 非対応の場合、fnmatch で leaf パターンを照合

**検証**: コード確認済み。OOM の根本原因（pathlib.glob の symlink 追跡）が除去され、3重の安全策（followlinks=False, seen_dirs, MAX_SCAN）が機能する。

### BUG-5 完了 (fixer-terminal, 2026-02-24)
**変更箇所**:
1. **行 100-108** (新規 `_signal_cleanup_handler`): SIGTERM/SIGHUP でスクロールリージョンを復元後、デフォルトハンドラで再送信。OOM kill 以外のシグナル終了時にターミナル状態が復元される。
2. **行 653-659** (InputMonitor._poll の finally ブロック): termios 設定を確実に復元。スレッドが異常終了してもターミナルが壊れない。
3. **行 93**: `\033[2J\033[H` 追加（画面クリア+ホーム）— BUG-10 のゴミ表示も同時修正。

**検証**: コード確認済み。atexit + SIGTERM/SIGHUP + finally の3重保護でターミナル復元が確実になった。

### BUG-6 完了 (fixer-terminal, 2026-02-24)
**変更箇所**: 行 2062-2068 (`_iter_openai_sse`)
1. **MAX_BUF チェックを `\n` split ループの前に移動**: `if len(buf) > MAX_BUF: buf = b""; continue` — 改行の有無に関係なく発動する。以前は `\n` を含む SSE データでは MAX_BUF チェックが到達不能だった。

**検証**: コード確認済み。`while b"\n" in buf` ループの前にバッファサイズチェックがあり、SSE ストリーム中でもバッファが 2MB を超えない。

### BUG-4 完了 (fixer-ratelimit, 2026-02-24)
**変更箇所**: 行 2148-2269 (chat メソッドのリトライロジック全体)
1. **`while True` → `while retry_count < MAX_RETRIES`** (行 2175): `MAX_RETRIES = 5` (行 2156) で無限ループを防止
2. **`retry_count += 1`** (行 2188): RateLimitError 発生毎にカウント増加
3. **MAX_RETRIES 超過時に RuntimeError** (行 2265-2269): ループ外で明確なエラーメッセージを raise
4. **Cross-tier fallback 追加** (行 2210-2221): same-tier 全滅時に lower tier (strong→balanced→fast) にフォールバック
5. **Provider health tracking** (行 2184-2189): 成功時 healthy マーク、失敗時 unhealthy マーク
6. **Exponential backoff with jitter** (行 2224-2226): `min(wait_time * 2^(retry-1), 60s)` + 30% jitter

**検証**: コード確認済み。以前の `while True` + `tried_providers.discard()` による無限ループが除去され、最大5回でリトライ終了する。cross-tier fallback も正しく機能する。

### BUG-7 完了 (fixer-misc, 2026-02-24)
**変更箇所**: 行 6998-7001 (`_classify_complexity` 戻り値)
1. **tier hint 文字列を返すよう変更**: `"tier:strong"`, `"tier:balanced"`, `"tier:fast"` を返し、Client 側で `tier:` プレフィックスから直接 tier を解決 (行 2163-2164)
2. Config が model 名に解決してから Client が再度 tier を推定する二重マッピング問題を解消

**検証**: コード確認済み。`_classify_complexity` → `"tier:..."` → Client の `_hint.startswith("tier:")` で一貫した tier 解決。

### BUG-8 完了 (fixer-misc, 2026-02-24)
**変更箇所**: 行 7423-7435 (並列ツール実行)
1. **`_pdur_lock = threading.Lock()`** (行 7424): `_parallel_durations` dict への書き込みをロックで保護
2. **`with _pdur_lock:`** (行 7430, 7434): 成功時・例外時の両方でロック取得後に書き込み

**検証**: コード確認済み。全ての `_parallel_durations` 書き込みが `_pdur_lock` で保護されている。

### BUG-9 完了 (fixer-misc, 2026-02-24)
**変更箇所**: 行 5550-5554 (`_enforce_max_messages`)
1. **孤立 tool_calls チェック追加** (行 5550-5554): トリム後の先頭メッセージが `role=assistant` + `tool_calls` 付きで、次が `role=tool` でない場合、その assistant メッセージを除去
2. これにより `compact_if_needed` と同等の孤立チェックが `_enforce_max_messages` にも適用

**検証**: コード確認済み。トリム後に tool_calls 付き assistant が対応する tool 結果なしで残ることがなくなった。

---

## サーベイ・分析タスク

### 改善点洗い出し 完了 (improvement-scout, 2026-02-24)
**成果物**: `/Users/yoichiochiai/co-vibe/IMPROVEMENTS.md`
**概要**: 既知バグ (BUG-1〜11) 以外の改善点を30項目洗い出し。
- UX改善: 7件 (IMP-U1〜U7)
- パフォーマンス: 5件 (IMP-P1〜P5)
- 堅牢性: 7件
- コード品質: 8件
- 新機能: 7件
- セキュリティ: 5件

Quick Wins: ReadTool残行数カウント廃止、APIキーリダクション、プロバイダリトライ上限、protected_path重複修正、MultiProviderClient自己代入削除、/resumeコマンド追加

### ツール拡充サーベイ 完了 (survey-tools, 2026-02-24)
**成果物**: `/Users/yoichiochiai/co-vibe/TOOL-SURVEY.md`
**概要**: Claude Code のツール一覧と co-vibe の差分分析。17ツール実装済み、Claude Code コア17種の88%をカバー。
- **HIGH優先の不足ツール**: ScreenshotTool (50行), ClipboardTool (30行), ProcessManagerTool (60行), BrowserTool (MCP連携)
- **MEDIUM優先**: DatabaseTool, DockerTool, SSHTool, GUIAutomationTool 等
- **主要インサイト**: 約230行の追加でほぼ全不足機能カバー可能。MCP連携による拡張が最もコスト効率良い。

### マルチエージェント設計サーベイ 完了 (survey-multiagent, 2026-02-24)
**成果物**: `/Users/yoichiochiai/co-vibe/MULTIAGENT-SURVEY.md`
**概要**: co-vibe のマルチエージェント機能の現状分析と設計提案。
- 現状: SubAgent, ParallelAgents, MultiAgentCoordinator, auto-parallel detection
- 不足点: inter-agent communication, shared memory/blackboard, task dependency graph, dynamic re-planning, agent specialization
- 設計提案あり（詳細はレポート参照）

---

## 追加バグ修正

### BUG-11 完了 (fixer-markdown + fixer-bash, 2026-02-24)
**問題**: マークダウンが生テキストで表示される
**変更箇所**:
1. **`_render_markdown` メソッド強化** (行 ~6403-6470): イタリック、リンク、水平線(`---`,`***`,`___`)、テーブル、箇条書き/番号付きリスト、ブロッククォート(`>`)、`####`ヘッダー対応を追加
2. **ストリーミング出力のマークダウンレンダリング** (行 ~6238-6264): `_stream_md_print()` + `_flush_md_buf()` による行バッファリング方式。チャンク受信→改行区切り→完全行をMDレンダリング
3. **リファクタリング**: `_apply_inline_md()` (インライン書式), `_render_md_line()` (1行レンダリング+ステート管理), `_render_markdown()` (ラッパー) の3層構造

**検証**: _render_markdown メソッドが存在し、assistant 出力時に呼び出されている (行 6416, 7188)。ストリーミング時も行バッファリングで正しくレンダリングされる。

---

## フェーズ2: 新機能実装・テスト

### #25 WebFetch POST拡張 + ClipboardTool 完了 (impl-webfetch-clipboard, 2026-02-24)
**変更箇所**:
1. **WebFetchTool POST拡張** (行 3501-3516): `method` (GET/POST/PUT/DELETE/PATCH, enum), `headers` (object), `body` (string) パラメータ追加。既存GETは完全互換。
2. **ClipboardTool 新規作成** (行 3912-): read/write action, macOS(pbpaste/pbcopy)/Linux(xclip/xsel)/Windows(PowerShell) 分岐, timeout=5s

**検証**: WebFetchTool に method/headers/body パラメータ確認 (行 3501-3516)。ClipboardTool クラス存在確認 (行 3912)。enum バリデーション付き。

### #24 ツール実行ユニットテスト 完了 (test-tools, 2026-02-24)
**成果物**: `/Users/yoichiochiai/co-vibe/tests/test_tools_unit.py`
**概要**: 149 ユニットテスト、全パス
- BashTool (execution, timeout, security, background, env sanitization)
- ReadTool (file read, offset/limit, binary, image, notebook, symlink)
- WriteTool (atomic write, protected paths, symlink rejection, size limit)
- EditTool (replacement, Unicode NFC, binary rejection, replace_all, protected paths)
- GlobTool (pattern matching, SKIP_DIRS, MAX_RESULTS, symlink loops)
- GrepTool (regex, binary skip, ReDoS defense, context lines, glob filter, head_limit)

### #32 ヘッドレス統合テスト + UIテスト 完了 (test-integration, 2026-02-24)
**成果物**:
- `/Users/yoichiochiai/co-vibe/tests/test_integration.py` (31テスト): API キーなし終了、ワンショットモード、セッション管理、Config デフォルト、シグナルハンドリング、ToolRegistry、PermissionMgr 等
- `/Users/yoichiochiai/co-vibe/tests/test_ui.py` (83テスト): バナー、ヘルプ、ステータス、ToolCall/Result 表示、マークダウンレンダリング、ScrollRegion、Spinner、CJK検出 等
**合計**: 114テスト、全パス

### #26 ScreenshotTool + ProcessManagerTool 完了 (impl-screenshot-process, 2026-02-24)
**変更箇所**:
1. **ScreenshotTool** (行 5581-): macOS(screencapture)/Linux(import)/Windows(PowerShell) 3プラットフォーム対応。region(x,y,w,h) 部分キャプチャ、window パラメータ対応。base64 PNG JSON 返却。PermissionMgr.SAFE_TOOLS 登録。
2. **ProcessManagerTool** (行 5732-): 4アクション (list_processes, kill_process, check_port, list_ports)。PID 1/自己/親プロセスの kill 拒否。lsof でポート使用プロセス特定。PermissionMgr.ASK_TOOLS 登録。

**検証**: 両クラスの存在を確認済み (行 5581, 5732)。

### #27 DatabaseTool (SQLite) 完了 (impl-database, 2026-02-24)
**変更箇所**: `class DatabaseTool(Tool)` (行 5592-, 約150行)
- 3アクション: query (パラメータ化SQL), schema (CREATE TABLE一覧), tables (テーブル名一覧)
- セキュリティ: realpath 解決, readonly モード (SELECT/PRAGMA/EXPLAIN のみ), MAX_ROWS=1000, timeout=10s
- PermissionMgr.ASK_TOOLS に "Database" 追加

**検証**: クラス存在確認 (行 5592)。action enum, db_path, sql, params, readonly パラメータ確認済み。

### #23 テスト基盤構築 完了 (test-core, 2026-02-24)
**成果物**: `/Users/yoichiochiai/co-vibe/tests/test_core.py` (108テスト、全パス)
**カバレッジ**:
- _try_parse_json_value (10), _extract_tool_calls_from_text (23), _estimate_tokens (11, CJK対応)
- _enforce_max_messages (4, BUG-9含む), compact_if_needed (7, 無限再圧縮防止)
- Provider health tracking (6), _get_cross_tier_fallbacks (4)
- MultiProviderClient.chat fallback (4, MAX_RETRIES), _classify_complexity (27, 日英)
- _get_fallback_models tier-aware (2), _select_model tier: prefix (4)
全テストはモック使用 (外部API呼び出しなし)。

### #28 AgentBlackboard + ROLE_CONFIGS 完了 (impl-blackboard, 2026-02-24)
**変更箇所** (~150行追加):
1. **AgentBlackboard** (行 5147-): スレッドセーフ共有メモリ。write/read/read_all/append_finding/get_findings(since)/clear。threading.Lock 使用。
2. **ROLE_CONFIGS** (行 4340-): 5ロール — researcher (Read/Glob/Grep/WebFetch/WebSearch, fast), coder (Read/Glob/Grep/Bash/Write/Edit, balanced), reviewer (Read/Glob/Grep, strong), tester (balanced), general (legacy全ツール)
3. **SubAgentTool.execute** (行 4429-): role パラメータ追加、_resolve_model_for_tier() ヘルパー、blackboard コンテキスト注入
4. **MultiAgentCoordinator.run_parallel** (行 5218-): 共有 AgentBlackboard 生成、各サブエージェントに注入
5. **ParallelAgentTool.parameters**: task に role enum 追加

**検証**: ROLE_CONFIGS (行 4340)、AgentBlackboard (行 5147) 存在確認済み。後方互換 (role 未指定 = "general")。

### #31 Quick Wins一括修正 完了 (impl-quickwins, 2026-02-24)
**修正5件**:
1. **IMP-P1** (行 2796): ReadTool `sum(1 for _ in f)` → `bool(next(f, None))` — O(n) 全行スキャンを O(1) ピークに
2. **IMP-S1** (行 1780-1781): `_http_request()` エラーメッセージから API キープレフィックス (sk-, key-, sess-) を re.sub で redact
3. **IMP-C3** (行 2903): `_is_protected_path()` の重複タプル `("co-vibe", "co-vibe")` → `("co-vibe",)` に修正
4. **IMP-C4**: `MultiProviderClient = MultiProviderClient` ノーオプ行を削除
5. **IMP-C6** (行 176-180): `Limits` クラス追加。マジックナンバー 30000/10000/50000 を `Limits.MAX_OUTPUT` / `Limits.MAX_SUBAGENT_OUTPUT` / `Limits.MAX_WEB_CONTENT` に置換 (4箇所)

**検証**: IMP-C4 削除確認済み (grep ヒットなし)。

### #30 ExecutionMemory + WorkQueue 完了 (impl-memory-queue, 2026-02-24)
**変更箇所** (~161行追加 + ~25行統合):
1. **ExecutionMemory** (行 5199-, 94行): JSON永続化 (.co-vibe-memory.json), MAX_ENTRIES=500, record() でタスク実行記録、recommend_tier() で過去20件から最適tier推薦 (成功率→速度でタイブレーク)、get_stats()、threading.Lock
2. **WorkQueue** (行 5293-, 67行): submit()/run_all()、ThreadPoolExecutor + work-stealing (共有dequeから取得)、max_workers=6、スレッドセーフ
3. **Agent.__init__** (行 8066): ExecutionMemory 初期化
4. **Agent._select_tier_model** (行 8100-8106): ヒューリスティック後に execution_memory.recommend_tier() でオーバーライド
5. **Agent.run end** (行 8700-8715): 全実行を ExecutionMemory に記録 (tier, tools, duration, success)
6. **MultiAgentCoordinator.run_parallel** (行 5464-5468): threading.Thread → WorkQueue (work-stealing) に置換

**検証**: 両クラスの存在確認済み (行 5199, 5293)。ファイル合計 9577行。

### #29 DAGWorkflow + SmartTaskDecomposer 完了 (impl-dag, 2026-02-24)
**変更箇所** (~200行追加):
1. **DAGWorkflow** (行 8035-8127): DAG実行エンジン。add_node(), add_edge(), has_cycle() (Kahn's algorithm), get_ready_nodes(), execute(coordinator)。依存解決後に並列バッチ実行。
2. **SmartTaskDecomposer** (行 8137-8253): DECOMPOSE_SCHEMA (id/role/prompt/depends_on/estimated_complexity)。should_decompose() ヒューリスティック (50文字以上 + 2アクション動詞以上)。decompose() で sidecar モデルに構造化 JSON タスクグラフ生成を依頼。
3. **Agent._execute_dag_plan** (行 8488-8553): プランから DAG 構築、エッジ追加、サイクルフォールバック、coordinator 経由実行、結果統合。
4. **Agent.run 統合** (行 8575-8582): 既存 Tier 1 regex 検出後に Tier 2 として should_decompose() → decompose() → _execute_dag_plan() を呼び出し。

**検証**: DAGWorkflow (行 8035) と SmartTaskDecomposer (行 8137) の存在確認済み。

---

## 全タスク完了 (2026-02-24)

**フェーズ1 (バグ修正 + サーベイ)**: 11バグ修正 + 3サーベイ = 全14件完了
**フェーズ2 (新機能 + テスト)**: 10タスク = 全10件完了
**合計**: 24タスク完了、co-vibe.py は 8198行 → 9577行+ に拡大
