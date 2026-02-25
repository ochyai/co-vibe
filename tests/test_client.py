"""Comprehensive tests for MultiProviderClient.

Tests cover: init, check_connection, check_model, _select_model,
_get_fallback_models, message/tool format converters, chat, chat_sync,
tokenize, and constants.  All HTTP is mocked — no real API calls.
"""

import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import MagicMock, patch, PropertyMock

# co-vibe uses a hyphen, so standard import won't work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib

co_vibe = importlib.import_module("co-vibe")
MultiProviderClient = co_vibe.MultiProviderClient
Config = co_vibe.Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Return a Config with sensible defaults (no API keys unless set)."""
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
        return MultiProviderClient(_make_config(**overrides))


# ═══════════════════════════════════════════════════════════════════════════
# 1. __init__
# ═══════════════════════════════════════════════════════════════════════════

class TestInit(unittest.TestCase):

    def test_init_no_keys(self):
        client = _make_client()
        self.assertEqual(client._api_keys, {})
        self.assertEqual(client._available_models, [])

    def test_init_anthropic_key_from_config(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertIn("anthropic", client._api_keys)
        self.assertTrue(
            any(m[0] == "anthropic" for m in client._available_models)
        )

    def test_init_openai_key_from_config(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        self.assertIn("openai", client._api_keys)

    def test_init_groq_key_from_config(self):
        client = _make_client(groq_api_key="gsk_TESTKEY123456789")
        self.assertIn("groq", client._api_keys)

    def test_init_key_from_env_var(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-ENVKEY123456",
            "OPENAI_API_KEY": "",
            "GROQ_API_KEY": "",
            "CO_VIBE_STRATEGY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            client = MultiProviderClient(_make_config())
        self.assertIn("anthropic", client._api_keys)
        self.assertEqual(client._api_keys["anthropic"], "sk-ant-ENVKEY123456")

    def test_init_short_key_ignored(self):
        """Keys <= 5 chars are rejected."""
        client = _make_client(anthropic_api_key="short")
        self.assertNotIn("anthropic", client._api_keys)

    def test_init_config_key_overrides_env(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-ENVKEY123456",
            "OPENAI_API_KEY": "",
            "GROQ_API_KEY": "",
            "CO_VIBE_STRATEGY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            client = MultiProviderClient(
                _make_config(anthropic_api_key="sk-ant-CONFIGKEY1234")
            )
        self.assertEqual(client._api_keys["anthropic"], "sk-ant-CONFIGKEY1234")

    def test_init_multiple_providers(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        self.assertEqual(len(client._api_keys), 2)
        # Available models should come from both providers
        providers = {m[0] for m in client._available_models}
        self.assertEqual(providers, {"anthropic", "openai"})

    def test_init_strategy_from_config(self):
        client = _make_client(strategy="fast")
        self.assertEqual(client._strategy, "fast")

    def test_init_strategy_from_env(self):
        env = {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
            "GROQ_API_KEY": "",
            "CO_VIBE_STRATEGY": "cheap",
        }
        cfg = _make_config()
        cfg.strategy = None  # unset so env takes over
        with patch.dict(os.environ, env, clear=False):
            client = MultiProviderClient(cfg)
        self.assertEqual(client._strategy, "cheap")

    def test_init_stores_config_values(self):
        client = _make_client()
        self.assertEqual(client.max_tokens, 1024)
        self.assertEqual(client.temperature, 0.7)
        self.assertEqual(client.context_window, 128000)
        self.assertFalse(client.debug)


# ═══════════════════════════════════════════════════════════════════════════
# 2. check_connection
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckConnection(unittest.TestCase):

    def test_no_keys_returns_false(self):
        client = _make_client()
        ok, models = client.check_connection()
        self.assertFalse(ok)
        self.assertEqual(models, [])

    def test_with_keys_http_success(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data":[]}'
        mock_resp.close = MagicMock()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, models = client.check_connection()
        self.assertTrue(ok)
        self.assertIn("claude-sonnet-4-6", models)

    def test_with_keys_http_failure_still_returns_true(self):
        """Even if the health-check HTTP call fails, we still return True if keys exist."""
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network")):
            ok, models = client.check_connection(retries=1)
        self.assertTrue(ok)
        self.assertTrue(len(models) > 0)

    def test_check_connection_retries(self):
        """Should retry the specified number of times before giving up."""
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")) as mock_url:
            with patch("time.sleep"):
                client.check_connection(retries=3)
        self.assertEqual(mock_url.call_count, 3)


# ═══════════════════════════════════════════════════════════════════════════
# 3. check_model
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckModel(unittest.TestCase):

    def test_known_model_with_key(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client.check_model("claude-sonnet-4-6"))

    def test_known_model_without_key(self):
        client = _make_client()
        self.assertFalse(client.check_model("claude-sonnet-4-6"))

    def test_auto_with_keys(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client.check_model("auto"))

    def test_auto_without_keys(self):
        client = _make_client()
        self.assertFalse(client.check_model("auto"))

    def test_empty_string_with_keys(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client.check_model(""))

    def test_partial_match(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client.check_model("claude-sonnet"))

    def test_unknown_model_with_keys_fallback(self):
        """Unknown model name still returns True if we have any provider."""
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        self.assertTrue(client.check_model("some-future-model-v99"))

    def test_unknown_model_without_keys(self):
        client = _make_client()
        self.assertFalse(client.check_model("some-future-model-v99"))

    def test_custom_available_list(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        self.assertTrue(client.check_model("my-custom", available_models=["my-custom"]))


# ═══════════════════════════════════════════════════════════════════════════
# 4. _select_model
# ═══════════════════════════════════════════════════════════════════════════

class TestSelectModel(unittest.TestCase):

    def test_exact_hint(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        provider, model = client._select_model("claude-sonnet-4-6")
        self.assertEqual(provider, "anthropic")
        self.assertEqual(model, "claude-sonnet-4-6")

    def test_partial_hint(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        provider, model = client._select_model("claude-haiku")
        self.assertEqual(provider, "anthropic")
        self.assertIn("haiku", model)

    def test_auto_uses_strategy(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
            strategy="fast",
        )
        provider, model = client._select_model("auto")
        # fast strategy prefers "fast" tier first
        fast_models = [m[1] for m in client.MODELS if m[2] == "fast"]
        self.assertIn(model, fast_models)

    def test_empty_hint_uses_strategy(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            strategy="auto",
        )
        provider, model = client._select_model("")
        # "auto" prefers "balanced" tier
        self.assertEqual(model, "claude-sonnet-4-6")

    def test_no_models_raises(self):
        client = _make_client()
        with self.assertRaises(RuntimeError):
            client._select_model("auto")

    def test_strategy_strong(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
            strategy="strong",
        )
        # "strong" tier: picks Opus or o3
        provider, model = client._select_model("")
        strong_models = [m[1] for m in client.MODELS if m[2] == "strong"]
        self.assertIn(model, strong_models)

    def test_strategy_cheap(self):
        client = _make_client(
            groq_api_key="gsk_TESTKEY123456789",
            strategy="cheap",
        )
        provider, model = client._select_model("")
        # Fast tier Groq models: qwen/qwen3-32b or llama-3.1-8b-instant
        self.assertIn(model, ("qwen/qwen3-32b", "llama-3.1-8b-instant"))

    def test_fallback_to_first_available(self):
        """If no tier matches, first available model is returned."""
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        # Temporarily break strategy tiers so nothing matches
        original = client.STRATEGY_TIERS
        client.STRATEGY_TIERS = {"auto": ["nonexistent_tier"]}
        client._strategy = "auto"
        provider, model = client._select_model("")
        self.assertEqual(provider, "anthropic")
        # Restore
        client.STRATEGY_TIERS = original


# ═══════════════════════════════════════════════════════════════════════════
# 5. _get_fallback_models
# ═══════════════════════════════════════════════════════════════════════════

class TestGetFallbackModels(unittest.TestCase):

    def test_excludes_failed_provider(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        fallbacks = client._get_fallback_models("anthropic", "claude-sonnet-4-6")
        # First fallbacks should be from different providers (prioritized)
        # Then same-provider different models
        diff_provider = [(p, m) for p, m in fallbacks if p != "anthropic"]
        same_provider = [(p, m) for p, m in fallbacks if p == "anthropic"]
        self.assertTrue(len(diff_provider) > 0, "Should have fallbacks from other providers")
        self.assertIn("openai", {p for p, _ in diff_provider})
        # Same-provider fallbacks should not include the failed model
        for _, mid in same_provider:
            self.assertNotEqual(mid, "claude-sonnet-4-6")

    def test_same_provider_different_models_when_single_provider(self):
        """With one provider, fallback returns same-provider different models."""
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        fallbacks = client._get_fallback_models("anthropic", "claude-sonnet-4-6")
        # Should return other anthropic models (opus, haiku) but NOT the failed model
        for _, model_id in fallbacks:
            self.assertNotEqual(model_id, "claude-sonnet-4-6")
        # All should be anthropic (only provider available)
        for provider, _ in fallbacks:
            self.assertEqual(provider, "anthropic")

    def test_multiple_fallbacks(self):
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
            groq_api_key="gsk_TESTKEY123456789",
        )
        fallbacks = client._get_fallback_models("anthropic", "claude-sonnet-4-6")
        providers = {p for p, _ in fallbacks}
        self.assertIn("openai", providers)
        self.assertIn("groq", providers)


# ═══════════════════════════════════════════════════════════════════════════
# 6. _messages_to_anthropic
# ═══════════════════════════════════════════════════════════════════════════

class TestMessagesToAnthropic(unittest.TestCase):

    def _client(self):
        return _make_client(anthropic_api_key="sk-ant-TESTKEY123456")

    def test_simple_user_message(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "Hello"}
        ])
        self.assertEqual(system, "")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Hello")

    def test_system_message_extracted(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ])
        self.assertEqual(system, "You are helpful.")
        self.assertEqual(len(msgs), 1)

    def test_multiple_system_messages(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "system", "content": "Rule 1"},
            {"role": "system", "content": "Rule 2"},
            {"role": "user", "content": "Hi"},
        ])
        self.assertIn("Rule 1", system)
        self.assertIn("Rule 2", system)

    def test_assistant_with_tool_calls(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": "I'll use a tool.",
                "tool_calls": [{
                    "id": "call_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Tokyo"}',
                    },
                }],
            },
        ])
        self.assertEqual(len(msgs), 2)
        blocks = msgs[1]["content"]
        self.assertIsInstance(blocks, list)
        types = [b["type"] for b in blocks]
        self.assertIn("text", types)
        self.assertIn("tool_use", types)
        tool_block = [b for b in blocks if b["type"] == "tool_use"][0]
        self.assertEqual(tool_block["id"], "call_123")
        self.assertEqual(tool_block["name"], "get_weather")
        self.assertEqual(tool_block["input"], {"city": "Tokyo"})

    def test_tool_result_converted(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_123",
                    "function": {"name": "search", "arguments": "{}"},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": "Result data",
            },
        ])
        # tool result becomes a user message with tool_result content block
        tool_msg = [m for m in msgs if m["role"] == "user"
                    and isinstance(m.get("content"), list)
                    and any(b.get("type") == "tool_result" for b in m["content"])]
        self.assertTrue(len(tool_msg) > 0)

    def test_consecutive_same_role_merged(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ])
        self.assertEqual(len(msgs), 1)
        self.assertIn("Hello", msgs[0]["content"])
        self.assertIn("World", msgs[0]["content"])

    def test_empty_messages(self):
        system, msgs = self._client()._messages_to_anthropic([])
        self.assertEqual(system, "")
        self.assertEqual(msgs, [])

    def test_multi_turn_conversation(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Reply 2"},
        ])
        self.assertEqual(system, "System prompt")
        self.assertEqual(len(msgs), 4)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])

    def test_assistant_tool_call_invalid_json_args(self):
        """Invalid JSON arguments should be wrapped in a raw dict."""
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "test"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_bad",
                    "function": {
                        "name": "broken",
                        "arguments": "not valid json {{{",
                    },
                }],
            },
        ])
        blocks = msgs[1]["content"]
        tool_block = [b for b in blocks if b["type"] == "tool_use"][0]
        self.assertIn("raw", tool_block["input"])

    def test_merge_str_with_list(self):
        """Merging a string content with a list content."""
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "Hello"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "tool result",
            },
        ])
        # Both should merge into a single user message (string + list)
        self.assertEqual(len(msgs), 1)
        self.assertIsInstance(msgs[0]["content"], list)

    def test_multiple_tool_calls_in_single_assistant_msg(self):
        system, msgs = self._client()._messages_to_anthropic([
            {"role": "user", "content": "do two things"},
            {
                "role": "assistant",
                "content": "Using two tools",
                "tool_calls": [
                    {
                        "id": "call_a",
                        "function": {"name": "tool_a", "arguments": '{"x":1}'},
                    },
                    {
                        "id": "call_b",
                        "function": {"name": "tool_b", "arguments": '{"y":2}'},
                    },
                ],
            },
        ])
        blocks = msgs[1]["content"]
        tool_blocks = [b for b in blocks if b["type"] == "tool_use"]
        self.assertEqual(len(tool_blocks), 2)
        self.assertEqual(tool_blocks[0]["name"], "tool_a")
        self.assertEqual(tool_blocks[1]["name"], "tool_b")


# ═══════════════════════════════════════════════════════════════════════════
# 7. _tools_to_anthropic
# ═══════════════════════════════════════════════════════════════════════════

class TestToolsToAnthropic(unittest.TestCase):

    def _client(self):
        return _make_client(anthropic_api_key="sk-ant-TESTKEY123456")

    def test_empty_tools(self):
        result = self._client()._tools_to_anthropic([])
        self.assertEqual(result, [])

    def test_none_tools(self):
        result = self._client()._tools_to_anthropic(None)
        self.assertEqual(result, [])

    def test_openai_function_format(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]
        result = self._client()._tools_to_anthropic(tools)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "get_weather")
        self.assertEqual(result[0]["description"], "Get the current weather")
        self.assertIn("properties", result[0]["input_schema"])

    def test_unwrapped_format(self):
        """Handles tools without the wrapping 'function' key."""
        tools = [{
            "name": "search",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {}},
        }]
        result = self._client()._tools_to_anthropic(tools)
        self.assertEqual(result[0]["name"], "search")

    def test_description_truncated(self):
        """Description should be truncated to 1024 chars."""
        tools = [{
            "function": {
                "name": "verbose_tool",
                "description": "A" * 2000,
                "parameters": {},
            },
        }]
        result = self._client()._tools_to_anthropic(tools)
        self.assertLessEqual(len(result[0]["description"]), 1024)


# ═══════════════════════════════════════════════════════════════════════════
# 8. _anthropic_response_to_openai
# ═══════════════════════════════════════════════════════════════════════════

class TestAnthropicResponseToOpenai(unittest.TestCase):

    def _client(self):
        return _make_client(anthropic_api_key="sk-ant-TESTKEY123456")

    def test_text_response(self):
        anth = {
            "id": "msg_123",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "Hello world"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = self._client()._anthropic_response_to_openai(anth)
        self.assertEqual(result["object"], "chat.completion")
        self.assertEqual(result["choices"][0]["message"]["content"], "Hello world")
        self.assertEqual(result["choices"][0]["finish_reason"], "stop")
        self.assertEqual(result["usage"]["total_tokens"], 15)

    def test_tool_use_response(self):
        anth = {
            "id": "msg_456",
            "model": "claude-sonnet-4-6",
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "get_weather",
                    "input": {"city": "Tokyo"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 30},
        }
        result = self._client()._anthropic_response_to_openai(anth)
        msg = result["choices"][0]["message"]
        self.assertEqual(msg["content"], "Let me check.")
        self.assertEqual(len(msg["tool_calls"]), 1)
        tc = msg["tool_calls"][0]
        self.assertEqual(tc["id"], "toolu_abc")
        self.assertEqual(tc["type"], "function")
        self.assertEqual(tc["function"]["name"], "get_weather")
        self.assertEqual(json.loads(tc["function"]["arguments"]), {"city": "Tokyo"})
        self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")

    def test_empty_content(self):
        anth = {
            "content": [],
            "stop_reason": "end_turn",
            "usage": {},
        }
        result = self._client()._anthropic_response_to_openai(anth)
        self.assertIsNone(result["choices"][0]["message"]["content"])

    def test_multiple_text_blocks(self):
        anth = {
            "content": [
                {"type": "text", "text": "Line 1"},
                {"type": "text", "text": "Line 2"},
            ],
            "stop_reason": "end_turn",
            "usage": {},
        }
        result = self._client()._anthropic_response_to_openai(anth)
        self.assertIn("Line 1", result["choices"][0]["message"]["content"])
        self.assertIn("Line 2", result["choices"][0]["message"]["content"])

    def test_multiple_tool_calls(self):
        anth = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "tool_a",
                    "input": {"a": 1},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "tool_b",
                    "input": {"b": 2},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }
        result = self._client()._anthropic_response_to_openai(anth)
        msg = result["choices"][0]["message"]
        self.assertEqual(len(msg["tool_calls"]), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 9. chat — mock HTTP, provider routing, fallback
# ═══════════════════════════════════════════════════════════════════════════

class TestChat(unittest.TestCase):

    def test_chat_anthropic_non_streaming(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        mock_resp = {
            "id": "msg_test",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "Hi from Claude"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        with patch.object(client, "_http_request", return_value=mock_resp):
            result = client.chat(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )
        self.assertEqual(result["choices"][0]["message"]["content"], "Hi from Claude")

    def test_chat_openai_non_streaming(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": "gpt-4o",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Hi from GPT"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        with patch.object(client, "_http_request", return_value=mock_resp):
            result = client.chat(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
            )
        self.assertEqual(result["choices"][0]["message"]["content"], "Hi from GPT")

    def test_chat_fallback_on_error(self):
        """If anthropic fails, should fall back to openai."""
        client = _make_client(
            anthropic_api_key="sk-ant-TESTKEY123456",
            openai_api_key="sk-openai-TESTKEY123456",
        )
        call_count = [0]
        def mock_http(url, body, headers, **kw):
            call_count[0] += 1
            if "anthropic" in url:
                raise RuntimeError("API error (HTTP 500): server error")
            return {
                "id": "chatcmpl-fb",
                "object": "chat.completion",
                "model": "gpt-4o",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Fallback reply"},
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
        self.assertEqual(result["choices"][0]["message"]["content"], "Fallback reply")
        self.assertEqual(call_count[0], 2)

    def test_chat_raises_when_all_fallbacks_exhausted(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        with patch.object(client, "_http_request",
                          side_effect=RuntimeError("API error (HTTP 500): down")):
            with self.assertRaises(RuntimeError):
                client.chat(
                    model="claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "Hi"}],
                    stream=False,
                )

    def test_chat_with_tools(self):
        client = _make_client(anthropic_api_key="sk-ant-TESTKEY123456")
        mock_resp = {
            "id": "msg_tools",
            "model": "claude-sonnet-4-6",
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "search",
                 "input": {"q": "test"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        tools = [{
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        }]
        with patch.object(client, "_http_request", return_value=mock_resp):
            result = client.chat(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "search for test"}],
                tools=tools,
                stream=False,
            )
        self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")


# ═══════════════════════════════════════════════════════════════════════════
# 10. chat_sync
# ═══════════════════════════════════════════════════════════════════════════

class TestChatSync(unittest.TestCase):

    def test_basic_content(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Sync reply"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hi"}],
            )
        self.assertEqual(result["content"], "Sync reply")
        self.assertEqual(result["tool_calls"], [])

    def test_tool_calls_parsed(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_sync1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "2+2"}',
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "calc"}],
            )
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["name"], "calculator")
        self.assertEqual(result["tool_calls"][0]["arguments"], {"expression": "2+2"})

    def test_think_tags_stripped(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<think>internal reasoning</think>The answer is 42.",
                },
                "finish_reason": "stop",
            }],
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "answer"}],
            )
        self.assertEqual(result["content"], "The answer is 42.")

    def test_invalid_json_arguments_recovered(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_bad",
                        "type": "function",
                        "function": {
                            "name": "broken",
                            "arguments": "{'key': 'value',}",  # single quotes + trailing comma
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        self.assertEqual(result["tool_calls"][0]["arguments"], {"key": "value"})

    def test_completely_broken_json_goes_to_raw(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        mock_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_raw",
                        "type": "function",
                        "function": {
                            "name": "broken",
                            "arguments": "totally not json at all!!!",
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        self.assertIn("raw", result["tool_calls"][0]["arguments"])

    def test_oversized_arguments_capped(self):
        client = _make_client(openai_api_key="sk-openai-TESTKEY123456")
        huge_args = '{"data": "' + "X" * 200000 + '"}'
        mock_resp = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_big",
                        "type": "function",
                        "function": {
                            "name": "big_tool",
                            "arguments": huge_args,
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        with patch.object(client, "chat", return_value=mock_resp):
            result = client.chat_sync(
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        # The result should exist but arguments were truncated at 100KB
        self.assertTrue(len(result["tool_calls"]) == 1)


# ═══════════════════════════════════════════════════════════════════════════
# 11. tokenize
# ═══════════════════════════════════════════════════════════════════════════

class TestTokenize(unittest.TestCase):

    def test_basic(self):
        client = _make_client()
        self.assertEqual(client.tokenize("any-model", "Hello world!!"), 3)

    def test_empty(self):
        client = _make_client()
        self.assertEqual(client.tokenize("any-model", ""), 0)

    def test_long_text(self):
        client = _make_client()
        text = "a" * 1000
        self.assertEqual(client.tokenize("any-model", text), 250)


# ═══════════════════════════════════════════════════════════════════════════
# 12. Constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):

    def test_models_structure(self):
        for entry in MultiProviderClient.MODELS:
            self.assertEqual(len(entry), 4)
            provider, model_id, tier, ctx = entry
            self.assertIn(provider, ("anthropic", "openai", "groq", "ollama"))
            self.assertIsInstance(model_id, str)
            self.assertIn(tier, ("strong", "balanced", "fast", "cheap"))
            self.assertIsInstance(ctx, int)
            self.assertGreater(ctx, 0)

    def test_provider_endpoints_keys(self):
        self.assertIn("anthropic", MultiProviderClient.PROVIDER_ENDPOINTS)
        self.assertIn("openai", MultiProviderClient.PROVIDER_ENDPOINTS)
        self.assertIn("groq", MultiProviderClient.PROVIDER_ENDPOINTS)

    def test_provider_endpoints_are_urls(self):
        for name, url in MultiProviderClient.PROVIDER_ENDPOINTS.items():
            if name == "ollama":
                self.assertTrue(url.startswith("http://"))  # Ollama is local HTTP
            else:
                self.assertTrue(url.startswith("https://"))

    def test_strategy_tiers_keys(self):
        expected = {"strong", "auto", "fast", "cheap"}
        self.assertEqual(set(MultiProviderClient.STRATEGY_TIERS.keys()), expected)

    def test_strategy_tiers_values_are_lists(self):
        for key, tiers in MultiProviderClient.STRATEGY_TIERS.items():
            self.assertIsInstance(tiers, list)
            self.assertTrue(len(tiers) > 0)

    def test_provider_key_envs(self):
        self.assertEqual(
            MultiProviderClient.PROVIDER_KEY_ENVS["anthropic"],
            "ANTHROPIC_API_KEY",
        )
        self.assertEqual(
            MultiProviderClient.PROVIDER_KEY_ENVS["openai"],
            "OPENAI_API_KEY",
        )
        self.assertEqual(
            MultiProviderClient.PROVIDER_KEY_ENVS["groq"],
            "GROQ_API_KEY",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Extra: pull_model
# ═══════════════════════════════════════════════════════════════════════════

class TestPullModel(unittest.TestCase):

    def test_always_returns_true(self):
        client = _make_client()
        self.assertTrue(client.pull_model("any-model"))


if __name__ == "__main__":
    unittest.main()
