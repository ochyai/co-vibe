"""Tests for Session class and utility functions in co-vibe.py."""

import sys
import os
import json
import tempfile
import hashlib
import importlib
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Import co-vibe module (hyphenated name requires importlib)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
co_vibe = importlib.import_module("co-vibe")
Session = co_vibe.Session
Config = co_vibe.Config
ToolResult = co_vibe.ToolResult
_get_ram_gb = co_vibe._get_ram_gb
_build_system_prompt = co_vibe._build_system_prompt
_display_width = co_vibe._display_width
_truncate_to_display_width = co_vibe._truncate_to_display_width


def _make_config(**overrides):
    """Create a minimal mock config for testing."""
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


# ════════════════════════════════════════════════════════════════════════════════
# Session.__init__
# ════════════════════════════════════════════════════════════════════════════════

class TestSessionInit(unittest.TestCase):
    def test_init_creates_empty_messages(self):
        cfg = _make_config()
        s = Session(cfg, "You are a helper.")
        self.assertEqual(s.messages, [])

    def test_init_stores_config_and_prompt(self):
        cfg = _make_config()
        prompt = "System prompt text"
        s = Session(cfg, prompt)
        self.assertIs(s.config, cfg)
        self.assertEqual(s.system_prompt, prompt)

    def test_init_generates_session_id_when_none(self):
        cfg = _make_config(session_id=None)
        s = Session(cfg, "prompt")
        self.assertTrue(len(s.session_id) > 0)

    def test_init_uses_provided_session_id(self):
        cfg = _make_config(session_id="my_custom_session")
        s = Session(cfg, "prompt")
        self.assertEqual(s.session_id, "my_custom_session")

    def test_init_sanitizes_session_id(self):
        cfg = _make_config(session_id="../../etc/passwd")
        s = Session(cfg, "prompt")
        # Path traversal chars should be stripped
        self.assertNotIn("/", s.session_id)
        self.assertNotIn("..", s.session_id)

    def test_init_token_estimate_zero(self):
        cfg = _make_config()
        s = Session(cfg, "prompt")
        self.assertEqual(s._token_estimate, 0)


# ════════════════════════════════════════════════════════════════════════════════
# Session.add_user_message
# ════════════════════════════════════════════════════════════════════════════════

class TestAddUserMessage(unittest.TestCase):
    def test_appends_user_role(self):
        s = Session(_make_config(), "prompt")
        s.add_user_message("Hello")
        self.assertEqual(len(s.messages), 1)
        self.assertEqual(s.messages[0]["role"], "user")
        self.assertEqual(s.messages[0]["content"], "Hello")

    def test_updates_token_estimate(self):
        s = Session(_make_config(), "prompt")
        s.add_user_message("Hello world, this is a test message.")
        self.assertGreater(s._token_estimate, 0)

    def test_multiple_messages_appended_in_order(self):
        s = Session(_make_config(), "prompt")
        s.add_user_message("first")
        s.add_user_message("second")
        self.assertEqual(s.messages[0]["content"], "first")
        self.assertEqual(s.messages[1]["content"], "second")


# ════════════════════════════════════════════════════════════════════════════════
# Session.add_assistant_message
# ════════════════════════════════════════════════════════════════════════════════

class TestAddAssistantMessage(unittest.TestCase):
    def test_appends_assistant_role(self):
        s = Session(_make_config(), "prompt")
        s.add_assistant_message("Hi there")
        self.assertEqual(s.messages[0]["role"], "assistant")
        self.assertEqual(s.messages[0]["content"], "Hi there")

    def test_none_text_stored_as_none(self):
        s = Session(_make_config(), "prompt")
        s.add_assistant_message(None)
        self.assertIsNone(s.messages[0]["content"])

    def test_tool_calls_attached(self):
        s = Session(_make_config(), "prompt")
        tool_calls = [{"id": "tc1", "function": {"name": "Bash", "arguments": '{"cmd":"ls"}'}}]
        s.add_assistant_message("", tool_calls=tool_calls)
        self.assertEqual(s.messages[0]["tool_calls"], tool_calls)

    def test_no_tool_calls_key_when_none(self):
        s = Session(_make_config(), "prompt")
        s.add_assistant_message("just text")
        self.assertNotIn("tool_calls", s.messages[0])

    def test_tool_calls_increase_token_estimate(self):
        s = Session(_make_config(), "prompt")
        tool_calls = [{"id": "tc1", "function": {"name": "Bash", "arguments": '{"cmd":"ls -la"}'}}]
        s.add_assistant_message("", tool_calls=tool_calls)
        self.assertGreater(s._token_estimate, 0)


# ════════════════════════════════════════════════════════════════════════════════
# Session.add_tool_results
# ════════════════════════════════════════════════════════════════════════════════

class TestAddToolResults(unittest.TestCase):
    def test_adds_tool_role_messages(self):
        s = Session(_make_config(), "prompt")
        results = [ToolResult("tc1", "output text")]
        s.add_tool_results(results)
        self.assertEqual(len(s.messages), 1)
        self.assertEqual(s.messages[0]["role"], "tool")
        self.assertEqual(s.messages[0]["tool_call_id"], "tc1")
        self.assertEqual(s.messages[0]["content"], "output text")

    def test_multiple_results(self):
        s = Session(_make_config(), "prompt")
        results = [ToolResult("tc1", "out1"), ToolResult("tc2", "out2")]
        s.add_tool_results(results)
        tool_msgs = [m for m in s.messages if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 2)

    def test_image_marker_creates_multipart(self):
        s = Session(_make_config(), "prompt")
        marker = json.dumps({"type": "image", "media_type": "image/png", "data": "abc123base64"})
        results = [ToolResult("tc1", marker)]
        s.add_tool_results(results)
        # Should have a tool message and a user multipart message
        self.assertEqual(s.messages[0]["role"], "tool")
        self.assertEqual(s.messages[1]["role"], "user")
        self.assertIsInstance(s.messages[1]["content"], list)

    def test_truncates_large_output(self):
        s = Session(_make_config(context_window=1000), "prompt")
        huge_output = "x" * 100000
        results = [ToolResult("tc1", huge_output)]
        s.add_tool_results(results)
        content = s.messages[0]["content"]
        self.assertIn("truncated", content)
        self.assertLess(len(content), len(huge_output))


# ════════════════════════════════════════════════════════════════════════════════
# Session.add_system_note
# ════════════════════════════════════════════════════════════════════════════════

class TestAddSystemNote(unittest.TestCase):
    def test_adds_as_user_message_with_prefix(self):
        s = Session(_make_config(), "prompt")
        s.add_system_note("File changed: foo.py")
        self.assertEqual(s.messages[0]["role"], "user")
        self.assertIn("[System Note]", s.messages[0]["content"])
        self.assertIn("File changed: foo.py", s.messages[0]["content"])


# ════════════════════════════════════════════════════════════════════════════════
# Session.get_messages
# ════════════════════════════════════════════════════════════════════════════════

class TestGetMessages(unittest.TestCase):
    def test_prepends_system_prompt(self):
        s = Session(_make_config(), "You are helpful.")
        s.add_user_message("hi")
        msgs = s.get_messages()
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], "You are helpful.")
        self.assertEqual(msgs[1]["role"], "user")

    def test_empty_session_has_system_only(self):
        s = Session(_make_config(), "sys prompt")
        msgs = s.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "system")


# ════════════════════════════════════════════════════════════════════════════════
# Session.get_token_estimate
# ════════════════════════════════════════════════════════════════════════════════

class TestGetTokenEstimate(unittest.TestCase):
    def test_includes_system_prompt_tokens(self):
        prompt = "A" * 400  # ~100 tokens for ASCII
        s = Session(_make_config(), prompt)
        estimate = s.get_token_estimate()
        self.assertGreater(estimate, 0)

    def test_increases_after_adding_messages(self):
        s = Session(_make_config(), "prompt")
        est_before = s.get_token_estimate()
        s.add_user_message("Hello world " * 100)
        est_after = s.get_token_estimate()
        self.assertGreater(est_after, est_before)


# ════════════════════════════════════════════════════════════════════════════════
# Session._estimate_tokens (static)
# ════════════════════════════════════════════════════════════════════════════════

class TestEstimateTokens(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(Session._estimate_tokens(""), 0)

    def test_none(self):
        self.assertEqual(Session._estimate_tokens(None), 0)

    def test_ascii_roughly_len_div_4(self):
        text = "Hello world this is a test"
        tokens = Session._estimate_tokens(text)
        expected = len(text) // 4
        self.assertEqual(tokens, expected)

    def test_cjk_roughly_len(self):
        text = "こんにちは世界"  # 7 CJK characters
        tokens = Session._estimate_tokens(text)
        # Each CJK char = 1 token, no non-CJK
        self.assertEqual(tokens, 7)

    def test_mixed_text(self):
        text = "Hello世界"  # 5 ASCII + 2 CJK
        tokens = Session._estimate_tokens(text)
        # 2 CJK tokens + 5//4 = 1 ASCII token = 3
        self.assertEqual(tokens, 2 + 5 // 4)

    def test_korean_counted_as_cjk(self):
        text = "안녕하세요"  # 5 Korean characters
        tokens = Session._estimate_tokens(text)
        self.assertEqual(tokens, 5)

    def test_fullwidth_counted_as_cjk(self):
        text = "\uff01\uff02"  # 2 fullwidth characters
        tokens = Session._estimate_tokens(text)
        self.assertEqual(tokens, 2)


# ════════════════════════════════════════════════════════════════════════════════
# Session._enforce_max_messages
# ════════════════════════════════════════════════════════════════════════════════

class TestEnforceMaxMessages(unittest.TestCase):
    def test_no_trimming_below_limit(self):
        s = Session(_make_config(), "prompt")
        for i in range(10):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        s._enforce_max_messages()
        self.assertEqual(len(s.messages), 10)

    def test_trims_when_exceeding_limit(self):
        s = Session(_make_config(), "prompt")
        # Exceed MAX_MESSAGES
        for i in range(Session.MAX_MESSAGES + 50):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        s._enforce_max_messages()
        self.assertLessEqual(len(s.messages), Session.MAX_MESSAGES)

    def test_does_not_start_with_orphaned_tool(self):
        s = Session(_make_config(), "prompt")
        # Fill with MAX_MESSAGES + some, starting with tool results
        for i in range(Session.MAX_MESSAGES + 10):
            if i < 5:
                s.messages.append({"role": "tool", "tool_call_id": f"tc{i}", "content": "out"})
            else:
                s.messages.append({"role": "user", "content": f"msg {i}"})
        s._enforce_max_messages()
        # First message should not be a tool result
        self.assertNotEqual(s.messages[0]["role"], "tool")

    def test_never_empties_all_messages(self):
        s = Session(_make_config(), "prompt")
        for i in range(Session.MAX_MESSAGES + 100):
            s.messages.append({"role": "user", "content": f"msg {i}"})
        s._enforce_max_messages()
        self.assertGreater(len(s.messages), 0)


# ════════════════════════════════════════════════════════════════════════════════
# Session.save / Session.load
# ════════════════════════════════════════════════════════════════════════════════

class TestSaveLoad(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="test_sess")
            s = Session(cfg, "prompt")
            s.add_user_message("Hello")
            s.add_assistant_message("Hi there")
            s.save()

            s2 = Session(cfg, "prompt")
            loaded = s2.load("test_sess")
            self.assertTrue(loaded)
            self.assertEqual(len(s2.messages), 2)
            self.assertEqual(s2.messages[0]["content"], "Hello")
            self.assertEqual(s2.messages[1]["content"], "Hi there")

    def test_load_sets_session_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="sid_abc")
            s = Session(cfg, "prompt")
            s.add_user_message("data")
            s.save()

            cfg2 = _make_config(sessions_dir=tmpdir)
            s2 = Session(cfg2, "prompt")
            s2.load("sid_abc")
            self.assertEqual(s2.session_id, "sid_abc")

    def test_load_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir)
            s = Session(cfg, "prompt")
            self.assertFalse(s.load("nonexistent_session"))

    def test_save_empty_session_creates_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="empty_test")
            s = Session(cfg, "prompt")
            s.save()  # no messages
            path = os.path.join(tmpdir, "empty_test.jsonl")
            self.assertFalse(os.path.exists(path))

    def test_save_creates_jsonl_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="jsonl_test")
            s = Session(cfg, "prompt")
            s.add_user_message("line1")
            s.add_assistant_message("line2")
            s.save()

            path = os.path.join(tmpdir, "jsonl_test.jsonl")
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            self.assertEqual(len(lines), 2)
            for line in lines:
                obj = json.loads(line)
                self.assertIn("role", obj)

    def test_load_recalculates_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="tok_test")
            s = Session(cfg, "prompt")
            s.add_user_message("Hello world " * 50)
            s.save()

            s2 = Session(cfg, "prompt")
            s2.load("tok_test")
            self.assertGreater(s2._token_estimate, 0)


# ════════════════════════════════════════════════════════════════════════════════
# Session.list_sessions (static)
# ════════════════════════════════════════════════════════════════════════════════

class TestListSessions(unittest.TestCase):
    def test_returns_empty_for_no_dir(self):
        cfg = _make_config(sessions_dir="/tmp/nonexistent_dir_xyz_12345")
        sessions = Session.list_sessions(cfg)
        self.assertEqual(sessions, [])

    def test_lists_saved_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="list_test")
            s = Session(cfg, "prompt")
            s.add_user_message("data")
            s.save()

            sessions = Session.list_sessions(cfg)
            self.assertGreaterEqual(len(sessions), 1)
            ids = [sess["id"] for sess in sessions]
            self.assertIn("list_test", ids)

    def test_session_metadata_has_expected_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _make_config(sessions_dir=tmpdir, session_id="meta_test")
            s = Session(cfg, "prompt")
            s.add_user_message("data")
            s.save()

            sessions = Session.list_sessions(cfg)
            sess = sessions[0]
            self.assertIn("id", sess)
            self.assertIn("modified", sess)
            self.assertIn("size", sess)
            self.assertIn("messages", sess)


# ════════════════════════════════════════════════════════════════════════════════
# Session._cwd_hash (static)
# ════════════════════════════════════════════════════════════════════════════════

class TestCwdHash(unittest.TestCase):
    def test_deterministic(self):
        cfg = _make_config(cwd="/tmp/project_a")
        h1 = Session._cwd_hash(cfg)
        h2 = Session._cwd_hash(cfg)
        self.assertEqual(h1, h2)

    def test_different_cwd_different_hash(self):
        cfg_a = _make_config(cwd="/tmp/project_a")
        cfg_b = _make_config(cwd="/tmp/project_b")
        self.assertNotEqual(Session._cwd_hash(cfg_a), Session._cwd_hash(cfg_b))

    def test_hash_length(self):
        cfg = _make_config(cwd="/tmp/anything")
        h = Session._cwd_hash(cfg)
        self.assertEqual(len(h), 16)  # sha256[:16]


# ════════════════════════════════════════════════════════════════════════════════
# Session._parse_image_marker (static)
# ════════════════════════════════════════════════════════════════════════════════

class TestParseImageMarker(unittest.TestCase):
    def test_valid_image_marker(self):
        marker = json.dumps({"type": "image", "media_type": "image/png", "data": "base64stuff"})
        result = Session._parse_image_marker(marker)
        self.assertIsNotNone(result)
        self.assertEqual(result, ("image/png", "base64stuff"))

    def test_non_image_json_returns_none(self):
        marker = json.dumps({"type": "text", "content": "hello"})
        result = Session._parse_image_marker(marker)
        self.assertIsNone(result)

    def test_invalid_json_returns_none(self):
        result = Session._parse_image_marker("not json at all")
        self.assertIsNone(result)

    def test_none_input_returns_none(self):
        result = Session._parse_image_marker(None)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        result = Session._parse_image_marker("")
        self.assertIsNone(result)

    def test_missing_data_field_returns_none(self):
        marker = json.dumps({"type": "image", "media_type": "image/png"})
        result = Session._parse_image_marker(marker)
        self.assertIsNone(result)


# ════════════════════════════════════════════════════════════════════════════════
# Session.compact_if_needed
# ════════════════════════════════════════════════════════════════════════════════

class TestCompactIfNeeded(unittest.TestCase):
    def test_no_op_when_small(self):
        s = Session(_make_config(context_window=200000), "prompt")
        for i in range(5):
            s.add_user_message(f"msg {i}")
        msg_count_before = len(s.messages)
        s.compact_if_needed()
        self.assertEqual(len(s.messages), msg_count_before)

    def test_triggers_when_over_threshold(self):
        cfg = _make_config(context_window=1000, sidecar_model="")
        s = Session(cfg, "prompt")
        s._client = None  # no sidecar
        # Add enough messages to exceed 70% of context window (700 tokens)
        for i in range(200):
            s.add_user_message("x" * 100)  # ~25 tokens each -> 5000 total, well over 700
        msg_count_before = len(s.messages)
        s.compact_if_needed()
        self.assertLess(len(s.messages), msg_count_before)

    def test_force_compaction(self):
        cfg = _make_config(context_window=200000, sidecar_model="")
        s = Session(cfg, "prompt")
        s._client = None
        for i in range(50):
            s.add_user_message(f"message number {i}")
        msg_count_before = len(s.messages)
        s.compact_if_needed(force=True)
        self.assertLess(len(s.messages), msg_count_before)

    def test_sidecar_summarization_path(self):
        cfg = _make_config(context_window=1000, sidecar_model="mock-model")
        s = Session(cfg, "prompt")

        # Mock client that returns a summary
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "- Summary bullet 1\n- Summary bullet 2"}}]
        }
        s.set_client(mock_client)

        for i in range(200):
            s.add_user_message("x" * 100)

        s.compact_if_needed()
        # After sidecar compaction, should have summary message
        summary_msgs = [m for m in s.messages if "[Earlier conversation summary]" in (m.get("content") or "")]
        self.assertGreater(len(summary_msgs), 0)


# ════════════════════════════════════════════════════════════════════════════════
# Utility: _get_ram_gb
# ════════════════════════════════════════════════════════════════════════════════

class TestGetRamGb(unittest.TestCase):
    def test_returns_positive_number(self):
        ram = _get_ram_gb()
        self.assertIsInstance(ram, int)
        self.assertGreater(ram, 0)


# ════════════════════════════════════════════════════════════════════════════════
# Utility: _build_system_prompt
# ════════════════════════════════════════════════════════════════════════════════

class TestBuildSystemPrompt(unittest.TestCase):
    def test_includes_cwd(self):
        cfg = _make_config(cwd="/tmp/my_project")
        # _build_system_prompt expects config with cwd attribute
        prompt = _build_system_prompt(cfg)
        self.assertIn("/tmp/my_project", prompt)

    def test_includes_platform_info(self):
        import platform as plat_mod
        cfg = _make_config(cwd="/tmp/test")
        prompt = _build_system_prompt(cfg)
        # Should contain platform info
        self.assertIn(plat_mod.system().lower(), prompt.lower())

    def test_returns_string(self):
        cfg = _make_config(cwd="/tmp/test")
        prompt = _build_system_prompt(cfg)
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)


# ════════════════════════════════════════════════════════════════════════════════
# Utility: _display_width
# ════════════════════════════════════════════════════════════════════════════════

class TestDisplayWidth(unittest.TestCase):
    def test_ascii_width_1(self):
        self.assertEqual(_display_width("a"), 1)
        self.assertEqual(_display_width("abc"), 3)

    def test_cjk_width_2(self):
        # CJK ideographs are double-width
        self.assertEqual(_display_width("\u4e16"), 2)  # 世
        self.assertEqual(_display_width("世界"), 4)

    def test_mixed_text(self):
        # "Hi世界" = 2 (ASCII) + 4 (CJK) = 6
        self.assertEqual(_display_width("Hi世界"), 6)

    def test_empty_string(self):
        self.assertEqual(_display_width(""), 0)

    def test_fullwidth_chars(self):
        # Fullwidth exclamation mark
        self.assertEqual(_display_width("\uff01"), 2)


# ════════════════════════════════════════════════════════════════════════════════
# Utility: _truncate_to_display_width
# ════════════════════════════════════════════════════════════════════════════════

class TestTruncateToDisplayWidth(unittest.TestCase):
    def test_no_truncation_within_limit(self):
        text = "Hello"
        result = _truncate_to_display_width(text, 10)
        self.assertEqual(result, text)

    def test_truncates_ascii(self):
        text = "Hello World!"
        result = _truncate_to_display_width(text, 5)
        self.assertTrue(result.endswith("..."))
        # Display width of truncated part (excluding "...") should be <= 5
        self.assertLessEqual(len(result), len(text))

    def test_truncates_cjk(self):
        text = "世界こんにちは"  # each char width 2, total 14
        result = _truncate_to_display_width(text, 5)
        self.assertTrue(result.endswith("..."))

    def test_exact_fit_no_truncation(self):
        text = "Hello"
        result = _truncate_to_display_width(text, 5)
        self.assertEqual(result, text)

    def test_empty_string(self):
        result = _truncate_to_display_width("", 10)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
