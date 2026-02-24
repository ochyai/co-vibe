"""UI tests for co-vibe TUI class.

Tests the TUI class methods: banner, show_help, show_status, show_tool_call,
show_tool_result, markdown rendering, ScrollRegion, and ANSI output formatting.

Run with: pytest tests/test_ui.py -v
"""

import io
import os
import re
import sys
import threading

import pytest

# Import co-vibe module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
co_vibe = importlib.import_module("co-vibe")

TUI = co_vibe.TUI
Config = co_vibe.Config
Session = co_vibe.Session
ScrollRegion = co_vibe.ScrollRegion
C = co_vibe.C

# ANSI escape regex for stripping colors
ANSI_RE = re.compile(r'\033\[[0-9;]*[a-zA-Z]')


def _strip_ansi(text):
    """Remove ANSI escape sequences from text."""
    return ANSI_RE.sub('', text)


@pytest.fixture(autouse=True)
def disable_colors():
    """Disable ANSI colors for predictable test output."""
    # Save original state
    original_enabled = C._enabled
    original_attrs = {}
    for attr in dir(C):
        if attr.isupper() and isinstance(getattr(C, attr), str) and attr != "_enabled":
            original_attrs[attr] = getattr(C, attr)

    C.disable()
    yield

    # Restore original state
    C._enabled = original_enabled
    for attr, val in original_attrs.items():
        setattr(C, attr, val)


@pytest.fixture
def config():
    """Create a Config with defaults."""
    cfg = Config()
    cfg.anthropic_api_key = ""
    cfg.openai_api_key = ""
    cfg.groq_api_key = ""
    return cfg


@pytest.fixture
def tui(config):
    """Create a TUI instance with non-interactive mode."""
    t = TUI(config)
    t.is_interactive = False
    t._term_cols = 80
    return t


@pytest.fixture
def session(config):
    """Create a minimal Session."""
    return Session(config, "test system prompt")


# ══════════════════════════════════════════════════════════════════════════════
# 1. TUI.banner()
# ══════════════════════════════════════════════════════════════════════════════

class TestBanner:
    """Test banner output."""

    def test_banner_prints_co_vibe(self, tui, config, capsys):
        """Banner should contain CO-VIBE or CO VIBE text."""
        tui.banner(config, model_ok=True)
        output = capsys.readouterr().out
        # With NO_COLOR, the banner uses text characters
        assert "CO" in output.upper(), f"Banner should contain 'CO': {output!r}"

    def test_banner_shows_strategy(self, tui, config, capsys):
        config.strategy = "auto"
        tui.banner(config, model_ok=True)
        output = capsys.readouterr().out
        assert "auto" in output.lower()

    def test_banner_shows_no_keys_warning(self, tui, config, capsys):
        """When model_ok=False, banner should show warning."""
        tui.banner(config, model_ok=False)
        output = capsys.readouterr().out
        assert "api" in output.lower() or "key" in output.lower()

    def test_banner_shows_help_hint(self, tui, config, capsys):
        """Banner should mention /help."""
        tui.banner(config, model_ok=True)
        output = capsys.readouterr().out
        assert "/help" in output

    def test_banner_narrow_terminal(self, config, capsys):
        """Banner should adapt to narrow terminals."""
        t = TUI(config)
        t.is_interactive = False
        t._term_cols = 40
        t.banner(config, model_ok=True)
        output = capsys.readouterr().out
        # Should not crash; should produce some output
        assert len(output) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. TUI.show_help()
# ══════════════════════════════════════════════════════════════════════════════

class TestShowHelp:
    """Test show_help command listing."""

    def test_help_lists_all_sections(self, tui, capsys):
        tui.show_help()
        output = capsys.readouterr().out
        assert "Commands" in output
        assert "Git" in output
        assert "Plan" in output
        assert "Extensions" in output
        assert "Keyboard" in output
        assert "Tools" in output

    def test_help_lists_core_commands(self, tui, capsys):
        tui.show_help()
        output = capsys.readouterr().out
        for cmd in ["/help", "/exit", "/quit", "/clear", "/model", "/status",
                    "/save", "/compact", "/tokens", "/yes", "/no", "/config"]:
            assert cmd in output, f"Help should list {cmd}"

    def test_help_lists_git_commands(self, tui, capsys):
        tui.show_help()
        output = capsys.readouterr().out
        for cmd in ["/commit", "/diff", "/git"]:
            assert cmd in output, f"Help should list {cmd}"

    def test_help_lists_plan_commands(self, tui, capsys):
        tui.show_help()
        output = capsys.readouterr().out
        for cmd in ["/plan", "/approve", "/checkpoint", "/rollback"]:
            assert cmd in output, f"Help should list {cmd}"

    def test_help_lists_tools(self, tui, capsys):
        tui.show_help()
        output = capsys.readouterr().out
        for tool in ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]:
            assert tool in output, f"Help should list tool {tool}"


# ══════════════════════════════════════════════════════════════════════════════
# 3. TUI.show_status()
# ══════════════════════════════════════════════════════════════════════════════

class TestShowStatus:
    """Test show_status output."""

    def test_status_shows_session_id(self, tui, session, config, capsys):
        tui.show_status(session, config)
        output = capsys.readouterr().out
        assert session.session_id in output

    def test_status_shows_model(self, tui, session, config, capsys):
        tui.show_status(session, config)
        output = capsys.readouterr().out
        assert config.model in output

    def test_status_shows_message_count(self, tui, session, config, capsys):
        session.messages.append({"role": "user", "content": "hello"})
        session.messages.append({"role": "assistant", "content": "hi"})
        tui.show_status(session, config)
        output = capsys.readouterr().out
        assert "Messages" in output
        assert "2" in output

    def test_status_shows_context_bar(self, tui, session, config, capsys):
        tui.show_status(session, config)
        output = capsys.readouterr().out
        assert "Context" in output
        assert "%" in output


# ══════════════════════════════════════════════════════════════════════════════
# 4. TUI.show_tool_call()
# ══════════════════════════════════════════════════════════════════════════════

class TestShowToolCall:
    """Test show_tool_call formatting for different tools."""

    def test_bash_tool_call(self, tui, capsys):
        tui.show_tool_call("Bash", {"command": "ls -la"})
        output = capsys.readouterr().out
        assert "Bash" in output
        assert "ls -la" in output

    def test_read_tool_call(self, tui, capsys):
        tui.show_tool_call("Read", {"file_path": "/tmp/test.py"})
        output = capsys.readouterr().out
        assert "Read" in output
        assert "test.py" in output

    def test_read_tool_call_with_range(self, tui, capsys):
        tui.show_tool_call("Read", {"file_path": "/tmp/test.py", "offset": 10, "limit": 50})
        output = capsys.readouterr().out
        assert "Read" in output
        assert "L10" in output or "10" in output

    def test_write_tool_call(self, tui, capsys):
        tui.show_tool_call("Write", {"file_path": "/tmp/out.py", "content": "line1\nline2\nline3"})
        output = capsys.readouterr().out
        assert "Write" in output
        assert "out.py" in output
        assert "3" in output  # line count

    def test_edit_tool_call(self, tui, capsys):
        tui.show_tool_call("Edit", {
            "file_path": "/tmp/edit.py",
            "old_string": "old code",
            "new_string": "new code",
        })
        output = capsys.readouterr().out
        assert "Edit" in output
        assert "old code" in output
        assert "new code" in output

    def test_glob_tool_call(self, tui, capsys):
        tui.show_tool_call("Glob", {"pattern": "**/*.py", "path": "/tmp"})
        output = capsys.readouterr().out
        assert "Glob" in output
        assert "**/*.py" in output

    def test_grep_tool_call(self, tui, capsys):
        tui.show_tool_call("Grep", {"pattern": "TODO"})
        output = capsys.readouterr().out
        assert "Grep" in output
        assert "TODO" in output

    def test_webfetch_tool_call(self, tui, capsys):
        tui.show_tool_call("WebFetch", {"url": "https://example.com"})
        output = capsys.readouterr().out
        assert "WebFetch" in output
        assert "example.com" in output

    def test_websearch_tool_call(self, tui, capsys):
        tui.show_tool_call("WebSearch", {"query": "python tutorial"})
        output = capsys.readouterr().out
        assert "WebSearch" in output
        assert "python tutorial" in output

    def test_unknown_tool_call(self, tui, capsys):
        tui.show_tool_call("CustomTool", {"foo": "bar"})
        output = capsys.readouterr().out
        assert "CustomTool" in output

    def test_long_command_truncation(self, tui, capsys):
        """Long bash commands should be truncated."""
        long_cmd = "x" * 200
        tui.show_tool_call("Bash", {"command": long_cmd})
        output = capsys.readouterr().out
        assert "..." in output


# ══════════════════════════════════════════════════════════════════════════════
# 5. TUI.show_tool_result()
# ══════════════════════════════════════════════════════════════════════════════

class TestShowToolResult:
    """Test show_tool_result formatting."""

    def test_success_result(self, tui, capsys):
        tui.show_tool_result("Bash", "line1\nline2\nline3", is_error=False)
        output = capsys.readouterr().out
        assert "Bash" in output
        assert "3 lines" in output

    def test_error_result(self, tui, capsys):
        tui.show_tool_result("Bash", "command not found", is_error=True)
        output = capsys.readouterr().out
        assert "Bash" in output
        assert "command not found" in output

    def test_result_with_duration(self, tui, capsys):
        tui.show_tool_result("Read", "content here", duration=1.5)
        output = capsys.readouterr().out
        assert "1.5s" in output

    def test_result_with_params(self, tui, capsys):
        tui.show_tool_result("Read", "file content", params={"file_path": "/tmp/test.py"})
        output = capsys.readouterr().out
        assert "test.py" in output

    def test_write_result_ok(self, tui, capsys):
        tui.show_tool_result("Write", "File written", is_error=False)
        output = capsys.readouterr().out
        assert "Write" in output

    def test_multiline_result_truncates(self, tui, capsys):
        """Results with many lines should show limited detail."""
        lines = "\n".join([f"line {i}" for i in range(20)])
        tui.show_tool_result("Bash", lines, is_error=False)
        output = capsys.readouterr().out
        assert "more lines" in output


# ══════════════════════════════════════════════════════════════════════════════
# 6. TUI._render_markdown() / _render_md_line()
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkdownRendering:
    """Test markdown rendering methods."""

    def test_render_header_h1(self, tui, capsys):
        tui._render_markdown("# Hello World")
        output = capsys.readouterr().out
        assert "Hello World" in output

    def test_render_header_h2(self, tui, capsys):
        tui._render_markdown("## Section")
        output = capsys.readouterr().out
        assert "Section" in output

    def test_render_header_h3(self, tui, capsys):
        tui._render_markdown("### Subsection")
        output = capsys.readouterr().out
        assert "Subsection" in output

    def test_render_code_block(self, tui, capsys):
        tui._render_markdown("```python\nprint('hello')\n```")
        output = capsys.readouterr().out
        assert "print('hello')" in output

    def test_render_unordered_list(self, tui, capsys):
        tui._render_markdown("- item one\n- item two")
        output = capsys.readouterr().out
        assert "item one" in output
        assert "item two" in output

    def test_render_ordered_list(self, tui, capsys):
        tui._render_markdown("1. first\n2. second")
        output = capsys.readouterr().out
        assert "first" in output
        assert "second" in output

    def test_render_blockquote(self, tui, capsys):
        tui._render_markdown("> This is a quote")
        output = capsys.readouterr().out
        assert "This is a quote" in output

    def test_render_table(self, tui, capsys):
        tui._render_markdown("| Name | Value |\n|------|-------|\n| foo  | bar   |")
        output = capsys.readouterr().out
        assert "Name" in output
        assert "foo" in output
        assert "bar" in output

    def test_render_horizontal_rule(self, tui, capsys):
        tui._render_markdown("---")
        output = capsys.readouterr().out
        # Should render as separator line
        assert len(output.strip()) > 0

    def test_render_plain_text(self, tui, capsys):
        tui._render_markdown("Just some plain text")
        output = capsys.readouterr().out
        assert "Just some plain text" in output


# ══════════════════════════════════════════════════════════════════════════════
# 7. TUI._apply_inline_md()
# ══════════════════════════════════════════════════════════════════════════════

class TestInlineMarkdown:
    """Test inline markdown formatting."""

    def test_inline_code(self, tui):
        result = TUI._apply_inline_md("Use `foo()` here")
        assert "foo()" in result

    def test_bold(self, tui):
        result = TUI._apply_inline_md("This is **bold**")
        assert "bold" in result

    def test_italic(self, tui):
        result = TUI._apply_inline_md("This is *italic*")
        assert "italic" in result

    def test_link(self, tui):
        result = TUI._apply_inline_md("[Click](https://example.com)")
        assert "Click" in result
        assert "example.com" in result

    def test_no_markdown(self, tui):
        result = TUI._apply_inline_md("plain text")
        assert result == "plain text"


# ══════════════════════════════════════════════════════════════════════════════
# 8. TUI._has_markdown_syntax()
# ══════════════════════════════════════════════════════════════════════════════

class TestHasMarkdownSyntax:
    """Test markdown syntax detection."""

    def test_code_block(self):
        assert TUI._has_markdown_syntax("```\ncode\n```") is True

    def test_heading(self):
        assert TUI._has_markdown_syntax("# Title") is True

    def test_bold(self):
        assert TUI._has_markdown_syntax("**bold**") is True

    def test_inline_code(self):
        assert TUI._has_markdown_syntax("`code`") is True

    def test_table(self):
        assert TUI._has_markdown_syntax("| a | b |") is True

    def test_list(self):
        assert TUI._has_markdown_syntax("- item") is True

    def test_ordered_list(self):
        assert TUI._has_markdown_syntax("1. item") is True

    def test_blockquote(self):
        assert TUI._has_markdown_syntax("> quote") is True

    def test_plain_text(self):
        assert TUI._has_markdown_syntax("just text") is False

    def test_empty_string(self):
        assert TUI._has_markdown_syntax("") is False


# ══════════════════════════════════════════════════════════════════════════════
# 9. ScrollRegion
# ══════════════════════════════════════════════════════════════════════════════

class TestScrollRegion:
    """Test ScrollRegion state management."""

    def test_initial_state(self):
        sr = ScrollRegion()
        assert sr._active is False
        assert sr._rows == 0
        assert sr._cols == 0
        assert sr._status_text == ""
        assert sr._hint_text == ""

    def test_update_status(self):
        sr = ScrollRegion()
        sr.update_status("test status")
        assert sr._status_text == "test status"

    def test_update_hint(self):
        sr = ScrollRegion()
        sr.update_hint("type-ahead text")
        assert sr._hint_text == "type-ahead text"

    def test_clear_status(self):
        sr = ScrollRegion()
        sr.update_status("something")
        sr.clear_status()
        assert sr._status_text == ""

    def test_supported_non_tty(self):
        """ScrollRegion.supported() returns False when not a TTY."""
        sr = ScrollRegion()
        # In test environment, stdout is usually not a TTY
        if not sys.stdout.isatty():
            assert sr.supported() is False

    def test_supported_with_env_override(self):
        """VIBE_NO_SCROLL=1 disables scroll region."""
        sr = ScrollRegion()
        old_val = os.environ.get("VIBE_NO_SCROLL")
        os.environ["VIBE_NO_SCROLL"] = "1"
        try:
            assert sr.supported() is False
        finally:
            if old_val is None:
                del os.environ["VIBE_NO_SCROLL"]
            else:
                os.environ["VIBE_NO_SCROLL"] = old_val

    def test_setup_activates_with_sufficient_rows(self):
        """setup() activates when terminal size is sufficient (>= 10 rows)."""
        sr = ScrollRegion()
        sr.setup()  # Uses default terminal size (80x24) which is >= 10
        # Teardown to restore terminal state
        if sr._active:
            sr.teardown()
        # Just verify it doesn't crash; actual activation depends on shutil.get_terminal_size

    def test_teardown_noop_when_inactive(self):
        """teardown() should be safe to call when inactive."""
        sr = ScrollRegion()
        sr.teardown()  # Should not crash
        assert sr._active is False

    def test_status_rows_constant(self):
        sr = ScrollRegion()
        assert sr.STATUS_ROWS == 3

    def test_thread_safety_of_status_updates(self):
        """Multiple threads updating status should not crash."""
        sr = ScrollRegion()
        errors = []

        def updater(n):
            try:
                for i in range(50):
                    sr.update_status(f"thread-{n}-iter-{i}")
                    sr.update_hint(f"hint-{n}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=updater, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_print_output_when_inactive(self, capsys):
        """print_output() falls back to normal print when inactive."""
        sr = ScrollRegion()
        sr.print_output("test text")
        output = capsys.readouterr().out
        assert "test text" in output


# ══════════════════════════════════════════════════════════════════════════════
# 10. TUI.spinner
# ══════════════════════════════════════════════════════════════════════════════

class TestSpinner:
    """Test spinner start/stop."""

    def test_spinner_noop_when_not_interactive(self, tui):
        """start_spinner does nothing if not interactive."""
        tui.is_interactive = False
        tui.start_spinner("test")
        assert tui._spinner_thread is None
        tui.stop_spinner()

    def test_stop_spinner_safe_when_not_started(self, tui):
        """stop_spinner should not crash when no spinner is running."""
        tui.stop_spinner()  # No-op, should not raise


# ══════════════════════════════════════════════════════════════════════════════
# 11. TUI._detect_cjk_locale()
# ══════════════════════════════════════════════════════════════════════════════

class TestCJKDetection:
    """Test CJK locale detection."""

    def test_cjk_returns_bool(self, tui):
        """_detect_cjk_locale should return a boolean."""
        result = tui._detect_cjk_locale()
        assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════════════
# 12. TUI._tool_icons()
# ══════════════════════════════════════════════════════════════════════════════

class TestToolIcons:
    """Test tool icons mapping."""

    def test_has_core_tools(self):
        icons = TUI._tool_icons()
        for tool_name in ["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "WebFetch", "WebSearch", "NotebookEdit", "SubAgent"]:
            assert tool_name in icons, f"Missing icon for {tool_name}"

    def test_icon_format(self):
        """Each icon entry should be (icon_char, color_string) tuple."""
        icons = TUI._tool_icons()
        for name, (icon, color) in icons.items():
            assert isinstance(icon, str), f"{name} icon should be a string"
            assert isinstance(color, str), f"{name} color should be a string"


# ══════════════════════════════════════════════════════════════════════════════
# 13. TUI.show_sync_response()
# ══════════════════════════════════════════════════════════════════════════════

class TestShowSyncResponse:
    """Test sync response display."""

    def test_text_response(self, tui, capsys):
        data = {
            "choices": [{
                "message": {
                    "content": "Hello from the assistant",
                    "tool_calls": [],
                }
            }]
        }
        text, tool_calls = tui.show_sync_response(data)
        assert "Hello from the assistant" in text
        assert tool_calls == []
        output = capsys.readouterr().out
        assert "Hello from the assistant" in output

    def test_empty_response(self, tui, capsys):
        data = {"choices": [{"message": {"content": "", "tool_calls": []}}]}
        text, tool_calls = tui.show_sync_response(data)
        assert text == ""
        assert tool_calls == []

    def test_think_tags_stripped(self, tui, capsys):
        data = {
            "choices": [{
                "message": {
                    "content": "<think>internal reasoning</think>Visible text",
                    "tool_calls": [],
                }
            }]
        }
        text, tool_calls = tui.show_sync_response(data)
        assert "internal reasoning" not in text
        assert "Visible text" in text

    def test_tool_calls_returned(self, tui, capsys):
        data = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "Bash", "arguments": '{"command":"ls"}'},
                        }
                    ],
                }
            }]
        }
        text, tool_calls = tui.show_sync_response(data)
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "Bash"


# ══════════════════════════════════════════════════════════════════════════════
# 14. ANSI color system (C class)
# ══════════════════════════════════════════════════════════════════════════════

class TestColorSystem:
    """Test the C color class."""

    def test_disable_clears_codes(self):
        """C.disable() should set all codes to empty strings."""
        # Already disabled by autouse fixture
        assert C.RESET == ""
        assert C.BOLD == ""
        assert C.RED == ""

    def test_enabled_flag(self):
        """After disable, _enabled should be False."""
        assert C._enabled is False


# ══════════════════════════════════════════════════════════════════════════════
# 15. Helper functions
# ══════════════════════════════════════════════════════════════════════════════

class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_ansi_disabled(self):
        """_ansi() should return empty string when colors disabled."""
        _ansi = co_vibe._ansi
        result = _ansi("\033[38;5;51m")
        assert result == ""

    def test_get_terminal_width(self):
        """_get_terminal_width() should return a positive integer."""
        width = co_vibe._get_terminal_width()
        assert isinstance(width, int)
        assert width > 0

    def test_display_width_ascii(self):
        """_display_width for ASCII text equals len."""
        width = co_vibe._display_width("hello")
        assert width == 5

    def test_display_width_cjk(self):
        """CJK characters should count as double width."""
        width = co_vibe._display_width("AB")
        assert width == 2
        cjk_width = co_vibe._display_width("漢字")
        assert cjk_width == 4  # Each CJK char is 2 display columns

    def test_truncate_to_display_width(self):
        """_truncate_to_display_width should respect max width."""
        truncated = co_vibe._truncate_to_display_width("a" * 100, 10)
        assert len(truncated) <= 13  # 10 + "..."
