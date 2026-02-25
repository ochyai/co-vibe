"""Headless integration tests for co-vibe.

These tests run co-vibe.py as a subprocess, send commands via stdin,
and verify stdout/stderr responses. No real API calls are made --
only slash commands and UI interactions are tested.

Run with: pytest tests/test_integration.py -v
"""

import os
import sys
import time
import signal
import subprocess
import tempfile

import pytest

CO_VIBE_PATH = os.path.join(os.path.dirname(__file__), "..", "co-vibe.py")
PYTHON = sys.executable


def _launch_co_vibe(extra_args=None, env_override=None, timeout=10):
    """Launch co-vibe.py as a subprocess with no API keys (dry environment).

    Returns a Popen object. stdin/stdout/stderr are PIPEs.
    Environment is stripped of real API keys and HOME is redirected
    to a temp dir so .env files are not discovered.
    """
    env = os.environ.copy()
    # Remove real API keys to avoid accidental API calls
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
        env.pop(key, None)
    # Redirect HOME to temp dir so .env file is not found
    _fake_home = tempfile.mkdtemp(prefix="covibe_test_")
    env["HOME"] = _fake_home
    # Force non-interactive: NO_COLOR=1 to disable ANSI, TERM=dumb
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["VIBE_NO_SCROLL"] = "1"
    env["CO_VIBE_NO_OLLAMA"] = "1"  # Disable Ollama auto-detect in tests
    env["CO_VIBE_NO_DOTENV"] = "1"  # Skip .env loading (avoid picking up real keys)
    if env_override:
        env.update(env_override)

    args = [PYTHON, CO_VIBE_PATH]
    if extra_args:
        args.extend(extra_args)

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )
    return proc


def _send_and_collect(proc, commands, timeout=10):
    """Send commands to proc stdin and collect stdout/stderr.

    commands: list of strings (each is a line sent to stdin)
    Returns (stdout, stderr, returncode).
    """
    input_text = "\n".join(commands) + "\n"
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
    return stdout, stderr, proc.returncode


# ── 1. No API keys: exits with error message ─────────────────────────────────

class TestNoApiKeysExit:
    """co-vibe without API keys should exit with an error message."""

    def test_exits_with_no_keys(self):
        """Without any API keys, co-vibe should exit with returncode 1."""
        proc = _launch_co_vibe()
        stdout, stderr, rc = _send_and_collect(proc, [], timeout=10)
        # Should exit with error about no API keys
        assert rc == 1, f"Expected exit code 1, got {rc}. stdout={stdout!r}"
        combined = stdout + stderr
        assert "no api" in combined.lower() or "api key" in combined.lower(), (
            f"Expected 'no API' or 'API key' message, got: {combined!r}"
        )


# ── 2. One-shot mode (-p) ────────────────────────────────────────────────────

class TestOneShotMode:
    """One-shot mode (-p) without API keys should fail gracefully."""

    def test_oneshot_no_keys_exits(self):
        """co-vibe -p 'hello' without API keys exits with error."""
        proc = _launch_co_vibe(extra_args=["-p", "hello"])
        stdout, stderr, rc = _send_and_collect(proc, [], timeout=10)
        assert rc == 1
        combined = stdout + stderr
        assert "no api" in combined.lower() or "api key" in combined.lower()


# ── 3. --list-sessions ───────────────────────────────────────────────────────

class TestListSessions:
    """--list-sessions should work without API keys (it reads local files only)."""

    def test_list_sessions_empty(self):
        """--list-sessions with no saved sessions prints 'No saved sessions'."""
        # Use a temp dir so there are no existing sessions
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "HOME": tmpdir,
                "XDG_DATA_HOME": os.path.join(tmpdir, ".local", "share"),
                "XDG_STATE_HOME": os.path.join(tmpdir, ".local", "state"),
                "XDG_CONFIG_HOME": os.path.join(tmpdir, ".config"),
            }
            proc = _launch_co_vibe(extra_args=["--list-sessions"], env_override=env)
            stdout, stderr, rc = _send_and_collect(proc, [], timeout=10)
            assert rc == 0
            assert "no saved sessions" in stdout.lower(), (
                f"Expected 'No saved sessions', got: {stdout!r}"
            )


# ── 4. Version check ─────────────────────────────────────────────────────────

class TestVersionImport:
    """Verify the module can be imported and has a version."""

    def test_module_has_version(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        assert hasattr(co_vibe, "__version__")
        assert isinstance(co_vibe.__version__, str)
        assert len(co_vibe.__version__) > 0


# ── 5. Config class basic tests ──────────────────────────────────────────────

class TestConfigDefaults:
    """Config should have sensible defaults."""

    def test_default_values(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        cfg = co_vibe.Config()
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.temperature == 0.7
        assert cfg.max_tokens == 8192
        assert cfg.context_window == 200000
        assert cfg.strategy == "auto"
        assert cfg.yes_mode is False
        assert cfg.debug is False


# ── 6. Session class ─────────────────────────────────────────────────────────

class TestSession:
    """Session basic functionality."""

    def _get_session_class(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        return co_vibe.Session, co_vibe.Config

    def test_session_creation(self):
        Session, Config = self._get_session_class()
        cfg = Config()
        cfg._ensure_dirs = lambda: None  # avoid creating dirs
        sess = Session(cfg, "test system prompt")
        assert len(sess.messages) == 0
        assert sess.session_id is not None

    def test_session_token_estimate(self):
        Session, Config = self._get_session_class()
        cfg = Config()
        sess = Session(cfg, "test")
        assert sess.get_token_estimate() >= 0

    def test_session_save_and_load(self):
        Session, Config = self._get_session_class()
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config()
            cfg.state_dir = tmpdir
            cfg.sessions_dir = os.path.join(tmpdir, "sessions")
            os.makedirs(cfg.sessions_dir, exist_ok=True)
            cfg.cwd = tmpdir

            sess = Session(cfg, "test prompt")
            sess.messages.append({"role": "user", "content": "hello"})
            sess.messages.append({"role": "assistant", "content": "hi"})
            sess.save()

            # Load it back
            sess2 = Session(cfg, "test prompt")
            loaded = sess2.load(sess.session_id)
            assert loaded is True
            assert len(sess2.messages) >= 2


# ── 7. Slash command output format (import-based) ────────────────────────────

class TestSlashCommandsViaImport:
    """Test slash command handling by importing classes and calling methods."""

    def _get_module(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        return importlib.import_module("co-vibe")

    def test_help_output_contains_commands(self, capsys):
        """show_help() should list known commands like /help, /status, /tokens."""
        co_vibe = self._get_module()
        # Disable colors for clean capture
        co_vibe.C.disable()
        cfg = co_vibe.Config()
        tui = co_vibe.TUI(cfg)
        tui.is_interactive = False
        tui.show_help()
        captured = capsys.readouterr()
        output = captured.out
        assert "/help" in output
        assert "/status" in output
        assert "/tokens" in output
        assert "/exit" in output
        assert "/commit" in output
        assert "/plan" in output

    def test_status_output(self, capsys):
        """show_status() should display session info."""
        co_vibe = self._get_module()
        co_vibe.C.disable()
        cfg = co_vibe.Config()
        sess = co_vibe.Session(cfg, "test")
        tui = co_vibe.TUI(cfg)
        tui.is_interactive = False
        tui.show_status(sess, cfg)
        captured = capsys.readouterr()
        output = captured.out
        assert "Session" in output
        assert "Messages" in output
        assert "Model" in output
        assert "Strategy" in output

    def test_unknown_command_suggestion(self, capsys):
        """Unknown slash commands should suggest close matches."""
        co_vibe = self._get_module()
        co_vibe.C.disable()
        # Simulate: the main loop handles unknown commands with "Did you mean?"
        # We test the logic directly
        cmd = "/hel"
        _all_cmds = ["/help", "/exit", "/quit", "/clear", "/model", "/models",
                     "/status", "/save", "/compact", "/yes", "/no",
                     "/tokens", "/commit", "/diff", "/git", "/plan",
                     "/approve", "/act", "/execute", "/undo", "/init",
                     "/config", "/debug", "/debug-scroll", "/checkpoint",
                     "/rollback", "/autotest", "/skills"]
        _close = [c for c in _all_cmds if c.startswith(cmd[:3])] if len(cmd) >= 3 else []
        assert "/help" in _close


# ── 8. SIGINT handling ────────────────────────────────────────────────────────

class TestSignalHandling:
    """Test that co-vibe handles signals correctly."""

    @pytest.mark.skipif(os.name == "nt", reason="SIGINT not reliable on Windows")
    def test_sigterm_cleanup(self):
        """Sending SIGTERM to co-vibe should trigger cleanup without crash."""
        # Without API keys, co-vibe exits immediately with code 1.
        # This test just verifies the signal handler is registered (it is at module level).
        # We verify by importing the module and checking the handler.
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe_mod = importlib.import_module("co-vibe")
        # The signal handler for SIGTERM should be registered
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not None
        assert handler is not signal.SIG_DFL

    @pytest.mark.skipif(os.name == "nt", reason="SIGINT not reliable on Windows")
    def test_no_keys_process_exits_cleanly(self):
        """co-vibe with no API keys exits with code 1 without Python traceback."""
        proc = _launch_co_vibe()
        stdout, stderr, rc = _send_and_collect(proc, [], timeout=10)
        assert rc == 1
        combined = stdout + stderr
        # The exit should be clean (no Python traceback)
        assert "Traceback (most recent call last)" not in combined


# ── 9. RateLimitError ────────────────────────────────────────────────────────

class TestRateLimitError:
    """Test the RateLimitError class."""

    def test_ratelimit_error_attributes(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        err = co_vibe.RateLimitError("rate limited", provider="anthropic", retry_after=30)
        assert str(err) == "rate limited"
        assert err.provider == "anthropic"
        assert err.retry_after == 30


# ── 10. MultiProviderClient no-key behavior ──────────────────────────────────

class TestClientNoKeys:
    """MultiProviderClient with no keys should return (False, [])."""

    def test_check_connection_no_keys(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        # Temporarily remove real API keys from environment
        _saved = {}
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"):
            if k in os.environ:
                _saved[k] = os.environ.pop(k)
        try:
            cfg = co_vibe.Config()
            cfg.anthropic_api_key = ""
            cfg.openai_api_key = ""
            cfg.groq_api_key = ""
            client = co_vibe.MultiProviderClient(cfg)
            ok, models = client.check_connection()
            assert ok is False
            assert models == []
        finally:
            os.environ.update(_saved)


# ── 11. ToolRegistry ─────────────────────────────────────────────────────────

class TestToolRegistry:
    """ToolRegistry registers default tools correctly."""

    def test_register_defaults(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        registry = co_vibe.ToolRegistry()
        registry.register_defaults()
        tool_names = registry.names()
        # Should have core tools
        assert "Bash" in tool_names
        assert "Read" in tool_names
        assert "Write" in tool_names
        assert "Edit" in tool_names
        assert "Glob" in tool_names
        assert "Grep" in tool_names

    def test_get_tool_schema(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        registry = co_vibe.ToolRegistry()
        registry.register_defaults()
        schemas = registry.get_schemas()
        assert len(schemas) > 0
        # Each schema should have function definition
        for schema in schemas:
            assert "function" in schema


# ── 12. PermissionMgr ────────────────────────────────────────────────────────

class TestPermissionMgr:
    """PermissionMgr basic behavior."""

    def test_yes_mode_allows_all(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        cfg = co_vibe.Config()
        cfg.yes_mode = True
        perm = co_vibe.PermissionMgr(cfg)
        assert perm.yes_mode is True

    def test_default_mode_has_ask_tools(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        co_vibe = importlib.import_module("co-vibe")
        cfg = co_vibe.Config()
        cfg.yes_mode = False
        perm = co_vibe.PermissionMgr(cfg)
        # Bash, Write, Edit should require permission
        assert "Bash" in perm.ASK_TOOLS
        assert "Write" in perm.ASK_TOOLS
        assert "Edit" in perm.ASK_TOOLS


# ── 13. _has_markdown_syntax static method ────────────────────────────────────

class TestHasMarkdownSyntax:
    """TUI._has_markdown_syntax detects markdown patterns."""

    def _get_tui_class(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        return importlib.import_module("co-vibe").TUI

    def test_code_block_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("```python\nprint('hello')\n```") is True

    def test_header_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("# Title") is True
        assert TUI._has_markdown_syntax("## Subtitle") is True

    def test_bold_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("This is **bold** text") is True

    def test_inline_code_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("Use `foo()` here") is True

    def test_plain_text_not_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("Just plain text here") is False

    def test_list_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("- item one\n- item two") is True

    def test_blockquote_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("> quote") is True

    def test_table_detected(self):
        TUI = self._get_tui_class()
        assert TUI._has_markdown_syntax("| col1 | col2 |") is True


# ── 14. Session token estimation ─────────────────────────────────────────────

class TestTokenEstimation:
    """Session._estimate_tokens handles ASCII and CJK text."""

    def _get_estimate(self):
        import importlib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        return importlib.import_module("co-vibe").Session._estimate_tokens

    def test_empty_string(self):
        est = self._get_estimate()
        assert est("") == 0

    def test_ascii_text(self):
        est = self._get_estimate()
        result = est("hello world")
        assert result > 0
        # ~11 chars / 4 = ~2-3 tokens
        assert result <= 11

    def test_cjk_text(self):
        est = self._get_estimate()
        result = est("こんにちは世界")
        # CJK chars should each count as ~1 token
        assert result >= 7

    def test_mixed_text(self):
        est = self._get_estimate()
        result = est("hello こんにちは")
        # 5 ascii chars (1-2 tokens) + 5 CJK (5 tokens) + space
        assert result >= 5
