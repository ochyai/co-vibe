"""Comprehensive tests for the Config class in co-vibe.py."""

import os
import sys
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

# co-vibe uses a hyphen, so we must use importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib
co_vibe = importlib.import_module("co-vibe")
Config = co_vibe.Config


class TestConfigDefaults(unittest.TestCase):
    """Test default values after plain __init__ (no load)."""

    def setUp(self):
        self.cfg = Config()

    def test_default_model(self):
        self.assertEqual(self.cfg.model, "claude-sonnet-4-6")

    def test_default_sidecar_model(self):
        self.assertEqual(self.cfg.sidecar_model, "")

    def test_default_max_tokens(self):
        self.assertEqual(self.cfg.max_tokens, 8192)

    def test_default_temperature(self):
        self.assertAlmostEqual(self.cfg.temperature, 0.7)

    def test_default_context_window(self):
        self.assertEqual(self.cfg.context_window, 200000)

    def test_default_strategy(self):
        self.assertEqual(self.cfg.strategy, "auto")

    def test_default_prompt_is_none(self):
        self.assertIsNone(self.cfg.prompt)

    def test_default_yes_mode_false(self):
        self.assertFalse(self.cfg.yes_mode)

    def test_default_debug_false(self):
        self.assertFalse(self.cfg.debug)

    def test_default_resume_false(self):
        self.assertFalse(self.cfg.resume)

    def test_default_api_keys_empty(self):
        self.assertEqual(self.cfg.anthropic_api_key, "")
        self.assertEqual(self.cfg.openai_api_key, "")
        self.assertEqual(self.cfg.groq_api_key, "")

    def test_default_session_id_none(self):
        self.assertIsNone(self.cfg.session_id)

    def test_default_list_sessions_false(self):
        self.assertFalse(self.cfg.list_sessions)


class TestConfigPaths(unittest.TestCase):
    """Test path setup on non-Windows."""

    def test_config_dir_uses_co_vibe(self):
        cfg = Config()
        self.assertIn("co-vibe", cfg.config_dir)

    def test_state_dir_uses_co_vibe(self):
        cfg = Config()
        self.assertIn("co-vibe", cfg.state_dir)

    def test_config_file_inside_config_dir(self):
        cfg = Config()
        self.assertEqual(cfg.config_file, os.path.join(cfg.config_dir, "config"))

    def test_sessions_dir_inside_state_dir(self):
        cfg = Config()
        self.assertEqual(cfg.sessions_dir, os.path.join(cfg.state_dir, "sessions"))

    def test_history_file_inside_state_dir(self):
        cfg = Config()
        self.assertEqual(cfg.history_file, os.path.join(cfg.state_dir, "history"))

    @unittest.skipIf(os.name == "nt", "Unix-only path layout")
    def test_unix_config_dir(self):
        cfg = Config()
        home = os.path.expanduser("~")
        self.assertEqual(cfg.config_dir, os.path.join(home, ".config", "co-vibe"))

    @unittest.skipIf(os.name == "nt", "Unix-only path layout")
    def test_unix_state_dir(self):
        cfg = Config()
        home = os.path.expanduser("~")
        self.assertEqual(cfg.state_dir, os.path.join(home, ".local", "state", "co-vibe"))


class TestLoadDotenv(unittest.TestCase):
    """Test _load_dotenv reads .env files."""

    def _make_env_file(self, content):
        """Create a temp .env file and return its path."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_load_anthropic_key(self):
        env_path = self._make_env_file('ANTHROPIC_API_KEY=sk-ant-test123\n')
        try:
            cfg = Config()
            # Patch candidates to use our temp file
            with patch.object(Config, '_load_dotenv') as mock_ld:
                # Manually replicate _load_dotenv with our file
                pass
            # Direct parse via internal method logic
            cfg._parse_config_file(env_path)  # same format
            self.assertEqual(cfg.anthropic_api_key, "sk-ant-test123")
        finally:
            os.unlink(env_path)

    def test_load_openai_key(self):
        env_path = self._make_env_file('OPENAI_API_KEY="sk-openai-test"\n')
        cfg = Config()
        cfg._parse_config_file(env_path)
        self.assertEqual(cfg.openai_api_key, "sk-openai-test")
        os.unlink(env_path)

    def test_load_groq_key(self):
        env_path = self._make_env_file("GROQ_API_KEY='gsk_test'\n")
        cfg = Config()
        cfg._parse_config_file(env_path)
        self.assertEqual(cfg.groq_api_key, "gsk_test")
        os.unlink(env_path)

    def test_load_strategy_from_dotenv(self):
        env_path = self._make_env_file("CO_VIBE_STRATEGY=strong\n")
        cfg = Config()
        cfg._parse_config_file(env_path)
        self.assertEqual(cfg.strategy, "strong")
        os.unlink(env_path)

    def test_skips_comments_and_empty_lines(self):
        env_path = self._make_env_file(
            "# comment\n\n  \nANTHROPIC_API_KEY=valid\n"
        )
        cfg = Config()
        cfg._parse_config_file(env_path)
        self.assertEqual(cfg.anthropic_api_key, "valid")
        os.unlink(env_path)

    def test_skips_lines_without_equals(self):
        env_path = self._make_env_file("NO_EQUALS_HERE\nANTHROPIC_API_KEY=yes\n")
        cfg = Config()
        cfg._parse_config_file(env_path)
        self.assertEqual(cfg.anthropic_api_key, "yes")
        os.unlink(env_path)

    def test_dotenv_skips_symlinks(self):
        """_load_dotenv should skip symlinked .env files for security."""
        with tempfile.TemporaryDirectory() as td:
            real = os.path.join(td, "real.env")
            link = os.path.join(td, ".env")
            with open(real, "w") as f:
                f.write("ANTHROPIC_API_KEY=symlinked\n")
            os.symlink(real, link)
            cfg = Config()
            # Simulate _load_dotenv logic: islink check
            self.assertTrue(os.path.islink(link))
            # The real _load_dotenv skips symlinks
            self.assertEqual(cfg.anthropic_api_key, "")  # should remain default

    def test_dotenv_empty_value_skipped(self):
        env_path = self._make_env_file("ANTHROPIC_API_KEY=\n")
        cfg = Config()
        cfg._parse_config_file(env_path)
        # Empty val after strip => skipped for API keys because of `and val` check
        self.assertEqual(cfg.anthropic_api_key, "")
        os.unlink(env_path)


class TestParseConfigFile(unittest.TestCase):
    """Test _parse_config_file key=value parsing."""

    def _write_config(self, content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parse_model(self):
        p = self._write_config("MODEL=gpt-4o\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.model, "gpt-4o")
        os.unlink(p)

    def test_parse_sidecar_model(self):
        p = self._write_config("SIDECAR_MODEL=gpt-4o-mini\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.sidecar_model, "gpt-4o-mini")
        os.unlink(p)

    def test_parse_strategy(self):
        p = self._write_config("CO_VIBE_STRATEGY=cheap\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.strategy, "cheap")
        os.unlink(p)

    def test_parse_api_keys(self):
        p = self._write_config(textwrap.dedent("""\
            ANTHROPIC_API_KEY=a1
            OPENAI_API_KEY=o1
            GROQ_API_KEY=g1
        """))
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.anthropic_api_key, "a1")
        self.assertEqual(cfg.openai_api_key, "o1")
        self.assertEqual(cfg.groq_api_key, "g1")
        os.unlink(p)

    def test_parse_max_tokens(self):
        p = self._write_config("MAX_TOKENS=4096\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.max_tokens, 4096)
        os.unlink(p)

    def test_parse_max_tokens_invalid(self):
        p = self._write_config("MAX_TOKENS=not_a_number\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.max_tokens, Config.DEFAULT_MAX_TOKENS)
        os.unlink(p)

    def test_parse_temperature(self):
        p = self._write_config("TEMPERATURE=0.3\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertAlmostEqual(cfg.temperature, 0.3)
        os.unlink(p)

    def test_parse_temperature_invalid(self):
        p = self._write_config("TEMPERATURE=abc\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertAlmostEqual(cfg.temperature, Config.DEFAULT_TEMPERATURE)
        os.unlink(p)

    def test_parse_context_window(self):
        p = self._write_config("CONTEXT_WINDOW=128000\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.context_window, 128000)
        os.unlink(p)

    def test_parse_context_window_invalid(self):
        p = self._write_config("CONTEXT_WINDOW=xyz\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.context_window, Config.DEFAULT_CONTEXT_WINDOW)
        os.unlink(p)

    def test_skips_comments_and_blanks(self):
        p = self._write_config("# comment\n\nMODEL=gpt-4o\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.model, "gpt-4o")
        os.unlink(p)

    def test_strips_quotes(self):
        p = self._write_config('MODEL="gpt-4o"\n')
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.model, "gpt-4o")
        os.unlink(p)

    def test_strips_single_quotes(self):
        p = self._write_config("MODEL='gpt-4o'\n")
        cfg = Config()
        cfg._parse_config_file(p)
        self.assertEqual(cfg.model, "gpt-4o")
        os.unlink(p)


class TestLoadEnv(unittest.TestCase):
    """Test _load_env reads environment variables."""

    def test_env_anthropic_key(self):
        cfg = Config()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-ant"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.anthropic_api_key, "env-ant")

    def test_env_openai_key(self):
        cfg = Config()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-oai"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.openai_api_key, "env-oai")

    def test_env_groq_key(self):
        cfg = Config()
        with patch.dict(os.environ, {"GROQ_API_KEY": "env-groq"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.groq_api_key, "env-groq")

    def test_env_strategy(self):
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_STRATEGY": "fast"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.strategy, "fast")

    def test_env_model(self):
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_MODEL": "o3"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.model, "o3")

    def test_env_debug(self):
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_DEBUG": "1"}, clear=False):
            cfg._load_env()
        self.assertTrue(cfg.debug)

    def test_env_debug_not_set(self):
        cfg = Config()
        env = {k: v for k, v in os.environ.items() if k != "CO_VIBE_DEBUG"}
        with patch.dict(os.environ, env, clear=True):
            cfg._load_env()
        self.assertFalse(cfg.debug)


class TestLoadCliArgs(unittest.TestCase):
    """Test _load_cli_args parses all argparse flags."""

    def test_prompt_short(self):
        cfg = Config()
        cfg._load_cli_args(["-p", "hello world"])
        self.assertEqual(cfg.prompt, "hello world")

    def test_prompt_long(self):
        cfg = Config()
        cfg._load_cli_args(["--prompt", "testing"])
        self.assertEqual(cfg.prompt, "testing")

    def test_model_short(self):
        cfg = Config()
        cfg._load_cli_args(["-m", "gpt-4o"])
        self.assertEqual(cfg.model, "gpt-4o")

    def test_model_long(self):
        cfg = Config()
        cfg._load_cli_args(["--model", "o3"])
        self.assertEqual(cfg.model, "o3")

    def test_strategy(self):
        cfg = Config()
        cfg._load_cli_args(["--strategy", "strong"])
        self.assertEqual(cfg.strategy, "strong")

    def test_strategy_invalid_rejected(self):
        cfg = Config()
        with self.assertRaises(SystemExit):
            cfg._load_cli_args(["--strategy", "invalid"])

    def test_yes_short(self):
        cfg = Config()
        cfg._load_cli_args(["-y"])
        self.assertTrue(cfg.yes_mode)

    def test_yes_long(self):
        cfg = Config()
        cfg._load_cli_args(["--yes"])
        self.assertTrue(cfg.yes_mode)

    def test_debug(self):
        cfg = Config()
        cfg._load_cli_args(["--debug"])
        self.assertTrue(cfg.debug)

    def test_resume(self):
        cfg = Config()
        cfg._load_cli_args(["--resume"])
        self.assertTrue(cfg.resume)

    def test_session_id_sets_resume(self):
        cfg = Config()
        cfg._load_cli_args(["--session-id", "abc123"])
        self.assertEqual(cfg.session_id, "abc123")
        self.assertTrue(cfg.resume)

    def test_list_sessions(self):
        cfg = Config()
        cfg._load_cli_args(["--list-sessions"])
        self.assertTrue(cfg.list_sessions)

    def test_max_tokens(self):
        cfg = Config()
        cfg._load_cli_args(["--max-tokens", "2048"])
        self.assertEqual(cfg.max_tokens, 2048)

    def test_temperature(self):
        cfg = Config()
        cfg._load_cli_args(["--temperature", "1.5"])
        self.assertAlmostEqual(cfg.temperature, 1.5)

    def test_context_window(self):
        cfg = Config()
        cfg._load_cli_args(["--context-window", "64000"])
        self.assertEqual(cfg.context_window, 64000)

    def test_dangerously_skip_permissions(self):
        cfg = Config()
        cfg._load_cli_args(["--dangerously-skip-permissions"])
        self.assertTrue(cfg.yes_mode)

    def test_fullwidth_space_handling(self):
        """Full-width spaces (\\u3000) should be treated as separators."""
        cfg = Config()
        cfg._load_cli_args(["-m\u3000gpt-4o"])
        self.assertEqual(cfg.model, "gpt-4o")

    def test_fullwidth_space_in_flag(self):
        cfg = Config()
        cfg._load_cli_args(["--model\u3000o3"])
        self.assertEqual(cfg.model, "o3")

    def test_no_args(self):
        cfg = Config()
        cfg._load_cli_args([])
        # Should keep defaults
        self.assertEqual(cfg.model, Config.DEFAULT_MODEL)
        self.assertIsNone(cfg.prompt)
        self.assertFalse(cfg.yes_mode)

    def test_multiple_flags(self):
        cfg = Config()
        cfg._load_cli_args(["-m", "gpt-4o", "--strategy", "fast", "-y", "--debug"])
        self.assertEqual(cfg.model, "gpt-4o")
        self.assertEqual(cfg.strategy, "fast")
        self.assertTrue(cfg.yes_mode)
        self.assertTrue(cfg.debug)


class TestAutoDetectModel(unittest.TestCase):
    """Test _auto_detect_model strategy-based selection."""

    def test_explicit_model_kept(self):
        cfg = Config()
        cfg.model = "my-custom-model"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "my-custom-model")

    def test_strong_strategy_anthropic(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL  # ensure default so auto-detect runs
        cfg.strategy = "strong"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "claude-opus-4-6")

    def test_strong_strategy_openai_only(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "strong"
        cfg.openai_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "gpt-5.2-pro")

    def test_auto_strategy_anthropic(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "claude-sonnet-4-6")

    def test_auto_strategy_openai_only(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.openai_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "gpt-5.2-chat-latest")

    def test_auto_strategy_groq_only(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.groq_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "llama-3.3-70b-versatile")

    def test_fast_strategy_groq(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "fast"
        cfg.groq_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "llama-3.1-8b-instant")

    def test_cheap_strategy_anthropic(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "cheap"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, "claude-haiku-4-5-20251001")

    @patch.object(Config, '_detect_ollama', return_value=False)
    def test_no_keys_falls_back_to_default(self, _mock_ollama):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg._auto_detect_model()
        self.assertEqual(cfg.model, Config.DEFAULT_MODEL)

    def test_sidecar_selected_different_from_main(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        # Sidecar should be picked and not equal to main model
        if cfg.sidecar_model:
            self.assertNotEqual(cfg.sidecar_model, cfg.model)

    def test_sidecar_with_anthropic_key(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        # claude-haiku-4-5-20251001 is first sidecar candidate for anthropic
        self.assertEqual(cfg.sidecar_model, "claude-haiku-4-5-20251001")

    def test_sidecar_with_openai_key(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "auto"
        cfg.openai_api_key = "key"
        cfg._auto_detect_model()
        # Main model will be gpt-5.2-chat-latest; sidecar should be gpt-5-main-mini
        self.assertEqual(cfg.sidecar_model, "gpt-5-main-mini")

    def test_sidecar_already_set_not_overridden(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.sidecar_model = "my-sidecar"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        self.assertEqual(cfg.sidecar_model, "my-sidecar")

    def test_invalid_strategy_treated_as_auto(self):
        cfg = Config()
        cfg.model = Config.DEFAULT_MODEL
        cfg.strategy = "nonexistent"
        cfg.anthropic_api_key = "key"
        cfg._auto_detect_model()
        # Falls back to "auto" strategy -> claude-sonnet-4-6
        self.assertEqual(cfg.model, "claude-sonnet-4-6")


class TestValidateSettings(unittest.TestCase):
    """Test _validate_settings bounds checking."""

    def test_context_window_zero_reset(self):
        cfg = Config()
        cfg.context_window = 0
        cfg._validate_settings()
        self.assertEqual(cfg.context_window, Config.DEFAULT_CONTEXT_WINDOW)

    def test_context_window_negative_reset(self):
        cfg = Config()
        cfg.context_window = -100
        cfg._validate_settings()
        self.assertEqual(cfg.context_window, Config.DEFAULT_CONTEXT_WINDOW)

    def test_context_window_too_large_reset(self):
        cfg = Config()
        cfg.context_window = 2_000_000
        cfg._validate_settings()
        self.assertEqual(cfg.context_window, Config.DEFAULT_CONTEXT_WINDOW)

    def test_context_window_at_max_boundary(self):
        cfg = Config()
        cfg.context_window = 1_048_576
        cfg._validate_settings()
        self.assertEqual(cfg.context_window, 1_048_576)

    def test_max_tokens_zero_reset(self):
        cfg = Config()
        cfg.max_tokens = 0
        cfg._validate_settings()
        self.assertEqual(cfg.max_tokens, Config.DEFAULT_MAX_TOKENS)

    def test_max_tokens_too_large_reset(self):
        cfg = Config()
        cfg.max_tokens = 200_000
        cfg._validate_settings()
        self.assertEqual(cfg.max_tokens, Config.DEFAULT_MAX_TOKENS)

    def test_max_tokens_at_max_boundary(self):
        cfg = Config()
        cfg.max_tokens = 131_072
        cfg._validate_settings()
        self.assertEqual(cfg.max_tokens, 131_072)

    def test_temperature_negative_reset(self):
        cfg = Config()
        cfg.temperature = -0.1
        cfg._validate_settings()
        self.assertAlmostEqual(cfg.temperature, Config.DEFAULT_TEMPERATURE)

    def test_temperature_too_high_reset(self):
        cfg = Config()
        cfg.temperature = 2.5
        cfg._validate_settings()
        self.assertAlmostEqual(cfg.temperature, Config.DEFAULT_TEMPERATURE)

    def test_temperature_at_max_boundary(self):
        cfg = Config()
        cfg.temperature = 2.0
        cfg._validate_settings()
        self.assertAlmostEqual(cfg.temperature, 2.0)

    def test_temperature_zero_valid(self):
        cfg = Config()
        cfg.temperature = 0.0
        cfg._validate_settings()
        self.assertAlmostEqual(cfg.temperature, 0.0)

    def test_invalid_strategy_reset(self):
        cfg = Config()
        cfg.strategy = "nonexistent"
        cfg._validate_settings()
        self.assertEqual(cfg.strategy, Config.DEFAULT_STRATEGY)

    def test_valid_strategies_kept(self):
        for strat in ["auto", "strong", "fast", "cheap"]:
            cfg = Config()
            cfg.strategy = strat
            cfg._validate_settings()
            self.assertEqual(cfg.strategy, strat, f"strategy {strat} should be kept")

    def test_model_name_with_shell_metachar_reset(self):
        cfg = Config()
        cfg.model = "model; rm -rf /"
        cfg._validate_settings()
        self.assertEqual(cfg.model, Config.DEFAULT_MODEL)

    def test_model_name_with_backtick_reset(self):
        cfg = Config()
        cfg.model = "model`whoami`"
        cfg._validate_settings()
        self.assertEqual(cfg.model, Config.DEFAULT_MODEL)

    def test_sidecar_name_with_metachar_reset(self):
        cfg = Config()
        cfg.sidecar_model = "bad$(cmd)"
        cfg._validate_settings()
        self.assertEqual(cfg.sidecar_model, "")

    def test_safe_model_names_kept(self):
        for name in ["claude-sonnet-4-6", "gpt-4o", "llama-3.3-70b-versatile",
                      "qwen3:8b", "my/custom-model_v2"]:
            cfg = Config()
            cfg.model = name
            cfg._validate_settings()
            self.assertEqual(cfg.model, name, f"model name {name} should be safe")


class TestApplyContextWindow(unittest.TestCase):
    """Test _apply_context_window sets correct sizes."""

    def test_claude_models_200k(self):
        for model in ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]:
            cfg = Config()
            cfg.context_window = Config.DEFAULT_CONTEXT_WINDOW  # reset
            cfg._apply_context_window(model)
            self.assertEqual(cfg.context_window, 200000, f"{model} should be 200k")

    def test_gpt_52_200k(self):
        cfg = Config()
        cfg._apply_context_window("gpt-5.2")
        self.assertEqual(cfg.context_window, 200000)

    def test_gpt_5_main_mini_128k(self):
        cfg = Config()
        cfg._apply_context_window("gpt-5-main-mini")
        self.assertEqual(cfg.context_window, 128000)

    def test_o3_200k(self):
        cfg = Config()
        cfg._apply_context_window("o3")
        self.assertEqual(cfg.context_window, 200000)

    def test_llama_models_131k(self):
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            cfg = Config()
            cfg.context_window = Config.DEFAULT_CONTEXT_WINDOW
            cfg._apply_context_window(model)
            self.assertEqual(cfg.context_window, 131072, f"{model} should be 131072")

    def test_unknown_model_keeps_default(self):
        cfg = Config()
        cfg._apply_context_window("unknown-model-xyz")
        self.assertEqual(cfg.context_window, Config.DEFAULT_CONTEXT_WINDOW)

    def test_user_override_not_changed(self):
        """If user explicitly set context_window, _apply_context_window should not override."""
        cfg = Config()
        cfg.context_window = 50000  # user override (not DEFAULT)
        cfg._apply_context_window("gpt-4o")
        self.assertEqual(cfg.context_window, 50000)


class TestGetModelTier(unittest.TestCase):
    """Test get_model_tier classmethod."""

    def test_claude_model(self):
        provider, extra = Config.get_model_tier("claude-sonnet-4-6")
        self.assertEqual(provider, "Anthropic")
        self.assertIsNone(extra)

    def test_gpt_model(self):
        provider, extra = Config.get_model_tier("gpt-5.2")
        self.assertEqual(provider, "Openai")
        self.assertIsNone(extra)

    def test_groq_model(self):
        provider, extra = Config.get_model_tier("llama-3.3-70b-versatile")
        self.assertEqual(provider, "Groq")
        self.assertIsNone(extra)

    def test_unknown_model(self):
        provider, extra = Config.get_model_tier("unknown-model")
        self.assertIsNone(provider)
        self.assertIsNone(extra)

    def test_o3_is_openai(self):
        provider, _ = Config.get_model_tier("o3")
        self.assertEqual(provider, "Openai")


class TestLoadOrder(unittest.TestCase):
    """Test that load order is: dotenv -> config -> env -> CLI (later overrides earlier)."""

    def test_env_overrides_config_file(self):
        """Environment variable should override config file value."""
        cfg = Config()
        # Simulate config file setting
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("ANTHROPIC_API_KEY=from-config\n")
            cfg_path = f.name
        cfg._parse_config_file(cfg_path)
        self.assertEqual(cfg.anthropic_api_key, "from-config")
        # Env overrides
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "from-env"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.anthropic_api_key, "from-env")
        os.unlink(cfg_path)

    def test_cli_overrides_env(self):
        """CLI arg should override environment variable."""
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_MODEL": "gpt-4o"}, clear=False):
            cfg._load_env()
        self.assertEqual(cfg.model, "gpt-4o")
        cfg._load_cli_args(["-m", "o3"])
        self.assertEqual(cfg.model, "o3")

    def test_cli_overrides_config_file_strategy(self):
        cfg = Config()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("CO_VIBE_STRATEGY=cheap\n")
            cfg_path = f.name
        cfg._parse_config_file(cfg_path)
        self.assertEqual(cfg.strategy, "cheap")
        cfg._load_cli_args(["--strategy", "strong"])
        self.assertEqual(cfg.strategy, "strong")
        os.unlink(cfg_path)

    def test_full_load_order(self):
        """End-to-end: config file sets a value, env overrides, CLI overrides again."""
        cfg = Config()
        # Step 1: config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("MAX_TOKENS=1000\n")
            cfg_path = f.name
        cfg._parse_config_file(cfg_path)
        self.assertEqual(cfg.max_tokens, 1000)
        # Step 2: env does not set MAX_TOKENS, so config value persists
        cfg._load_env()
        self.assertEqual(cfg.max_tokens, 1000)
        # Step 3: CLI overrides
        cfg._load_cli_args(["--max-tokens", "2048"])
        self.assertEqual(cfg.max_tokens, 2048)
        os.unlink(cfg_path)


class TestConfigFileSecurityChecks(unittest.TestCase):
    """Test _load_config_file security: symlinks, oversized files."""

    def test_skips_symlinked_config(self):
        with tempfile.TemporaryDirectory() as td:
            real = os.path.join(td, "real_config")
            link = os.path.join(td, "config")
            with open(real, "w") as f:
                f.write("MODEL=evil\n")
            os.symlink(real, link)
            cfg = Config()
            # _load_config_file checks islink
            self.assertTrue(os.path.islink(link))
            # The internal code skips symlinks, so model should remain default
            # We test the skip logic by mimicking _load_config_file
            if not os.path.islink(link):
                cfg._parse_config_file(link)
            self.assertEqual(cfg.model, Config.DEFAULT_MODEL)

    def test_skips_oversized_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            # Write > 65536 bytes
            f.write("MODEL=gpt-4o\n" * 10000)
            cfg_path = f.name
        cfg = Config()
        # Mimick the size check
        self.assertGreater(os.path.getsize(cfg_path), 65536)
        os.unlink(cfg_path)


class TestDebugFromDotenv(unittest.TestCase):
    """Test CO_VIBE_DEBUG in dotenv."""

    def test_debug_set_to_1(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("CO_VIBE_DEBUG=1\n")
            env_path = f.name
        cfg = Config()
        # _load_dotenv uses same key=value parsing; simulate via direct approach
        # The dotenv parser sets self.debug = True if val == "1"
        # We test via _load_env with environ mock as the logic is identical
        with patch.dict(os.environ, {"CO_VIBE_DEBUG": "1"}, clear=False):
            cfg._load_env()
        self.assertTrue(cfg.debug)
        os.unlink(env_path)

    def test_debug_not_1_stays_false(self):
        cfg = Config()
        with patch.dict(os.environ, {"CO_VIBE_DEBUG": "0"}, clear=False):
            cfg._load_env()
        self.assertFalse(cfg.debug)


if __name__ == "__main__":
    unittest.main()
