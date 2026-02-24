#!/usr/bin/env python3
"""
co-vibe setup wizard - Vaporwave Edition
Multi-provider AI Orchestrator setup with aesthetic TUI
Pure Python - no external dependencies
"""

import os
import sys
import json
import time
import platform
import threading
import urllib.request
import urllib.error

# =============================================
# VAPORWAVE COLOR PALETTE (ANSI 256-color)
# =============================================

PINK = '\033[38;5;198m'
HOT_PINK = '\033[38;5;206m'
MAGENTA = '\033[38;5;165m'
PURPLE = '\033[38;5;141m'
CYAN = '\033[38;5;51m'
AQUA = '\033[38;5;87m'
MINT = '\033[38;5;121m'
CORAL = '\033[38;5;210m'
ORANGE = '\033[38;5;208m'
YELLOW = '\033[38;5;226m'
WHITE = '\033[38;5;255m'
GRAY = '\033[38;5;245m'
RED = '\033[38;5;196m'
GREEN = '\033[38;5;46m'
NEON_GREEN = '\033[38;5;118m'
BLUE = '\033[38;5;33m'

BOLD = '\033[1m'
DIM = '\033[2m'
NC = '\033[0m'

GRADIENT_NEON = [46, 47, 48, 49, 50, 51, 45, 39, 33, 27, 21, 57, 93, 129, 165, 201, 200, 199, 198, 197, 196]
GRADIENT_VAPOR = [51, 87, 123, 159, 195, 189, 183, 177, 171, 165]
GRADIENT_PROGRESS = [198, 199, 207, 213, 177, 171, 165, 129, 93, 57, 51, 50, 49, 48, 47, 46]

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
TOTAL_STEPS = 5

PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "key_prefix": "sk-ant-",
        "env_var": "ANTHROPIC_API_KEY",
        "test_url": "https://api.anthropic.com/v1/messages",
        "models": ["Opus 4.6", "Sonnet 4.6", "Haiku 4.5"],
        "signup": "https://console.anthropic.com/",
        "icon": "🤖",
        "color": PURPLE,
    },
    "openai": {
        "name": "OpenAI (GPT-4o)",
        "key_prefix": "sk-",
        "env_var": "OPENAI_API_KEY",
        "test_url": "https://api.openai.com/v1/models",
        "models": ["GPT-4o", "GPT-4o-mini", "o3"],
        "signup": "https://platform.openai.com/api-keys",
        "icon": "💚",
        "color": NEON_GREEN,
    },
    "groq": {
        "name": "Groq (Ultra-Fast)",
        "key_prefix": "gsk_",
        "env_var": "GROQ_API_KEY",
        "test_url": "https://api.groq.com/openai/v1/models",
        "models": ["Llama 3.3 70B", "Llama 3.1 8B"],
        "signup": "https://console.groq.com/keys",
        "icon": "⚡",
        "color": CYAN,
    },
}

STRATEGIES = {
    "auto": {
        "desc": "Auto-select based on request complexity",
        "detail": "Simple->Fast, Complex->Strong",
        "badge": "RECOMMENDED",
        "badge_color": NEON_GREEN,
    },
    "strong": {
        "desc": "Always use strongest model",
        "detail": "Opus > o3 > Sonnet",
        "badge": "QUALITY",
        "badge_color": PURPLE,
    },
    "fast": {
        "desc": "Fastest response time",
        "detail": "Groq > Haiku > GPT-4o-mini",
        "badge": "SPEED",
        "badge_color": CYAN,
    },
    "cheap": {
        "desc": "Minimize cost",
        "detail": "Haiku > GPT-4o-mini > Groq",
        "badge": "BUDGET",
        "badge_color": YELLOW,
    },
}


# =============================================
# VAPORWAVE RENDERING ENGINE
# =============================================

def rainbow_text(text):
    """Render text with neon gradient colors."""
    colors = GRADIENT_NEON
    result = ""
    ci = 0
    for ch in text:
        if ch == ' ':
            result += ch
        else:
            result += f"\033[38;5;{colors[ci % len(colors)]}m{ch}"
            ci += 1
    return result + NC


def vapor_text(text):
    """Render text with vaporwave gradient."""
    colors = GRADIENT_VAPOR
    result = ""
    length = max(len(text.replace(' ', '')), 1)
    ci = 0
    for ch in text:
        if ch == ' ':
            result += ch
        else:
            idx = (ci * len(colors) // length) % len(colors)
            result += f"\033[38;5;{colors[idx]}m{ch}"
            ci += 1
    return result + NC


def heart_line():
    """Print a decorative heart divider line."""
    colors = [PINK, MAGENTA, PURPLE, CYAN, AQUA, MINT, NEON_GREEN,
              YELLOW, ORANGE, CORAL, HOT_PINK, PINK, MAGENTA, PURPLE, CYAN, AQUA]
    line = "  "
    for c in colors:
        line += f"{c}*{NC}"
    print(line)


def vapor_box(title, color=CYAN):
    """Print a vaporwave-styled section box."""
    w = 56
    print(f"  {color}{'=' * w}{NC}")
    padding = (w - len(title) - 2) // 2
    print(f"  {color}{'=' * padding} {BOLD}{WHITE}{title}{NC} {color}{'=' * padding}{NC}")
    print(f"  {color}{'=' * w}{NC}")


def step_header(num, title):
    """Print step header with vaporwave styling."""
    icons = ["🔍", "🔑", "🎯", "⚙\ufe0f", "💾"]
    step_colors = [51, 87, 165, 171, 198]
    icon = icons[num - 1] if num <= len(icons) else "🔮"
    c = step_colors[num - 1] if num <= len(step_colors) else 51

    print()
    print(f"  \033[38;5;{c}m{'━' * 56}{NC}")
    print(f"  {icon}  \033[38;5;{c}m{BOLD}STEP {num}/{TOTAL_STEPS}{NC}  {BOLD}{WHITE}{title}{NC}")
    print(f"  \033[38;5;{c}m{'━' * 56}{NC}")
    print()


def vapor_success(msg):
    print(f"  {NEON_GREEN}|{NC} ✅ {BOLD}{MINT}{msg}{NC}")


def vapor_info(msg):
    print(f"  {CYAN}|{NC} 💠 {AQUA}{msg}{NC}")


def vapor_warn(msg):
    print(f"  {ORANGE}|{NC} ⚠  {YELLOW}{msg}{NC}")


def vapor_error(msg):
    print(f"  {RED}|{NC} 💀 {RED}{BOLD}{msg}{NC}")


def progress_bar(label, duration=1.0, width=40):
    """Animated vaporwave progress bar."""
    colors = GRADIENT_PROGRESS
    num_colors = len(colors)
    bar_chars = ["░", "▒", "▓", "█"]
    sparkles = ["✨", "💎", "🔮", "💜", "🌸", "🎵", "🌊", "⚡"]
    steps = max(int(duration * 20), 10)

    for s in range(steps + 1):
        pct = s * 100 // steps
        filled = s * width // steps
        empty = width - filled

        spark = sparkles[s % len(sparkles)]

        bar = ""
        for b in range(filled):
            ci = b * num_colors // width
            bar += f"\033[38;5;{colors[ci]}m█"

        if filled < width:
            anim_idx = s % 4
            ci = filled * num_colors // width
            bar += f"\033[38;5;{colors[ci]}m{bar_chars[anim_idx]}"
            empty -= 1

        for _ in range(max(0, empty)):
            bar += f"\033[38;5;237m░"

        sys.stdout.write(
            f"\r  {spark} {BOLD}{CYAN}{label:<30s}{NC} {MAGENTA}▐{NC}{bar}{MAGENTA}▌{NC} "
            f"{BOLD}{NEON_GREEN}{pct:3d}%{NC} {spark} "
        )
        sys.stdout.flush()
        time.sleep(0.05)

    # Complete state
    bar = ""
    for b in range(width):
        ci = b * num_colors // width
        bar += f"\033[38;5;{colors[ci]}m█"
    sys.stdout.write(
        f"\r  ✅ {BOLD}{GREEN}{label:<30s}{NC} {MAGENTA}▐{NC}{bar}{MAGENTA}▌{NC} "
        f"{BOLD}{NEON_GREEN}100%{NC} 🎉 \n"
    )
    sys.stdout.flush()


class Spinner:
    """Animated spinner for async operations."""

    def __init__(self, label):
        self.label = label
        self.running = False
        self.thread = None
        self.sparkles = ["✨", "💎", "🔮", "💜", "🌸", "🎵", "🌊", "⚡", "🔥", "💫"]
        self.colors = [198, 171, 165, 129, 93, 57, 51, 50, 49, 48]

    def __enter__(self):
        self.running = True
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write(f"\r{' ' * 70}\r")
        sys.stdout.flush()

    def _animate(self):
        sec = 0
        while self.running:
            si = sec % len(self.sparkles)
            ci = sec % len(self.colors)
            elapsed = sec // 2
            sys.stdout.write(
                f"\r  {self.sparkles[si]} "
                f"\033[38;5;{self.colors[ci]}m{BOLD}{self.label:<35s}{NC} "
                f"{DIM}{GRAY}{elapsed}s{NC}  "
            )
            sys.stdout.flush()
            time.sleep(0.5)
            sec += 1


# =============================================
# SYSTEM DETECTION
# =============================================

def get_system_info():
    """Gather system information."""
    info = {
        "os": platform.system(),
        "os_version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "ram_gb": "?",
    }

    if platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            ram_bytes = int(result.stdout.strip())
            info["ram_gb"] = str(ram_bytes // (1024 ** 3))
        except Exception:
            pass
    elif platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        info["ram_gb"] = str(kb // (1024 * 1024))
                        break
        except Exception:
            pass

    return info


# =============================================
# API KEY TESTING
# =============================================

def test_anthropic_key(api_key):
    """Test Anthropic API key with a minimal request."""
    try:
        data = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        urllib.request.urlopen(req, timeout=10)
        return True, "Key valid", ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key (401 Unauthorized)", []
        elif e.code == 429:
            return True, "Key valid (rate limited)", ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
        return False, f"HTTP {e.code}", []
    except Exception as e:
        return False, str(e), []


def test_openai_key(api_key):
    """Test OpenAI API key and list models."""
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        model_ids = [m["id"] for m in body.get("data", [])]
        highlight = [m for m in model_ids if any(k in m for k in ["gpt-4o", "o3", "o1"])]
        return True, "Key valid", highlight[:6]
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key (401 Unauthorized)", []
        return True, f"HTTP {e.code} (key may be valid)", []
    except Exception as e:
        return False, str(e), []


def test_groq_key(api_key):
    """Test Groq API key and list models."""
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        model_ids = [m["id"] for m in body.get("data", [])]
        highlight = [m for m in model_ids if any(k in m for k in ["llama", "mixtral", "gemma"])]
        return True, "Key valid", highlight[:6]
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key (401 Unauthorized)", []
        return True, f"HTTP {e.code} (key may be valid)", []
    except Exception as e:
        return False, str(e), []


TEST_FUNCS = {
    "anthropic": test_anthropic_key,
    "openai": test_openai_key,
    "groq": test_groq_key,
}


# =============================================
# FILE I/O
# =============================================

def load_existing_env():
    """Load existing .env values."""
    existing = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip().strip("\"'")
    return existing


def mask_key(key):
    """Show first 8 and last 4 chars of a key."""
    if len(key) <= 12:
        return key[:4] + "..." + key[-2:]
    return key[:8] + "..." + key[-4:]


def write_env(keys, strategy, port=8090):
    """Write .env file."""
    lines = [
        "# co-vibe configuration",
        "# Generated by setup wizard (vaporwave edition)",
        "",
    ]

    for pid, info in PROVIDERS.items():
        env_var = info["env_var"]
        if env_var in keys:
            lines.append(f"{env_var}={keys[env_var]}")
        else:
            lines.append(f"# {env_var}=")

    lines.extend([
        "",
        f"CO_VIBE_STRATEGY={strategy}",
        f"CO_VIBE_PORT={port}",
        "# CO_VIBE_DEBUG=1",
    ])

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(ENV_PATH, 0o600)


# =============================================
# INTERACTIVE STEPS
# =============================================

def clear():
    os.system("clear" if os.name != "nt" else "cls")


def show_banner():
    """Display the vaporwave ASCII art banner."""
    print()
    heart_line()
    print()
    print(f"{MAGENTA}{BOLD}", end="")
    banner_art = r"""
     ██████╗ ██████╗        ██╗   ██╗██╗██████╗ ███████╗
    ██╔════╝██╔═══██╗       ██║   ██║██║██╔══██╗██╔════╝
    ██║     ██║   ██║ █████╗██║   ██║██║██████╔╝█████╗
    ██║     ██║   ██║ ╚════╝╚██╗ ██╔╝██║██╔══██╗██╔══╝
    ╚██████╗╚██████╔╝        ╚████╔╝ ██║██████╔╝███████╗
     ╚═════╝ ╚═════╝          ╚═══╝  ╚═╝╚═════╝ ╚══════╝"""
    print(banner_art)
    print(NC)
    print(f"  {vapor_text('Multi-Provider AI Orchestrator Setup')}")
    print()
    heart_line()
    print()

    # Boot sequence
    boot_msgs = [
        (CYAN, "Initializing vaporwave subsystem..."),
        (PURPLE, "Loading aesthetic modules..."),
        (PINK, "Calibrating neon frequencies..."),
    ]
    for color, msg in boot_msgs:
        print(f"  {DIM}{color}{msg}{NC}")
        time.sleep(0.2)
    print(f"  {BOLD}{NEON_GREEN}  ▶ SYSTEM ONLINE{NC}")
    print()


def step1_system_info():
    """Step 1: Show system information."""
    step_header(1, "SYSTEM INFO")

    progress_bar("Scanning hardware...", 0.8)
    print()

    info = get_system_info()

    # OS info
    os_label = info["os"]
    if info["os"] == "Darwin":
        os_label = f"macOS {info['os_version']}"
    elif info["os"] == "Linux":
        os_label = f"Linux {info['os_version']}"

    # Display table
    print(f"  {PURPLE}|{NC} {BOLD}{WHITE}System Overview{NC}")
    print(f"  {PURPLE}|{NC}")
    print(f"  {PURPLE}|{NC}   {'OS':<16s} {NEON_GREEN}{os_label}{NC}")
    print(f"  {PURPLE}|{NC}   {'Architecture':<16s} {NEON_GREEN}{info['arch']}{NC}")
    print(f"  {PURPLE}|{NC}   {'Python':<16s} {NEON_GREEN}{info['python']}{NC}")

    # RAM with bar
    ram_gb = info["ram_gb"]
    if ram_gb != "?":
        ram_num = int(ram_gb)
        bar_width = 30
        max_display = 128
        filled = min(ram_num * bar_width // max_display, bar_width)
        empty = bar_width - filled
        ram_bar = f"{NEON_GREEN}{'█' * filled}{NC}\033[38;5;237m{'░' * empty}{NC}"
        print(f"  {PURPLE}|{NC}   {'RAM':<16s} {NEON_GREEN}{ram_gb}GB{NC}")
        print(f"  {PURPLE}|{NC}   {'':16s} {CYAN}▐{NC}{ram_bar}{CYAN}▌{NC} {DIM}{GRAY}({ram_gb}/{max_display}GB){NC}")
    else:
        print(f"  {PURPLE}|{NC}   {'RAM':<16s} {YELLOW}Unknown{NC}")

    print()
    vapor_success("System scan complete")
    return info


def step2_providers(existing):
    """Step 2: Provider setup with live testing."""
    step_header(2, "PROVIDER SETUP")

    print(f"  {CYAN}|{NC} Configure your AI provider API keys.")
    print(f"  {CYAN}|{NC} At least {BOLD}one provider{NC} is required.")
    print()

    keys = {}
    configured = 0

    for pid, info in PROVIDERS.items():
        color = info["color"]

        print(f"  {color}{'─' * 50}{NC}")
        print(f"  {info['icon']}  {color}{BOLD}{info['name']}{NC}")
        print(f"  {color}|{NC}  Models: {', '.join(info['models'])}")
        print(f"  {color}|{NC}  Signup: {DIM}{info['signup']}{NC}")

        current = existing.get(info["env_var"], "")
        if current and len(current) > 5:
            print(f"  {color}|{NC}  Current key: {GREEN}{mask_key(current)}{NC}")
            choice = input(f"  {color}|{NC}  Change? [y/N]: ").strip().lower()
            if choice not in ("y", "yes"):
                keys[info["env_var"]] = current
                configured += 1
                vapor_success(f"{info['name']} -- kept existing key")
                print()
                continue

        key = input(f"  {color}|{NC}  Enter API key (Enter to skip): ").strip()
        if not key:
            print(f"  {color}|{NC}  {YELLOW}Skipped{NC}")
            print()
            continue

        # Test with spinner
        test_ok = False
        test_msg = ""
        test_models = []

        with Spinner(f"Testing {info['name']}..."):
            test_ok, test_msg, test_models = TEST_FUNCS[pid](key)

        if test_ok:
            vapor_success(f"{test_msg}")
            if test_models:
                model_str = ", ".join(test_models[:4])
                if len(test_models) > 4:
                    model_str += f" +{len(test_models) - 4} more"
                print(f"  {color}|{NC}  Available: {DIM}{model_str}{NC}")
            keys[info["env_var"]] = key
            configured += 1
        else:
            vapor_error(f"{test_msg}")

            # Detailed error help
            if "401" in test_msg:
                print(f"  {color}|{NC}  {DIM}Check that your key is correct and not expired.{NC}")
                print(f"  {color}|{NC}  {DIM}Get a new key at: {info['signup']}{NC}")
            elif "timeout" in test_msg.lower() or "urlopen" in test_msg.lower():
                print(f"  {color}|{NC}  {DIM}Network error -- check your internet connection.{NC}")

            retry = input(f"  {color}|{NC}  Save anyway? [y/N]: ").strip().lower()
            if retry in ("y", "yes"):
                keys[info["env_var"]] = key
                configured += 1

        print()

    return keys, configured


def step3_strategy():
    """Step 3: Strategy selection with visual table."""
    step_header(3, "STRATEGY SELECTION")

    print(f"  {CYAN}|{NC} Choose how co-vibe routes requests across providers.")
    print()

    # Visual comparison table
    print(f"  {PURPLE}{'─' * 56}{NC}")
    print(f"  {BOLD}{WHITE}  #   Strategy   Description{' ' * 18}Tag{NC}")
    print(f"  {PURPLE}{'─' * 56}{NC}")

    strat_keys = list(STRATEGIES.keys())
    for i, key in enumerate(strat_keys, 1):
        s = STRATEGIES[key]
        badge = f"{s['badge_color']}{BOLD}[{s['badge']}]{NC}"
        marker = f" {NEON_GREEN}<--{NC}" if key == "auto" else ""

        print(f"  {BOLD}{WHITE}  [{i}]{NC}  {CYAN}{key:<10s}{NC} {s['desc']}")
        print(f"       {'':10s} {DIM}{s['detail']}{NC}  {badge}{marker}")
        if i < len(strat_keys):
            print(f"  {DIM}{GRAY}  {'.' * 52}{NC}")

    print(f"  {PURPLE}{'─' * 56}{NC}")
    print()

    choice = input(f"  Select strategy [1]: ").strip()
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(strat_keys) else 0
    strategy = strat_keys[idx]

    print()
    vapor_success(f"Strategy: {strategy} -- {STRATEGIES[strategy]['desc']}")
    return strategy


def step4_advanced(existing):
    """Step 4: Advanced settings."""
    step_header(4, "ADVANCED SETTINGS")

    print(f"  {CYAN}|{NC} Optional fine-tuning. Press Enter for defaults.")
    print()

    # Port
    default_port = existing.get("CO_VIBE_PORT", "8090")
    port_input = input(f"  Proxy port [{default_port}]: ").strip()
    port = int(port_input) if port_input.isdigit() else int(default_port)
    vapor_info(f"Port: {port}")

    print()

    # Model override (optional)
    print(f"  {CYAN}|{NC} Model overrides (leave blank for strategy defaults):")
    print(f"  {DIM}  Examples: claude-opus-4-6, gpt-4o, llama-3.3-70b{NC}")
    model_override = input(f"  Override model [none]: ").strip()
    if model_override:
        vapor_info(f"Model override: {model_override}")
    else:
        vapor_info("Model override: none (strategy decides)")

    return port, model_override


def step5_save_verify(keys, strategy, port, model_override):
    """Step 5: Save and verify configuration."""
    step_header(5, "SAVE & VERIFY")

    progress_bar("Writing configuration...", 0.8)
    write_env(keys, strategy, port)

    # If model override was set, append to .env
    if model_override:
        with open(ENV_PATH, "a") as f:
            f.write(f"CO_VIBE_MODEL_OVERRIDE={model_override}\n")

    print()
    vapor_success(f"Configuration saved: {ENV_PATH}")
    vapor_info("File permissions set to 600 (owner-only)")
    print()

    # Verification summary
    print(f"  {PURPLE}|{NC} {BOLD}{WHITE}Verification{NC}")
    print(f"  {PURPLE}|{NC}")

    for pid, info in PROVIDERS.items():
        env_var = info["env_var"]
        if env_var in keys:
            print(f"  {PURPLE}|{NC}   {GREEN}●{NC} {info['name']:<25s} {GREEN}configured{NC}")
        else:
            print(f"  {PURPLE}|{NC}   {RED}○{NC} {info['name']:<25s} {RED}not set{NC}")

    print(f"  {PURPLE}|{NC}")
    print(f"  {PURPLE}|{NC}   Strategy:  {CYAN}{strategy}{NC}")
    print(f"  {PURPLE}|{NC}   Port:      {CYAN}{port}{NC}")
    if model_override:
        print(f"  {PURPLE}|{NC}   Override:  {CYAN}{model_override}{NC}")
    print()

    return True


def celebration():
    """Completion celebration animation."""
    print()
    print()

    # Fireworks animation
    frames = [
        "  🎆 🎇 ✨ 💫 🌟 ⭐ 🌟 💫 ✨ 🎇 🎆",
        "  🎇 🎆 💫 ✨ ⭐ 🌟 ⭐ ✨ 💫 🎆 🎇",
        "  ✨ 💫 🎆 🎇 🌟 ⭐ 🌟 🎇 🎆 💫 ✨",
        "  💫 ✨ 🎇 🎆 ⭐ 🌟 ⭐ 🎆 🎇 ✨ 💫",
    ]
    for _ in range(3):
        for frame in frames:
            sys.stdout.write(f"\r{frame}")
            sys.stdout.flush()
            time.sleep(0.1)

    print()
    print()

    # Completion banner
    heart_line()
    print()
    print(f"  {rainbow_text('████████████████████████████████████████████████████████')}")
    print()
    print(f"          🎉🎉🎉  {BOLD}{MAGENTA}SETUP COMPLETE !!{NC}  🎉🎉🎉")
    print()
    print(f"  {rainbow_text('████████████████████████████████████████████████████████')}")
    print()
    heart_line()
    print()

    # Usage instructions
    print(f"  {rainbow_text('════════════════════════════════════════════════════════')}")
    print()
    print(f"    {BOLD}{WHITE}🚀 Quick Start:{NC}")
    print()
    print(f"    {PINK}❯{NC} {BOLD}{CYAN}python3 co-vibe-proxy.py{NC}      {DIM}Start proxy server{NC}")
    print(f"    {PINK}❯{NC} {BOLD}{CYAN}./co-vibe.sh{NC}                   {DIM}Launch Claude Code{NC}")
    print(f"    {PINK}❯{NC} {BOLD}{CYAN}python3 setup.py{NC}               {DIM}Reconfigure{NC}")
    print()
    print(f"  {rainbow_text('════════════════════════════════════════════════════════')}")
    print()
    print(f"  {vapor_text('    Enjoy multi-provider AI orchestration!')}")
    print()
    print()


# =============================================
# MAIN
# =============================================

def main():
    clear()
    show_banner()

    existing = load_existing_env()
    if existing:
        configured = sum(
            1 for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"]
            if existing.get(k, "") and len(existing.get(k, "")) > 5
        )
        if configured:
            vapor_info(f"Existing config found ({configured} provider(s) configured)")
    print()
    input(f"  {BOLD}{WHITE}Press Enter to begin setup...{NC}")

    # Step 1: System Info
    step1_system_info()

    # Step 2: Provider Setup
    keys, configured = step2_providers(existing)
    if configured == 0:
        vapor_error("At least one API key is required.")
        print(f"  {DIM}Get an API key from one of the providers listed above,{NC}")
        print(f"  {DIM}then run setup again.{NC}")
        sys.exit(1)

    # Step 3: Strategy Selection
    strategy = step3_strategy()

    # Step 4: Advanced Settings
    port, model_override = step4_advanced(existing)

    # Step 5: Save & Verify
    step5_save_verify(keys, strategy, port, model_override)

    # Celebration
    celebration()


if __name__ == "__main__":
    main()
