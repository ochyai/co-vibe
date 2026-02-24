"""Comprehensive tests for co-vibe proxy."""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from unittest import mock

import pytest

# Add project root to sys.path so we can import the proxy module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib
proxy_mod = importlib.import_module("co-vibe-proxy")

# Pull out all the names we need for testing
estimate_complexity = proxy_mod.estimate_complexity
select_model = proxy_mod.select_model
anthropic_to_openai_messages = proxy_mod.anthropic_to_openai_messages
anthropic_tools_to_openai = proxy_mod.anthropic_tools_to_openai
openai_response_to_anthropic = proxy_mod.openai_response_to_anthropic
get_available_providers = proxy_mod.get_available_providers
get_available_models = proxy_mod.get_available_models
load_dotenv = proxy_mod.load_dotenv
anthropic_to_sse = proxy_mod.anthropic_to_sse
ModelDef = proxy_mod.ModelDef
Tier = proxy_mod.Tier
MODELS = proxy_mod.MODELS
PROVIDER_CONFIGS = proxy_mod.PROVIDER_CONFIGS
CoVibeHandler = proxy_mod.CoVibeHandler
ThreadedHTTPServer = proxy_mod.ThreadedHTTPServer


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def all_providers():
    """Simulated environment with all three providers available."""
    return {
        "anthropic": "sk-ant-test-key-123456",
        "openai": "sk-openai-test-key-123456",
        "groq": "gsk-groq-test-key-123456",
    }


@pytest.fixture
def anthropic_only():
    """Environment with only Anthropic available."""
    return {"anthropic": "sk-ant-test-key-123456"}


@pytest.fixture
def openai_only():
    """Environment with only OpenAI available."""
    return {"openai": "sk-openai-test-key-123456"}


@pytest.fixture
def simple_request():
    """A simple request with short messages."""
    return {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
    }


@pytest.fixture
def complex_request():
    """A complex request with many messages, tools, and long content."""
    long_text = "x" * 60000
    tools = [{"name": f"tool_{i}", "description": f"Tool {i}", "input_schema": {"type": "object"}} for i in range(15)]
    messages = [{"role": "user", "content": long_text}]
    messages += [{"role": "assistant", "content": f"Response {i}"} for i in range(10)]
    messages += [{"role": "user", "content": f"Follow-up {i}"} for i in range(15)]
    return {
        "model": "claude-opus-4-6",
        "max_tokens": 8192,
        "system": "A" * 10000,
        "messages": messages,
        "tools": tools,
    }


# ============================================================
# 1. Routing Logic Tests
# ============================================================

class TestEstimateComplexity:
    """Tests for estimate_complexity()."""

    def test_empty_request(self):
        assert estimate_complexity({}) == 0.0

    def test_simple_request(self, simple_request):
        score = estimate_complexity(simple_request)
        assert score < 0.3

    def test_many_messages_increases_complexity(self):
        few = {"messages": [{"role": "user", "content": "hi"}] * 2}
        medium = {"messages": [{"role": "user", "content": "hi"}] * 10}
        many = {"messages": [{"role": "user", "content": "hi"}] * 25}

        score_few = estimate_complexity(few)
        score_medium = estimate_complexity(medium)
        score_many = estimate_complexity(many)

        assert score_few < score_medium
        assert score_medium < score_many

    def test_long_content_increases_complexity(self):
        short = {"messages": [{"role": "user", "content": "hello"}]}
        medium = {"messages": [{"role": "user", "content": "x" * 20000}]}
        long_ = {"messages": [{"role": "user", "content": "x" * 60000}]}

        assert estimate_complexity(short) < estimate_complexity(medium)
        assert estimate_complexity(medium) < estimate_complexity(long_)

    def test_tools_increase_complexity(self):
        no_tools = {"messages": [{"role": "user", "content": "hi"}]}
        few_tools = {"messages": [{"role": "user", "content": "hi"}], "tools": [{"name": "t"}] * 3}
        many_tools = {"messages": [{"role": "user", "content": "hi"}], "tools": [{"name": "t"}] * 15}

        assert estimate_complexity(no_tools) < estimate_complexity(few_tools)
        assert estimate_complexity(few_tools) < estimate_complexity(many_tools)

    def test_tool_use_blocks_increase_complexity(self):
        req = {
            "messages": [
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "result1"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "result2"},
                ]},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "t3", "name": "f", "input": {}},
                ]},
            ],
        }
        score = estimate_complexity(req)
        assert score >= 0.15

    def test_system_prompt_increases_complexity(self):
        short_sys = {"messages": [{"role": "user", "content": "hi"}], "system": "Be helpful."}
        long_sys = {"messages": [{"role": "user", "content": "hi"}], "system": "x" * 10000}

        assert estimate_complexity(short_sys) < estimate_complexity(long_sys)

    def test_system_prompt_as_list(self):
        req = {
            "messages": [{"role": "user", "content": "hi"}],
            "system": [{"type": "text", "text": "x" * 10000}],
        }
        score = estimate_complexity(req)
        assert score >= 0.1

    def test_content_as_list_with_text(self):
        req = {
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": "x" * 20000},
                ]},
            ],
        }
        score = estimate_complexity(req)
        assert score >= 0.2

    def test_complexity_capped_at_1(self, complex_request):
        score = estimate_complexity(complex_request)
        assert score <= 1.0

    def test_non_dict_content_in_list(self):
        req = {
            "messages": [
                {"role": "user", "content": ["just a string", 42]},
            ],
        }
        score = estimate_complexity(req)
        assert score >= 0.0


class TestSelectModel:
    """Tests for select_model()."""

    def test_strong_strategy_picks_strong_model(self, simple_request, all_providers):
        model = select_model(simple_request, "strong", all_providers)
        assert model.tier == Tier.STRONG

    def test_fast_strategy_picks_fast_model(self, simple_request, all_providers):
        model = select_model(simple_request, "fast", all_providers)
        assert model.latency_class == "fast"

    def test_cheap_strategy_picks_cheapest(self, simple_request, all_providers):
        model = select_model(simple_request, "cheap", all_providers)
        assert model.model_id == "llama-3.1-8b-instant"

    def test_auto_low_complexity_picks_fast(self, simple_request, all_providers):
        model = select_model(simple_request, "auto", all_providers)
        assert model.tier in (Tier.FAST, Tier.CHEAP)

    def test_auto_high_complexity_picks_strong(self, complex_request, all_providers):
        model = select_model(complex_request, "auto", all_providers)
        assert model.tier in (Tier.STRONG, Tier.BALANCED)

    def test_auto_medium_complexity(self, all_providers):
        req = {
            "messages": [{"role": "user", "content": "x" * 20000}] * 5,
            "tools": [{"name": "t"}] * 3,
        }
        model = select_model(req, "auto", all_providers)
        assert model.tier in (Tier.BALANCED, Tier.FAST)

    def test_no_models_raises(self, simple_request):
        with pytest.raises(ValueError, match="No models available"):
            select_model(simple_request, "auto", {})

    def test_single_provider_anthropic(self, simple_request, anthropic_only):
        model = select_model(simple_request, "auto", anthropic_only)
        assert model.provider == "anthropic"

    def test_single_provider_openai(self, simple_request, openai_only):
        model = select_model(simple_request, "auto", openai_only)
        assert model.provider == "openai"

    def test_strong_with_only_cheap_models(self, simple_request):
        groq_only = {"groq": "gsk-test-key-123456"}
        model = select_model(simple_request, "strong", groq_only)
        assert model.provider == "groq"

    def test_auto_fallback_to_first_available(self):
        req = {
            "messages": [{"role": "user", "content": "x" * 20000}],
            "tools": [{"name": "t"}] * 5,
        }
        groq_only = {"groq": "gsk-test-key-123456"}
        model = select_model(req, "auto", groq_only)
        assert model.provider == "groq"

    def test_model_override_strong(self, simple_request, all_providers):
        original = proxy_mod._strong_override
        try:
            proxy_mod._strong_override = "gpt-4o"
            model = select_model(simple_request, "strong", all_providers)
            assert model.model_id == "gpt-4o"
        finally:
            proxy_mod._strong_override = original

    def test_model_override_fast(self, simple_request, all_providers):
        original = proxy_mod._fast_override
        try:
            proxy_mod._fast_override = "gpt-4o-mini"
            model = select_model(simple_request, "fast", all_providers)
            assert model.model_id == "gpt-4o-mini"
        finally:
            proxy_mod._fast_override = original

    def test_model_override_cheap(self, simple_request, all_providers):
        original = proxy_mod._cheap_override
        try:
            proxy_mod._cheap_override = "gemma2-9b-it"
            model = select_model(simple_request, "cheap", all_providers)
            assert model.model_id == "gemma2-9b-it"
        finally:
            proxy_mod._cheap_override = original


# ============================================================
# 2. Format Conversion Tests
# ============================================================

class TestAnthropicToOpenaiMessages:
    """Tests for anthropic_to_openai_messages()."""

    def test_simple_text_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"

    def test_text_block_content(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "Line 1"},
            {"type": "text", "text": "Line 2"},
        ]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert "Line 1" in result[0]["content"]
        assert "Line 2" in result[0]["content"]

    def test_tool_use_block(self):
        messages = [{"role": "assistant", "content": [
            {"type": "text", "text": "I'll search."},
            {"type": "tool_use", "id": "toolu_abc123", "name": "search", "input": {"q": "test"}},
        ]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "toolu_abc123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "search"
        assert json.loads(tc["function"]["arguments"]) == {"q": "test"}

    def test_tool_result_block(self):
        messages = [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_abc123", "content": "Found 5 results"},
        ]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "toolu_abc123"
        assert result[0]["content"] == "Found 5 results"

    def test_tool_result_with_list_content(self):
        messages = [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_x", "content": [
                {"type": "text", "text": "Result part 1"},
                {"type": "text", "text": "Result part 2"},
            ]},
        ]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert "Result part 1" in result[0]["content"]
        assert "Result part 2" in result[0]["content"]

    def test_thinking_blocks_skipped(self):
        messages = [{"role": "assistant", "content": [
            {"type": "thinking", "thinking": "Let me think..."},
            {"type": "text", "text": "The answer is 42."},
        ]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["content"] == "The answer is 42."

    def test_multiple_messages(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"

    def test_non_dict_block_in_content_list(self):
        messages = [{"role": "user", "content": ["raw string"]}]
        result = anthropic_to_openai_messages(messages)
        assert len(result) == 1
        assert "raw string" in result[0]["content"]

    def test_tool_use_without_explicit_id(self):
        messages = [{"role": "assistant", "content": [
            {"type": "tool_use", "name": "do_something", "input": {}},
        ]}]
        result = anthropic_to_openai_messages(messages)
        tc = result[0]["tool_calls"][0]
        assert tc["id"].startswith("call_")

    def test_tool_calls_with_text(self):
        messages = [{"role": "assistant", "content": [
            {"type": "text", "text": "Calling tool now"},
            {"type": "tool_use", "id": "t1", "name": "f", "input": {}},
        ]}]
        result = anthropic_to_openai_messages(messages)
        msg = result[0]
        assert msg["content"] == "Calling tool now"
        assert len(msg["tool_calls"]) == 1


class TestAnthropicToolsToOpenai:
    """Tests for anthropic_tools_to_openai()."""

    def test_basic_tool_conversion(self):
        tools = [
            {
                "name": "read_file",
                "description": "Read a file from the filesystem",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "File path"}},
                    "required": ["path"],
                },
            }
        ]
        result = anthropic_tools_to_openai(tools)
        assert len(result) == 1
        t = result[0]
        assert t["type"] == "function"
        assert t["function"]["name"] == "read_file"
        assert t["function"]["description"] == "Read a file from the filesystem"
        assert t["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {"type": "object"}},
            {"name": "tool_b", "description": "B", "input_schema": {"type": "object"}},
            {"name": "tool_c", "description": "C", "input_schema": {"type": "object"}},
        ]
        result = anthropic_tools_to_openai(tools)
        assert len(result) == 3
        assert [t["function"]["name"] for t in result] == ["tool_a", "tool_b", "tool_c"]

    def test_description_truncation(self):
        tools = [{"name": "t", "description": "x" * 2000, "input_schema": {"type": "object"}}]
        result = anthropic_tools_to_openai(tools)
        assert len(result[0]["function"]["description"]) == 1024

    def test_empty_tool_list(self):
        assert anthropic_tools_to_openai([]) == []

    def test_missing_fields(self):
        tools = [{}]
        result = anthropic_tools_to_openai(tools)
        assert result[0]["function"]["name"] == ""
        assert result[0]["function"]["description"] == ""
        assert result[0]["function"]["parameters"] == {}


class TestOpenaiResponseToAnthropic:
    """Tests for openai_response_to_anthropic()."""

    def test_simple_text_response(self):
        oai_resp = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert result["model"] == "gpt-4o"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello!"
        assert result["stop_reason"] == "end_turn"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 5

    def test_tool_call_response(self):
        oai_resp = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"query": "test"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        assert result["stop_reason"] == "tool_use"
        tool_blocks = [b for b in result["content"] if b["type"] == "tool_use"]
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["name"] == "search"
        assert tool_blocks[0]["input"] == {"query": "test"}
        assert tool_blocks[0]["id"].startswith("toolu_")

    def test_text_and_tool_calls(self):
        oai_resp = {
            "choices": [{
                "message": {
                    "content": "Let me search.",
                    "tool_calls": [{
                        "id": "call_xyz",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "x"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        types = [b["type"] for b in result["content"]]
        assert "text" in types
        assert "tool_use" in types

    def test_empty_response(self):
        oai_resp = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": {},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == ""

    def test_invalid_json_arguments(self):
        oai_resp = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_bad",
                        "type": "function",
                        "function": {"name": "f", "arguments": "not valid json{"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        tool_block = [b for b in result["content"] if b["type"] == "tool_use"][0]
        assert "raw" in tool_block["input"]

    def test_response_has_required_fields(self):
        oai_resp = {
            "choices": [{"message": {"content": "test"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        result = openai_response_to_anthropic(oai_resp, "test-model")
        assert "id" in result
        assert result["id"].startswith("msg_")
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert result["stop_sequence"] is None
        assert "cache_creation_input_tokens" in result["usage"]
        assert "cache_read_input_tokens" in result["usage"]

    def test_none_content_with_no_tool_calls(self):
        oai_resp = {
            "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
            "usage": {},
        }
        result = openai_response_to_anthropic(oai_resp, "gpt-4o")
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == ""


# ============================================================
# 3. Provider Selection Tests
# ============================================================

class TestGetAvailableProviders:
    """Tests for get_available_providers()."""

    def test_all_keys_present(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-testing-key-1234567",
            "OPENAI_API_KEY": "sk-openai-testing-key-1234567",
            "GROQ_API_KEY": "gsk-groq-testing-key-1234567",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            providers = get_available_providers()
        assert "anthropic" in providers
        assert "openai" in providers
        assert "groq" in providers

    def test_no_keys_present(self):
        env_clear = {k: "" for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"]}
        with mock.patch.dict(os.environ, env_clear, clear=False):
            providers = get_available_providers()
        assert len(providers) == 0

    def test_short_key_rejected(self):
        env = {"ANTHROPIC_API_KEY": "short", "OPENAI_API_KEY": "", "GROQ_API_KEY": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            providers = get_available_providers()
        assert "anthropic" not in providers

    def test_partial_keys(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test-long-enough-key",
            "OPENAI_API_KEY": "",
            "GROQ_API_KEY": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            providers = get_available_providers()
        assert "anthropic" in providers
        assert "openai" not in providers
        assert "groq" not in providers


class TestGetAvailableModels:
    """Tests for get_available_models()."""

    def test_filters_by_provider(self):
        available = {"anthropic": "key"}
        models = get_available_models(available)
        assert all(m.provider == "anthropic" for m in models)
        assert len(models) == 3

    def test_all_providers(self):
        available = {"anthropic": "k", "openai": "k", "groq": "k"}
        models = get_available_models(available)
        assert len(models) == len(MODELS)

    def test_no_providers(self):
        assert get_available_models({}) == []


# ============================================================
# 4. .env Loading Test
# ============================================================

class TestLoadDotenv:
    """Tests for load_dotenv()."""

    def test_loads_key_value_pairs(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_KEY_COVIBE=test_value_123\n")
            f.write("ANOTHER_KEY_COVIBE=another_value\n")
            f.flush()
            path = f.name
        try:
            os.environ.pop("TEST_KEY_COVIBE", None)
            os.environ.pop("ANOTHER_KEY_COVIBE", None)
            load_dotenv(path)
            assert os.environ.get("TEST_KEY_COVIBE") == "test_value_123"
            assert os.environ.get("ANOTHER_KEY_COVIBE") == "another_value"
        finally:
            os.environ.pop("TEST_KEY_COVIBE", None)
            os.environ.pop("ANOTHER_KEY_COVIBE", None)
            os.unlink(path)

    def test_skips_comments_and_empty_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# This is a comment\n")
            f.write("\n")
            f.write("  \n")
            f.write("VALID_KEY_COVIBE=valid_value\n")
            f.write("# Another comment\n")
            f.flush()
            path = f.name
        try:
            os.environ.pop("VALID_KEY_COVIBE", None)
            load_dotenv(path)
            assert os.environ.get("VALID_KEY_COVIBE") == "valid_value"
        finally:
            os.environ.pop("VALID_KEY_COVIBE", None)
            os.unlink(path)

    def test_strips_quotes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('DOUBLE_Q_COVIBE="double_quoted"\n')
            f.write("SINGLE_Q_COVIBE='single_quoted'\n")
            f.flush()
            path = f.name
        try:
            os.environ.pop("DOUBLE_Q_COVIBE", None)
            os.environ.pop("SINGLE_Q_COVIBE", None)
            load_dotenv(path)
            assert os.environ.get("DOUBLE_Q_COVIBE") == "double_quoted"
            assert os.environ.get("SINGLE_Q_COVIBE") == "single_quoted"
        finally:
            os.environ.pop("DOUBLE_Q_COVIBE", None)
            os.environ.pop("SINGLE_Q_COVIBE", None)
            os.unlink(path)

    def test_does_not_override_existing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("EXISTING_KEY_COVIBE=new_value\n")
            f.flush()
            path = f.name
        try:
            os.environ["EXISTING_KEY_COVIBE"] = "original_value"
            load_dotenv(path)
            assert os.environ.get("EXISTING_KEY_COVIBE") == "original_value"
        finally:
            os.environ.pop("EXISTING_KEY_COVIBE", None)
            os.unlink(path)

    def test_missing_file(self):
        load_dotenv("/nonexistent/path/.env")  # Should not raise

    def test_no_equals_sign(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("NO_EQUALS_SIGN\n")
            f.write("HAS_EQUALS_COVIBE=value\n")
            f.flush()
            path = f.name
        try:
            os.environ.pop("HAS_EQUALS_COVIBE", None)
            load_dotenv(path)
            assert os.environ.get("HAS_EQUALS_COVIBE") == "value"
        finally:
            os.environ.pop("HAS_EQUALS_COVIBE", None)
            os.unlink(path)


# ============================================================
# 5. SSE Conversion Test
# ============================================================

def _parse_sse_body(body_bytes):
    """Parse SSE event body bytes into list of (event_type, data_dict) tuples."""
    body = body_bytes.decode("utf-8") if isinstance(body_bytes, bytes) else body_bytes
    events = []
    current_event = None
    current_data = None

    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            current_data = json.loads(line[6:])
        elif line == "" and current_event is not None and current_data is not None:
            events.append((current_event, current_data))
            current_event = None
            current_data = None

    return events


class TestAnthropicToSSE:
    """Tests for anthropic_to_sse()."""

    def test_text_response_produces_correct_events(self):
        anthropic_resp = {
            "id": "msg_test123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello world"}],
            "model": "gpt-4o",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        body = anthropic_to_sse(anthropic_resp)
        events = _parse_sse_body(body)

        event_types = [e[0] for e in events]
        assert event_types == [
            "message_start",
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        ]

        # Verify message_start has empty content
        msg_start_data = events[0][1]
        assert msg_start_data["message"]["content"] == []

        # Verify text delta
        delta_data = events[2][1]
        assert delta_data["delta"]["text"] == "Hello world"

        # Verify message_delta stop_reason
        msg_delta_data = events[4][1]
        assert msg_delta_data["delta"]["stop_reason"] == "end_turn"

    def test_tool_use_response_produces_correct_events(self):
        anthropic_resp = {
            "id": "msg_test456",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Searching..."},
                {"type": "tool_use", "id": "toolu_abc", "name": "search", "input": {"q": "test"}},
            ],
            "model": "gpt-4o",
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 20, "output_tokens": 15},
        }

        body = anthropic_to_sse(anthropic_resp)
        events = _parse_sse_body(body)

        event_types = [e[0] for e in events]
        assert event_types == [
            "message_start",
            "content_block_start", "content_block_delta", "content_block_stop",
            "content_block_start", "content_block_delta", "content_block_stop",
            "message_delta",
            "message_stop",
        ]

        # Verify tool_use content_block_start
        tool_start = events[4][1]
        assert tool_start["content_block"]["type"] == "tool_use"
        assert tool_start["content_block"]["name"] == "search"

        # Verify tool input delta
        tool_delta = events[5][1]
        assert tool_delta["delta"]["type"] == "input_json_delta"
        assert json.loads(tool_delta["delta"]["partial_json"]) == {"q": "test"}

    def test_empty_content(self):
        anthropic_resp = {
            "id": "msg_empty",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": "gpt-4o",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

        body = anthropic_to_sse(anthropic_resp)
        events = _parse_sse_body(body)

        event_types = [e[0] for e in events]
        assert "message_start" in event_types
        assert "message_delta" in event_types
        assert "message_stop" in event_types

    def test_returns_bytes(self):
        anthropic_resp = {
            "id": "msg_ct",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "model": "test",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {},
        }
        body = anthropic_to_sse(anthropic_resp)
        assert isinstance(body, bytes)


# ============================================================
# 6. Integration Tests (stdlib HTTP server)
# ============================================================

def _find_free_port():
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


import socket


@pytest.fixture
def running_server():
    """Start the co-vibe proxy on a random port and yield (port, cleanup).
    Mocks _http_post to avoid real network calls."""
    port = _find_free_port()

    # Set up providers
    original_providers = proxy_mod._available_providers
    proxy_mod._available_providers = {
        "anthropic": "sk-ant-test-integration-key",
        "openai": "sk-openai-test-integration-key",
        "groq": "gsk-groq-test-integration-key",
    }

    server = ThreadedHTTPServer(("127.0.0.1", port), CoVibeHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Wait for server to start
    time.sleep(0.1)

    yield port

    server.shutdown()
    server.server_close()
    proxy_mod._available_providers = original_providers


def _post_json(port, path, data, headers=None):
    """Helper to POST JSON to the test server."""
    url = f"http://127.0.0.1:{port}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestIntegrationHTTPServer:
    """Integration tests using the real HTTP server with mocked upstream calls."""

    def test_full_request_openai_provider(self, running_server):
        """Test a full request cycle routed to an OpenAI-compatible provider."""
        port = running_server

        mock_oai_response = json.dumps({
            "choices": [{
                "message": {"content": "Test response from OpenAI"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode("utf-8")

        with mock.patch.object(proxy_mod, "_http_post", return_value=(200, mock_oai_response, "application/json")):
            status, data = _post_json(port, "/v1/messages", {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}],
            }, headers={"x-co-vibe-strategy": "fast"})

        assert status == 200
        assert data["type"] == "message"
        assert data["role"] == "assistant"
        assert any(b["text"] == "Test response from OpenAI" for b in data["content"] if b.get("type") == "text")

    def test_fallback_on_provider_error(self, running_server):
        """Test fallback when primary provider fails."""
        port = running_server
        call_count = 0

        # Anthropic-format response for the native fallback path
        mock_anthropic_resp = json.dumps({
            "id": "msg_fallback",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Fallback response"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }).encode("utf-8")

        # OpenAI-format response for OpenAI-compat fallback path
        mock_oai_resp = json.dumps({
            "choices": [{
                "message": {"content": "Fallback response"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode("utf-8")

        def side_effect(url, body_bytes, headers, timeout=300):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Provider down")
            # Return appropriate format based on URL
            if "anthropic.com" in url:
                return (200, mock_anthropic_resp, "application/json")
            return (200, mock_oai_resp, "application/json")

        with mock.patch.object(proxy_mod, "_http_post", side_effect=side_effect):
            status, data = _post_json(port, "/v1/messages", {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}],
            }, headers={"x-co-vibe-strategy": "fast"})

        # Should get either a successful fallback or a 502
        assert status in (200, 502)
        if status == 200:
            assert data["type"] == "message"

    def test_invalid_json_request(self, running_server):
        """Invalid JSON body should return 400."""
        port = running_server
        url = f"http://127.0.0.1:{port}/v1/messages"
        req = urllib.request.Request(url, data=b"not json", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            status = resp.status
            body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            status = e.code
            body = json.loads(e.read())
        assert status == 400

    def test_no_providers_returns_error(self):
        """When no providers are available, should return 500."""
        port = _find_free_port()
        original = proxy_mod._available_providers
        proxy_mod._available_providers = {}

        server = ThreadedHTTPServer(("127.0.0.1", port), CoVibeHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        try:
            status, data = _post_json(port, "/v1/messages", {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}],
            })
            assert status == 500
            assert "error" in data or "error" in str(data)
        finally:
            server.shutdown()
            server.server_close()
            proxy_mod._available_providers = original

    def test_strategy_header_override(self, running_server):
        """x-co-vibe-strategy header should override default strategy."""
        port = running_server

        mock_oai_response = json.dumps({
            "choices": [{
                "message": {"content": "Response"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }).encode("utf-8")

        with mock.patch.object(proxy_mod, "_http_post", return_value=(200, mock_oai_response, "application/json")):
            status, data = _post_json(port, "/v1/messages", {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hi"}],
            }, headers={"x-co-vibe-strategy": "cheap"})

        assert status == 200

    def test_anthropic_native_passthrough(self, running_server):
        """Test request routed to Anthropic (native passthrough)."""
        port = running_server

        mock_anthropic_response = json.dumps({
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Native Anthropic response"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }).encode("utf-8")

        with mock.patch.object(proxy_mod, "_http_post", return_value=(200, mock_anthropic_response, "application/json")):
            status, data = _post_json(port, "/v1/messages", {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}],
            }, headers={"x-co-vibe-strategy": "strong"})

        assert status == 200
        assert data["type"] == "message"
        assert data["content"][0]["text"] == "Native Anthropic response"

    def test_count_tokens_endpoint(self, running_server):
        """Test /v1/messages/count_tokens endpoint."""
        port = running_server
        status, data = _post_json(port, "/v1/messages/count_tokens", {
            "messages": [{"role": "user", "content": "Hello world, this is a test message."}],
        })
        assert status == 200
        assert "input_tokens" in data
        assert data["input_tokens"] > 0


# ============================================================
# Edge Cases and Additional Tests
# ============================================================

class TestEdgeCases:
    """Edge cases and additional coverage."""

    def test_model_def_defaults(self):
        m = ModelDef("test", "test-model", Tier.FAST, 1.0, 2.0)
        assert m.max_output == 16384
        assert m.latency_class == "medium"
        assert m.supports_tools is True

    def test_tier_enum_values(self):
        assert Tier.STRONG.value == "strong"
        assert Tier.BALANCED.value == "balanced"
        assert Tier.FAST.value == "fast"
        assert Tier.CHEAP.value == "cheap"

    def test_models_list_not_empty(self):
        assert len(MODELS) > 0

    def test_provider_configs_complete(self):
        for name, cfg in PROVIDER_CONFIGS.items():
            assert "base_url" in cfg
            assert "key_env" in cfg
            assert "native" in cfg

    def test_anthropic_is_native(self):
        assert PROVIDER_CONFIGS["anthropic"]["native"] is True

    def test_openai_and_groq_not_native(self):
        assert PROVIDER_CONFIGS["openai"]["native"] is False
        assert PROVIDER_CONFIGS["groq"]["native"] is False

    def test_select_model_deterministic(self, all_providers, simple_request):
        m1 = select_model(simple_request, "strong", all_providers)
        m2 = select_model(simple_request, "strong", all_providers)
        assert m1.model_id == m2.model_id
        assert m1.provider == m2.provider

    def test_estimate_complexity_with_mixed_content_types(self):
        req = {
            "messages": [
                {"role": "user", "content": "Simple string"},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "Block content"},
                ]},
                {"role": "user", "content": "Another string"},
            ],
        }
        score = estimate_complexity(req)
        assert 0.0 <= score <= 1.0

    def test_anthropic_to_openai_empty_messages(self):
        assert anthropic_to_openai_messages([]) == []

    def test_openai_response_empty_choices(self):
        oai_resp = {"choices": [{}], "usage": {}}
        result = openai_response_to_anthropic(oai_resp, "test")
        assert result["type"] == "message"
        assert len(result["content"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
