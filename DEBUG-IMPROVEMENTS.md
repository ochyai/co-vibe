# co-vibe.py Debug Log Improvement Report

Date: 2026-02-24
Analyzed by: Claude Code

## Applied Fixes (code already modified)

1. **[orchestrator] デバッグログ強化** -- `classified=`, `memory_override=`, 解決モデル名, 入力プレビューを表示
2. **ExecutionMemory 2段階降格ブロック** -- `strong` 分類時に `fast` への降格を禁止 (`balanced` まで)
3. **researcher ロールの tier を `balanced` に変更** -- `"fast"` -> `"balanced"` (deep research に haiku は不適切)
4. **`_done_count` にスレッドロック追加** -- `_done_lock = threading.Lock()` で 3箇所の `+=1` とハートビートの読み取りを保護
5. **サブエージェントのデバッグログ強化** -- tier名とモデル名を起動時メッセージに追加 (debug mode時)
6. **`_classify_complexity` に英語パターン追加** -- `deep research`, `deeply investigate`, `in-depth analysis`, `深く調査/調べ/研究/分析`
7. **prompt/completion 比率の異常警告** -- ratio > 100x のとき `WARNING: very low output` を表示 (Anthropic + OpenAI 両方)
8. **並列エージェントの retry jitter にインデックスオフセット追加** -- `+ (idx * 0.5)` でバースト回避

---

## Executive Summary

`co-vibe.py` のデバッグログから6つの改善点を特定した。
最も深刻なのは (1) ExecutionMemoryがtier分類をオーバーライドしてdeep researchがfastモデルに降格される問題と (2) Ctrl+C時にサブエージェントスレッドが停止しない問題。

---

## Issue 1: "deep research" が fast tier に分類される

**ログ**: `[orchestrator] tier=fast`
**根本原因**: `_classify_complexity()` (L8398) は `ディープリサーチ|survey.*paper` 等を `strong` に正しく分類するが、その後 `ExecutionMemory.recommend_tier()` (L8407) が過去の実行履歴に基づき tier をオーバーライドする可能性がある。

```python
# L8404: _classify_complexity は "strong" を返す
tier = self._classify_complexity(user_text)

# L8407-8412: ExecutionMemory が "fast" にオーバーライド
recommended = self.execution_memory.recommend_tier(tier)
if recommended and recommended != tier:
    tier = recommended  # strong -> fast に降格！
```

**問題点**:
1. `recommend_tier()` は task_type (=tier名) で過去データを検索するが、引数が `tier` (分類結果) なので、過去に "strong" タスクが fast で成功した記録があると fast を推薦してしまう
2. デバッグログ `[orchestrator] tier=fast` は最終結果のみ出力し、「なぜfastになったか」の理由を示さない

**修正案**:
```python
# (A) デバッグログを強化
classified_tier = self._classify_complexity(user_text)
tier = classified_tier
memory_override = None
if hasattr(self, 'execution_memory'):
    recommended = self.execution_memory.recommend_tier(tier)
    if recommended and recommended != tier:
        memory_override = recommended
        tier = recommended

if config.debug:
    _preview = user_text[:60].replace('\n', ' ') if user_text else "(empty)"
    _mem = f" memory_override={memory_override}" if memory_override else ""
    print(f"[orchestrator] tier={tier} (classified={classified_tier}{_mem}) "
          f"input=\"{_preview}\"", file=sys.stderr)

# (B) ExecutionMemory降格の制限: strong分類時はfastへの2段階降格を禁止
if classified_tier == "strong" and tier == "fast":
    tier = "balanced"  # 最低でもbalancedまで
```

**優先度**: HIGH

---

## Issue 2: researcher ロールの tier が "fast" 固定

**ログ**: `[debug] POST model=claude-haiku-4-5-20251001` (サブエージェント)
**根本原因**: `ROLE_CONFIGS["researcher"]["tier"]` が `"fast"` にハードコードされている (L4352)

```python
ROLE_CONFIGS = {
    "researcher": {
        ...
        "tier": "fast",  # <- deep research に haiku を使う
    },
```

**問題点**:
- "deep research" タスクのサブエージェントが researcher ロールで起動され、fast tier (haiku) が割り当てられる
- researcher ロールは読み取り専用ツールしか持たないので軽量にする設計意図は理解できるが、deep research 目的のときはモデル品質が重要

**修正案**:
```python
# Option A: researcher の tier を balanced に引き上げ
"researcher": {
    ...
    "tier": "balanced",
},

# Option B: 親の tier を継承する仕組みを追加
# SubAgentTool.execute() で parent_tier を引数に取り、
# role_tier が parent_tier より低い場合は parent_tier を使う
```

**優先度**: HIGH

---

## Issue 3: `_done_count` のスレッドセーフティ (race condition)

**ログ**: `0/4 agents done, 110s elapsed`
**根本原因**: `_done_count[0] += 1` (L5427) にロックがない

```python
_done_count = [0]  # L5387

def _run_one(idx, task):
    ...
    _done_count[0] += 1  # L5427: ロックなし！
```

**問題点**:
- Python の `+=` は read-modify-write 操作で、CPython の GIL があっても理論上は整数のインクリメントがアトミックでない場面がある
- 実際に4エージェント全て完了しているのにカウンタが0のままだった可能性

**修正案**:
```python
# _done_count をロック付きにする、または threading.Lock を使う
_done_lock = threading.Lock()

def _run_one(idx, task):
    ...
    with _done_lock:
        _done_count[0] += 1
```

ただし、CPython の GIL の下では `list[0] += 1` (整数) は実質アトミックなので、本当のバグかどうかは微妙。ハートビートの `int(elapsed) % 5 != 0` 条件 (L5479) により、5秒ごとにしか表示されないため、110秒時点でたまたま表示が0だった可能性もある。

**優先度**: MEDIUM

---

## Issue 4: 29K prompt / 158 completion トークンのアンバランス

**ログ**: `[debug] Response: prompt=29329 completion=158`
**根本原因**: サブエージェントの `chat_sync()` (non-streaming) レスポンスで、model がツールコールのみを返した場合、`completion_tokens` はツールコール引数 + 短いテキストだけになる

**分析**:
- 29K tokens のプロンプト構成: system prompt (~500) + ユーザープロンプト (~500) + ツールスキーマ (5ツール x ~1000 = ~5000) + ... = ~6K tokens。29K は大きすぎる
- `_build_sub_system_prompt()` に blackboard context が含まれる場合、他エージェントの findings が入る
- ツールの schemas が全て渡されている（`get_schemas()` から `allowed_tools` でフィルタしているが、description が長い）

**問題点**:
1. デバッグログに「サブエージェントかメインエージェントか」の区別がない
2. ツールスキーマのトークン数がログに出ない
3. prompt/completion 比率の異常を警告しない

**修正案**:
```python
# (A) デバッグログにエージェント種別を追加
if self.debug:
    _agent_type = "[sub-agent]" if is_subagent else "[main]"
    print(f"[debug] {_agent_type} POST ... prompt={p} completion={c}")

# (B) 異常比率の警告
if prompt_tokens > 0 and completion_tokens > 0:
    ratio = prompt_tokens / completion_tokens
    if ratio > 100:
        print(f"[debug] WARNING: prompt/completion ratio={ratio:.0f}x "
              f"(possible wasted tokens)")
```

**優先度**: MEDIUM

---

## Issue 5: Ctrl+C (SIGINT) でサブエージェントスレッドが停止しない

**ログ**: `^C -> Exception ignored on threading shutdown`, `[Agent 1/4] Sub-agent finished (116.0s) after Ctrl+C`

**根本原因**: Ctrl+C (KeyboardInterrupt) はメインスレッドにのみ配信される。`MultiAgentCoordinator.run_parallel()` の `_cancel` Event は ESC 検出のみに設定され、Ctrl+C では設定されない。

```python
# L5470-5477: ESC のみ _cancel を設定
_esc = globals().get("_esc_monitor")
if _esc and getattr(_esc, "pressed", False):
    _cancel.set()
```

**問題点**:
1. WorkQueue の daemon スレッド内で HTTP リクエストがブロック中の場合、cancel されない
2. メインスレッドで KeyboardInterrupt が発生しても、`wq.run_all()` の `future.result(timeout=300)` で最大300秒待つ
3. 終了後もスレッドが生存して API コールを続ける

**修正案**:
```python
# (A) メインスレッドの KeyboardInterrupt で _cancel を設定
try:
    wq.run_all()
except KeyboardInterrupt:
    _cancel.set()
    _heartbeat_stop.set()

# (B) _run_one 内の各 API コール前に _cancel をチェック
def _run_one(idx, task):
    ...
    for _attempt in range(_max_retries + 1):
        if _cancel.is_set():
            results[idx] = {..., "error": "Cancelled"}
            return
        # HTTP コール前に再チェック
```

**優先度**: HIGH

---

## Issue 6: レートリミット対応の改善点

**ログ**: `⚡ anthropic rate limited (attempt 1/5) -> Trying openai/gpt-4o-mini`

**現在の動作** (L2150-2279):
- MAX_RETRIES = 5
- Same-tier fallback -> Cross-tier fallback -> Exponential backoff
- Cross-tier fallback は strong -> balanced -> fast の一方向降格

**改善点**:
1. **フォールバック先のログが不十分**: `-> Trying openai/gpt-4o-mini` はユーザーに見えるが、`[debug]` レベルで「なぜそのモデルが選ばれたか」(same-tier? cross-tier?) が示されていない
2. **リトライ回数**: 並列エージェント内の `_max_retries = 2` (L5404) とメインの `MAX_RETRIES = 5` が異なる。並列エージェントは4つ同時にAPIを叩くので、レートリミットに当たりやすい。並列時はリトライ回数を増やすべき
3. **jitter の計算**: L2235 の `random.uniform(0, backoff * 0.3)` は控えめ。並列エージェントが同時にリトライすると再びバーストする。並列時は agent index に基づくオフセットを加えるべき

**修正案**:
```python
# 並列エージェント内のリトライ回数を増やす
_max_retries = 3  # was 2

# jitter に agent index を加味
wait = 3 + _attempt * 2 + random.uniform(0, 2) + (idx * 1.5)
```

**優先度**: MEDIUM

---

## Issue 7: ストリーミング時のトークン使用量デバッグログ欠如

**現状**:
- Non-streaming (`chat_sync`): L1850 でトークン数をログ出力
- Streaming (`chat` with `stream=True`): ストリーム終了時のトークンログなし

```python
# L1848-1851: non-streaming のみ
if self.debug:
    usage = result.get("usage", {})
    print(f"[debug] Response: prompt={...} completion={...}")
```

メインループは常に `stream=True` (L8693) なので、**通常の使用では prompt/completion のデバッグログが出ない**。ログに表示されている `[debug] Response: prompt=29329 completion=158` はサブエージェントの `chat_sync()` 呼び出しから来ている。

**修正案**: ストリーミング完了後に `message_delta` イベントからusage情報を抽出してログ出力する。

**優先度**: LOW

---

## Summary Table

| # | Issue | Severity | Fix Complexity |
|---|-------|----------|----------------|
| 1 | ExecutionMemory が tier を不適切にオーバーライド | HIGH | Medium |
| 2 | researcher ロールが fast 固定 | HIGH | Low |
| 3 | `_done_count` にロックがない | MEDIUM | Low |
| 4 | prompt/completion 比率異常の警告なし | MEDIUM | Low |
| 5 | Ctrl+C でサブエージェントが停止しない | HIGH | Medium |
| 6 | 並列エージェントのレートリミット対応 | MEDIUM | Medium |
| 7 | ストリーミング時のトークンログ欠如 | LOW | Medium |

---

## Appendix: Recommended Debug Log Format

現在のフォーマット:
```
[orchestrator] tier=fast
[debug] POST https://api.anthropic.com/v1/messages model=claude-opus-4-6 msgs=1 tools=20 stream=True
[debug] Response: prompt=29329 completion=158
```

推奨フォーマット:
```
[orchestrator] tier=fast (classified=strong memory_override=fast) -> anthropic/claude-haiku-4-5-20251001 input="デジタルネイチャーについて深く調査..."
[debug] [main] POST https://api.anthropic.com/v1/messages model=claude-opus-4-6 msgs=1 tools=20 stream=True
[debug] [sub-agent 1/4 researcher] POST model=claude-haiku-4-5-20251001 msgs=2 tools=5
[debug] [sub-agent 1/4] Response: prompt=29329 completion=158 (ratio=185x WARNING: low output)
[debug] [sub-agent 1/4] turn=1/10 action=tool_call(WebSearch) -> 2.3s
```

追加すべき情報:
- `[main]` vs `[sub-agent N/M role]` のプレフィックス
- tier 選択理由（classified, memory_override）
- 解決されたモデル名
- prompt/completion 比率の異常警告
- サブエージェントのturn番号とアクション
