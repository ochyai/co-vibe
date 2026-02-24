#!/usr/bin/env python3
"""
co-vibe: Multi-provider AI orchestrator proxy for Claude Code
Claude Code CLI -> co-vibe-proxy -> Anthropic / OpenAI / Groq

Routes requests to the best provider/model based on complexity,
cost, and speed preferences.

Pure Python stdlib - no external dependencies required.
Based on ochyai/vibe-local proxy architecture.
"""

import json
import http.server
import urllib.request
import urllib.error
import urllib.parse
import ssl
import os
import sys
import time
import uuid
import threading
import socket
import datetime
import shutil
import traceback
from dataclasses import dataclass
from enum import Enum

# ============================================================
# .env loader (minimal, no dependencies)
# ============================================================

def load_dotenv(path=None):
    """Load .env file into os.environ."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and not key.startswith("#"):
                os.environ.setdefault(key, value)

load_dotenv()

# ============================================================
# Configuration
# ============================================================

PROXY_PORT = int(os.environ.get("CO_VIBE_PORT", "8090"))
DEBUG_MODE = os.environ.get("CO_VIBE_DEBUG", "0") == "1"
STRATEGY = os.environ.get("CO_VIBE_STRATEGY", "auto")

# --- Session logging (like vibe-local) ---
LOG_DIR = os.path.join(os.path.expanduser("~"), ".local", "state", "co-vibe", "proxy-debug")
os.makedirs(LOG_DIR, mode=0o700, exist_ok=True)
_session_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_DIR = os.path.join(LOG_DIR, f"session_{_session_ts}")
os.makedirs(SESSION_DIR, mode=0o700, exist_ok=True)

# --- Tool filtering (from vibe-local: filter tools that confuse non-Anthropic models) ---
ALLOWED_TOOLS_FOR_OPENAI = {
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebFetch", "WebSearch", "NotebookEdit",
}

def _session_log(tag, data, req_id=0):
    """Write metadata log to session directory."""
    ts = datetime.datetime.now().strftime("%H%M%S")
    prefix = f"{req_id:04d}_{ts}" if req_id else ts
    path = os.path.join(SESSION_DIR, f"{prefix}_{tag}.json")
    try:
        with open(path, "w") as f:
            if isinstance(data, (dict, list)):
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(data))
    except Exception:
        pass

def _cleanup_old_sessions(max_age_days=7):
    """Remove sessions older than max_age_days."""
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    cleaned = 0
    try:
        for entry in os.listdir(LOG_DIR):
            if not entry.startswith("session_"):
                continue
            entry_path = os.path.join(LOG_DIR, entry)
            if os.path.isdir(entry_path) and os.path.getmtime(entry_path) < cutoff:
                shutil.rmtree(entry_path, ignore_errors=True)
                cleaned += 1
    except Exception:
        pass
    if cleaned:
        print(f"[co-vibe] Cleaned {cleaned} old session(s)")

# ============================================================
# Model & Provider definitions
# ============================================================

class Tier(Enum):
    STRONG = "strong"
    BALANCED = "balanced"
    FAST = "fast"
    CHEAP = "cheap"

@dataclass
class ModelDef:
    provider: str
    model_id: str
    tier: Tier
    input_cost_per_mtok: float
    output_cost_per_mtok: float
    max_output: int = 16384
    latency_class: str = "medium"
    supports_tools: bool = True

MODELS = [
    # Anthropic
    ModelDef("anthropic", "claude-opus-4-6",           Tier.STRONG,   15.0, 75.0,  32768, "slow"),
    ModelDef("anthropic", "claude-sonnet-4-6",         Tier.BALANCED,  3.0, 15.0,  16384, "medium"),
    ModelDef("anthropic", "claude-haiku-4-5-20251001", Tier.FAST,      0.8,  4.0,   8192, "fast"),
    # OpenAI
    ModelDef("openai", "gpt-4o",                       Tier.BALANCED,  2.5, 10.0,  16384, "medium"),
    ModelDef("openai", "gpt-4o-mini",                  Tier.FAST,     0.15,  0.6,  16384, "fast"),
    ModelDef("openai", "o3",                           Tier.STRONG,   10.0, 40.0,  32768, "slow"),
    # Groq
    ModelDef("groq", "llama-3.3-70b-versatile",        Tier.FAST,     0.59, 0.79,  8192, "fast"),
    ModelDef("groq", "llama-3.1-8b-instant",           Tier.CHEAP,    0.05, 0.08,  8192, "fast"),
    ModelDef("groq", "gemma2-9b-it",                   Tier.CHEAP,    0.20, 0.20,  8192, "fast"),
]

PROVIDER_CONFIGS = {
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "key_env": "ANTHROPIC_API_KEY",
        "native": True,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "native": False,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "native": False,
    },
}

# Model overrides
_strong_override = os.environ.get("CO_VIBE_STRONG_MODEL")
_fast_override = os.environ.get("CO_VIBE_FAST_MODEL")
_cheap_override = os.environ.get("CO_VIBE_CHEAP_MODEL")

# ============================================================
# Provider & model helpers
# ============================================================

def get_available_providers():
    available = {}
    for name, cfg in PROVIDER_CONFIGS.items():
        key = os.environ.get(cfg["key_env"], "")
        if key and len(key) > 5:
            available[name] = key
    return available

def get_available_models(available_providers):
    return [m for m in MODELS if m.provider in available_providers]

# ============================================================
# Smart Router
# ============================================================

def estimate_complexity(req):
    """Score 0.0 (trivial) to 1.0 (very complex)."""
    score = 0.0
    messages = req.get("messages", [])

    msg_count = len(messages)
    if msg_count > 20:
        score += 0.3
    elif msg_count > 8:
        score += 0.2
    elif msg_count > 3:
        score += 0.1

    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(block.get("text", ""))
                    if block.get("type") in ("tool_result", "tool_use"):
                        score += 0.05
        else:
            total_chars += len(str(content))

    if total_chars > 50000:
        score += 0.3
    elif total_chars > 15000:
        score += 0.2
    elif total_chars > 5000:
        score += 0.1

    tools = req.get("tools", [])
    if len(tools) > 10:
        score += 0.2
    elif len(tools) > 0:
        score += 0.1

    system = req.get("system", "")
    sys_len = sum(len(b.get("text", "")) for b in system if isinstance(b, dict)) if isinstance(system, list) else len(str(system))
    if sys_len > 8000:
        score += 0.1

    return min(score, 1.0)


def select_model(req, strategy, available):
    """Select best model based on strategy."""
    models = get_available_models(available)
    if not models:
        raise ValueError("No models available. Check your API keys.")

    # Overrides
    override_map = {"strong": _strong_override, "fast": _fast_override, "cheap": _cheap_override}
    override = override_map.get(strategy)
    if override:
        for m in models:
            if m.model_id == override:
                return m

    if strategy == "strong":
        priority = [Tier.STRONG, Tier.BALANCED, Tier.FAST, Tier.CHEAP]
        models.sort(key=lambda m: (priority.index(m.tier), -m.output_cost_per_mtok))
        return models[0]

    elif strategy == "fast":
        models.sort(key=lambda m: (0 if m.latency_class == "fast" else 1 if m.latency_class == "medium" else 2, m.input_cost_per_mtok))
        return models[0]

    elif strategy == "cheap":
        models.sort(key=lambda m: m.input_cost_per_mtok + m.output_cost_per_mtok)
        return models[0]

    else:  # auto
        complexity = estimate_complexity(req)
        if complexity >= 0.6:
            candidates = [m for m in models if m.tier in (Tier.STRONG, Tier.BALANCED)]
            if candidates:
                candidates.sort(key=lambda m: (0 if m.tier == Tier.STRONG else 1, -m.output_cost_per_mtok))
                return candidates[0]
        elif complexity >= 0.3:
            candidates = [m for m in models if m.tier in (Tier.BALANCED, Tier.FAST)]
            if candidates:
                candidates.sort(key=lambda m: (0 if m.tier == Tier.BALANCED else 1))
                return candidates[0]
        else:
            candidates = [m for m in models if m.tier in (Tier.FAST, Tier.CHEAP)]
            if candidates:
                candidates.sort(key=lambda m: (0 if m.latency_class == "fast" else 1, m.input_cost_per_mtok))
                return candidates[0]
        return models[0]

# ============================================================
# Format converters (Anthropic <-> OpenAI)
# ============================================================

def anthropic_to_openai_messages(messages):
    """Convert Anthropic message format to OpenAI format."""
    oai = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts, tool_calls_out, tool_results = [], [], []
            for block in content:
                if not isinstance(block, dict):
                    text_parts.append(str(block))
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "thinking":
                    pass
                elif btype == "tool_use":
                    tool_calls_out.append({
                        "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    })
                elif btype == "tool_result":
                    rc = block.get("content", "")
                    if isinstance(rc, list):
                        rc = "\n".join(b.get("text", str(b)) for b in rc if isinstance(b, dict))
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": str(rc),
                    })
            if tool_results:
                oai.extend(tool_results)
                continue
            if tool_calls_out:
                oai.append({"role": "assistant", "content": "\n".join(text_parts) if text_parts else None, "tool_calls": tool_calls_out})
                continue
            oai.append({"role": role, "content": "\n".join(text_parts)})
        else:
            oai.append({"role": role, "content": content})
    return oai


def anthropic_tools_to_openai(tools):
    return [{"type": "function", "function": {"name": t.get("name", ""), "description": t.get("description", "")[:1024], "parameters": t.get("input_schema", {})}} for t in tools]


def openai_response_to_anthropic(oai_resp, model_id):
    """Convert OpenAI response to Anthropic Messages format."""
    choice = oai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})
    content_text = message.get("content", "") or ""
    tool_calls = message.get("tool_calls", [])
    finish_reason = choice.get("finish_reason", "stop")

    blocks = []
    if content_text:
        blocks.append({"type": "text", "text": content_text})
    for tc in tool_calls:
        func = tc.get("function", {})
        try:
            inp = json.loads(func.get("arguments", "{}"))
        except json.JSONDecodeError:
            inp = {"raw": func.get("arguments", "")}
        blocks.append({"type": "tool_use", "id": f"toolu_{uuid.uuid4().hex[:24]}", "name": func.get("name", ""), "input": inp})

    if not blocks:
        blocks.append({"type": "text", "text": ""})

    usage = oai_resp.get("usage", {})
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message", "role": "assistant",
        "content": blocks, "model": model_id,
        "stop_reason": "tool_use" if finish_reason == "tool_calls" else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        },
    }


def anthropic_to_sse(resp):
    """Convert Anthropic sync response to SSE event stream bytes."""
    events = []
    msg_start = dict(resp)
    msg_start["content"] = []
    events.append(("message_start", {"type": "message_start", "message": msg_start}))

    for i, block in enumerate(resp.get("content", [])):
        btype = block.get("type", "text")
        if btype == "text":
            events.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}))
            events.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": block.get("text", "")}}))
            events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
        elif btype == "tool_use":
            events.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
            events.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block.get("input", {}), ensure_ascii=False)}}))
            events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))

    events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": resp.get("stop_reason", "end_turn"), "stop_sequence": None}, "usage": {"output_tokens": resp.get("usage", {}).get("output_tokens", 0)}}))
    events.append(("message_stop", {"type": "message_stop"}))

    body = ""
    for etype, data in events:
        body += f"event: {etype}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    return body.encode("utf-8")

# ============================================================
# Global state (thread-safe)
# ============================================================

_counter_lock = threading.Lock()
_request_counter = 0
_total_cost = 0.0
_cost_lock = threading.Lock()
_request_stats = {"total": 0, "by_provider": {}, "by_model": {}}
_stats_lock = threading.Lock()
_available_providers = {}
_ssl_ctx = ssl.create_default_context()


def _next_id():
    global _request_counter
    with _counter_lock:
        _request_counter += 1
        return _request_counter


def _add_cost(cost):
    global _total_cost
    with _cost_lock:
        _total_cost += cost


def _add_stat(provider, model_id):
    with _stats_lock:
        _request_stats["total"] += 1
        _request_stats["by_provider"][provider] = _request_stats["by_provider"].get(provider, 0) + 1
        _request_stats["by_model"][model_id] = _request_stats["by_model"].get(model_id, 0) + 1


def _log(tag, data, req_id=0):
    if DEBUG_MODE or tag.startswith("route") or tag == "startup":
        ts = time.strftime("%H:%M:%S")
        summary = json.dumps(data, ensure_ascii=False)[:200] if isinstance(data, dict) else str(data)[:200]
        print(f"[co-vibe][{ts}][#{req_id:04d}] {tag}: {summary}")

# ============================================================
# HTTP helpers
# ============================================================

def _http_post(url, body_bytes, headers, timeout=300):
    """Make HTTP POST, return (status, response_bytes, content_type)."""
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx)
        return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), "application/json"
    except Exception as e:
        raise


def _http_post_stream(url, body_bytes, headers, timeout=300):
    """Make HTTP POST, return response object for streaming."""
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx)

# ============================================================
# Main Handler
# ============================================================

class CoVibeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if DEBUG_MODE:
            print(f"[co-vibe][http] {args[0]}" if args else "")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._json_response(200, {
                "status": "ok", "proxy": "co-vibe", "strategy": STRATEGY,
                "providers": list(_available_providers.keys()),
                "stats": _request_stats,
                "total_cost": f"${_total_cost:.4f}",
            })
        elif path == "/v1/models":
            models = get_available_models(_available_providers)
            self._json_response(200, {"data": [
                {"id": m.model_id, "provider": m.provider, "tier": m.tier.value,
                 "latency": m.latency_class, "cost_input": m.input_cost_per_mtok, "cost_output": m.output_cost_per_mtok}
                for m in models
            ]})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            req = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._json_response(400, {"error": "invalid JSON"})
            return

        if path == "/v1/messages":
            self._handle_messages(req)
        elif path == "/v1/messages/count_tokens":
            self._handle_count_tokens(req)
        else:
            self._json_response(404, {"error": f"unknown path: {path}"})

    def _handle_messages(self, req):
        req_id = _next_id()
        t_start = time.time()
        stream = req.get("stream", False)

        # Strategy from header or global
        strategy = self.headers.get("x-co-vibe-strategy", STRATEGY)

        try:
            selected = select_model(req, strategy, _available_providers)
        except ValueError as e:
            self._json_response(500, {"type": "error", "error": {"type": "api_error", "message": str(e)}})
            return

        complexity = estimate_complexity(req)
        _log("route", {
            "model": selected.model_id, "provider": selected.provider,
            "tier": selected.tier.value, "strategy": strategy,
            "complexity": round(complexity, 2),
            "msgs": len(req.get("messages", [])),
            "tools": len(req.get("tools", [])),
        }, req_id)
        _session_log("route", {
            "model": selected.model_id, "provider": selected.provider,
            "tier": selected.tier.value, "strategy": strategy,
            "complexity": round(complexity, 2),
        }, req_id)
        _add_stat(selected.provider, selected.model_id)

        provider_cfg = PROVIDER_CONFIGS[selected.provider]
        api_key = _available_providers[selected.provider]

        try:
            if provider_cfg["native"]:
                self._proxy_anthropic(req, selected, api_key, stream, req_id, t_start)
            else:
                self._proxy_openai(req, selected, provider_cfg, api_key, stream, req_id, t_start)
        except Exception as e:
            _log("error", {"provider": selected.provider, "error": str(e)}, req_id)
            # Try fallback
            if not self._try_fallback(req, selected, stream, req_id, t_start):
                self._json_response(502, {"type": "error", "error": {"type": "api_error", "message": str(e)}})

    def _proxy_anthropic(self, req, model, api_key, stream, req_id, t_start):
        """Native Anthropic passthrough - zero conversion overhead."""
        req["model"] = model.model_id
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = json.dumps(req, ensure_ascii=False).encode("utf-8")
        url = "https://api.anthropic.com/v1/messages"

        if stream:
            # Stream passthrough
            try:
                upstream = _http_post_stream(url, body, headers)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                while True:
                    chunk = upstream.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

                elapsed = int((time.time() - t_start) * 1000)
                _log("done", {"provider": "anthropic", "model": model.model_id, "ms": elapsed, "mode": "stream"}, req_id)
            except urllib.error.HTTPError as e:
                error_body = e.read()
                _log("error", {"status": e.code, "body": error_body.decode()[:300]}, req_id)
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(error_body)
        else:
            status, resp_body, ct = _http_post(url, body, headers)
            elapsed = int((time.time() - t_start) * 1000)

            if status == 200:
                resp_data = json.loads(resp_body)
                usage = resp_data.get("usage", {})
                cost = (usage.get("input_tokens", 0) * model.input_cost_per_mtok / 1_000_000 +
                        usage.get("output_tokens", 0) * model.output_cost_per_mtok / 1_000_000)
                _add_cost(cost)
                _log("done", {"provider": "anthropic", "model": model.model_id, "ms": elapsed, "cost": f"${cost:.6f}", "total": f"${_total_cost:.4f}"}, req_id)
            else:
                _log("error", {"status": status, "body": resp_body.decode()[:300]}, req_id)

            self.send_response(status)
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(resp_body)

    def _proxy_openai(self, req, model, provider_cfg, api_key, stream, req_id, t_start):
        """Route to OpenAI-compatible provider with format conversion."""
        url = f"{provider_cfg['base_url']}/chat/completions"

        # Build OpenAI request
        oai_messages = []
        system = req.get("system", "")
        if system:
            sys_text = "\n".join(b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text") if isinstance(system, list) else str(system)
            oai_messages.append({"role": "system", "content": sys_text})
        oai_messages.extend(anthropic_to_openai_messages(req.get("messages", [])))

        oai_req = {
            "model": model.model_id,
            "messages": oai_messages,
            "max_tokens": min(req.get("max_tokens", 8192), model.max_output),
            "temperature": req.get("temperature", 0.7),
            "stream": False,
        }
        tools = req.get("tools", [])
        if tools and model.supports_tools:
            # Filter tools for non-Anthropic providers (like vibe-local)
            filtered = [t for t in tools if t.get("name", "") in ALLOWED_TOOLS_FOR_OPENAI]
            if len(filtered) != len(tools):
                _log("filter", {"original": len(tools), "filtered": len(filtered)}, req_id)
            oai_req["tools"] = anthropic_tools_to_openai(filtered)
            if filtered:
                oai_req["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        body = json.dumps(oai_req, ensure_ascii=False).encode("utf-8")

        status, resp_body, _ = _http_post(url, body, headers)
        elapsed = int((time.time() - t_start) * 1000)

        if status != 200:
            _log("error", {"provider": model.provider, "status": status, "body": resp_body.decode()[:300]}, req_id)
            raise RuntimeError(f"{model.provider} returned {status}")

        oai_resp = json.loads(resp_body)
        anthropic_resp = openai_response_to_anthropic(oai_resp, model.model_id)

        usage = anthropic_resp.get("usage", {})
        cost = (usage.get("input_tokens", 0) * model.input_cost_per_mtok / 1_000_000 +
                usage.get("output_tokens", 0) * model.output_cost_per_mtok / 1_000_000)
        _add_cost(cost)
        _log("done", {"provider": model.provider, "model": model.model_id, "ms": elapsed, "cost": f"${cost:.6f}", "total": f"${_total_cost:.4f}"}, req_id)

        if stream:
            sse_body = anthropic_to_sse(anthropic_resp)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(sse_body)
            self.wfile.flush()
        else:
            self._json_response(200, anthropic_resp)

    def _try_fallback(self, req, failed_model, stream, req_id, t_start):
        """Try another provider when one fails. Returns True if fallback succeeded."""
        fallback_models = [m for m in get_available_models(_available_providers)
                           if m.provider != failed_model.provider and m.tier in (failed_model.tier, Tier.BALANCED)]
        if not fallback_models:
            return False

        fallback = fallback_models[0]
        _log("fallback", {"from": f"{failed_model.provider}/{failed_model.model_id}", "to": f"{fallback.provider}/{fallback.model_id}"}, req_id)

        provider_cfg = PROVIDER_CONFIGS[fallback.provider]
        api_key = _available_providers[fallback.provider]

        try:
            if provider_cfg["native"]:
                self._proxy_anthropic(req, fallback, api_key, stream, req_id, t_start)
            else:
                self._proxy_openai(req, fallback, provider_cfg, api_key, stream, req_id, t_start)
            return True
        except Exception as e:
            _log("fallback_error", {"error": str(e)}, req_id)
            return False

    def _handle_count_tokens(self, req):
        total = 0
        for msg in req.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        total += len(block.get("text", "")) // 4
            else:
                total += len(str(content)) // 4
        system = req.get("system", "")
        if isinstance(system, list):
            for b in system:
                if isinstance(b, dict):
                    total += len(b.get("text", "")) // 4
        elif system:
            total += len(str(system)) // 4
        self._json_response(200, {"input_tokens": total})

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_sse(self, event_type, data):
        try:
            line = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
        except BrokenPipeError:
            pass


# ============================================================
# Threaded server (same pattern as vibe-local)
# ============================================================

class ThreadedHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        host, port = self.server_address
        self.server_name = host
        self.server_port = port

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


# ============================================================
# Entry point
# ============================================================

def main():
    global _available_providers
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PROXY_PORT
    _available_providers = get_available_providers()

    if not _available_providers:
        print("[co-vibe] ERROR: No API keys configured!")
        print("[co-vibe] Run: python3 setup.py")
        sys.exit(1)

    models = get_available_models(_available_providers)

    print(f"")
    print(f"  co-vibe proxy on http://127.0.0.1:{port}")
    print(f"  Strategy: {STRATEGY}")
    print(f"  Providers: {', '.join(_available_providers.keys())}")
    print(f"  Models: {len(models)} available")
    print(f"  Debug: {'ON' if DEBUG_MODE else 'OFF'}")
    print(f"  Session: {os.path.basename(SESSION_DIR)}")
    print(f"  Ctrl+C to stop")
    print(f"")

    _cleanup_old_sessions(7)

    _log("startup", {
        "providers": list(_available_providers.keys()),
        "models": [m.model_id for m in models],
        "strategy": STRATEGY, "port": port,
    })

    server = ThreadedHTTPServer(("127.0.0.1", port), CoVibeHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[co-vibe] stopped")
        server.server_close()


if __name__ == "__main__":
    main()
