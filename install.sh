#!/bin/bash
# co-vibe installer
# Ｃ Ｏ - Ｖ Ｉ Ｂ Ｅ   ＩＮＳＴＡＬＬＥＲ
# Multi-Provider AI Orchestrator for Claude Code
# Trilingual: ja/en/zh

set -uo pipefail

PINK='\033[38;5;198m'
HOT_PINK='\033[38;5;206m'
MAGENTA='\033[38;5;165m'
PURPLE='\033[38;5;141m'
CYAN='\033[38;5;51m'
AQUA='\033[38;5;87m'
MINT='\033[38;5;121m'
CORAL='\033[38;5;210m'
ORANGE='\033[38;5;208m'
YELLOW='\033[38;5;226m'
WHITE='\033[38;5;255m'
GRAY='\033[38;5;245m'
RED='\033[38;5;196m'
GREEN='\033[38;5;46m'
NEON_GREEN='\033[38;5;118m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

GRADIENT_NEON=(46 47 48 49 50 51 45 39 33 27 21 57 93 129 165 201 200 199 198 197 196)
GRADIENT_BAR=(198 199 207 213 177 171 165 129 93 57 51 50 49 48 47 46)

TOTAL_STEPS=6
INSTALL_DIR="${HOME}/.local/lib/co-vibe"
BIN_DIR="${HOME}/.local/bin"

# Trilingual
detect_lang() {
    local raw="${LANG:-${LC_ALL:-en_US.UTF-8}}"
    case "$raw" in ja*) echo "ja" ;; zh*) echo "zh" ;; *) echo "en" ;; esac
}
LANG_CODE="$(detect_lang)"

MSG_ja_subtitle="マルチプロバイダーAIオーケストレーター"
MSG_ja_complete="インストール完了！"
MSG_ja_enter_key="APIキーを入力 (スキップは Enter)"
MSG_ja_skip="スキップ"
MSG_en_subtitle="Multi-Provider AI Orchestrator"
MSG_en_complete="INSTALL COMPLETE !!"
MSG_en_enter_key="Enter API key (Enter to skip)"
MSG_en_skip="Skipped"
MSG_zh_subtitle="多供应商AI编排器"
MSG_zh_complete="安装完成！"
MSG_zh_enter_key="输入API密钥（回车跳过）"
MSG_zh_skip="跳过"

msg() { local var="MSG_${LANG_CODE}_${1}"; echo "${!var:-${1}}"; }

rainbow_text() {
    local text="$1"
    local colors=("${GRADIENT_NEON[@]}") len=${#text} num=${#GRADIENT_NEON[@]} r=""
    for ((i=0;i<len;i++)); do r+="\033[38;5;${colors[$((i%num))]}m${text:$i:1}"; done
    echo -e "${r}${NC}"
}

heart_line() {
    local cs=("$PINK" "$MAGENTA" "$PURPLE" "$CYAN" "$AQUA" "$MINT" "$NEON_GREEN" "$YELLOW" "$ORANGE" "$CORAL" "$HOT_PINK" "$PINK" "$MAGENTA" "$PURPLE" "$CYAN" "$AQUA")
    local l="  "; for c in "${cs[@]}"; do l+="${c}*${NC}"; done; echo -e "$l"
}

vapor_progress() {
    local label="$1" w=35 colors=("${GRADIENT_BAR[@]}") num=${#GRADIENT_BAR[@]} s=0 steps=20
    local sparkles=("✨" "💎" "🔮" "💜" "🌸" "🎵")
    for ((s=0;s<=steps;s++)); do
        local pct=$((s*100/steps))
        local filled=$((s*w/steps))
        local empty=$((w-filled))
        local spark="${sparkles[$((s%${#sparkles[@]}))]}" bar=""
        for ((b=0;b<filled;b++)); do bar+="\033[38;5;${colors[$((b*num/w))]}m█"; done
        for ((e=0;e<empty;e++)); do bar+="\033[38;5;237m░"; done
        printf "\r  %s ${BOLD}${CYAN}%-26s${NC} ${MAGENTA}▐${NC}%b${MAGENTA}▌${NC} ${BOLD}${NEON_GREEN}%3d%%${NC} " "$spark" "$label" "$bar" "$pct"
        sleep 0.03
    done
    local bar="" b=0
    for ((b=0;b<w;b++)); do bar+="\033[38;5;${colors[$((b*num/w))]}m█"; done
    printf "\r  ✅ ${BOLD}${GREEN}%-26s${NC} ${MAGENTA}▐${NC}%b${MAGENTA}▌${NC} ${BOLD}${NEON_GREEN}100%%${NC} 🎉\n" "$label" "$bar"
}

vapor_success() { echo -e "  ${NEON_GREEN}┃${NC} ✅ ${BOLD}${MINT}$*${NC}"; }
vapor_info()    { echo -e "  ${CYAN}┃${NC} 💠 ${AQUA}$*${NC}"; }
vapor_warn()    { echo -e "  ${ORANGE}┃${NC} ⚠️  ${YELLOW}$*${NC}"; }
vapor_error()   { echo -e "  ${RED}┃${NC} 💀 ${RED}${BOLD}$*${NC}"; }

step_header() {
    local num="$1" title="$2"
    local icons=("🔍" "📦" "⚙️" "🔗" "🔑" "🧪")
    local cs=(51 87 123 159 165 198)
    local c="${cs[$((num-1))]}"
    echo ""
    echo -e "  \033[38;5;${c}m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${icons[$((num-1))]}  \033[38;5;${c}m${BOLD}STEP ${num}/${TOTAL_STEPS}${NC}  ${BOLD}${WHITE}${title}${NC}"
    echo -e "  \033[38;5;${c}m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

celebrate() {
    local f=("🎆 🎇 ✨ 💫 🌟 ⭐ 🌟 💫 ✨ 🎇 🎆" "🎇 🎆 💫 ✨ ⭐ 🌟 ⭐ ✨ 💫 🎆 🎇" "✨ 💫 🎆 🎇 🌟 ⭐ 🌟 🎇 🎆 💫 ✨")
    for _ in 1 2 3; do for fr in "${f[@]}"; do printf "\r  %s" "$fr"; sleep 0.1; done; done; echo ""
}

# ═══════════════ MAIN ═══════════════

show_banner() {
    clear
    echo ""; heart_line; echo ""
    echo -e "${MAGENTA}${BOLD}"
    cat << 'B'
     ██████╗ ██████╗        ██╗   ██╗██╗██████╗ ███████╗
    ██╔════╝██╔═══██╗       ██║   ██║██║██╔══██╗██╔════╝
    ██║     ██║   ██║ █████╗██║   ██║██║██████╔╝█████╗
    ██║     ██║   ██║ ╚════╝╚██╗ ██╔╝██║██╔══██╗██╔══╝
    ╚██████╗╚██████╔╝        ╚████╔╝ ██║██████╔╝███████╗
     ╚═════╝ ╚═════╝          ╚═══╝  ╚═╝╚═════╝ ╚══════╝
B
    echo -e "${NC}"
    echo -e "    ${DIM}${CYAN}$(msg subtitle)${NC}"
    echo ""; heart_line; echo ""
    echo -e "  ${DIM}${CYAN}Initializing vaporwave subsystem...${NC}"; sleep 0.2
    echo -e "  ${DIM}${PURPLE}Loading aesthetic modules...${NC}"; sleep 0.2
    echo -e "  ${BOLD}${NEON_GREEN}  ▶ SYSTEM ONLINE${NC}"; echo ""
}

step1_scan() {
    step_header 1 "SYSTEM SCAN"
    vapor_progress "Scanning hardware..." 1; echo ""
    if command -v python3 &>/dev/null; then
        vapor_success "Python3: $(python3 --version 2>&1 | awk '{print $2}')"
    else
        vapor_error "Python3 not found!"; exit 1
    fi
    if command -v claude &>/dev/null; then
        vapor_success "Claude Code CLI detected"
    else
        vapor_warn "Claude Code CLI not found (recommended)"
    fi
    if [[ "$(uname)" == "Darwin" ]]; then
        vapor_info "macOS / $(($(sysctl -n hw.memsize)/1073741824))GB RAM / $(uname -m)"
    fi
    echo ""; vapor_success "Pure Python - zero external dependencies!"
}

step2_deploy() {
    step_header 2 "FILE DEPLOY"
    mkdir -p "$INSTALL_DIR" "$BIN_DIR"
    local src; src="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
    if [ -n "$src" ] && [ -f "${src}/co-vibe.py" ]; then
        vapor_progress "Deploying files..." 1
        for f in co-vibe.py co-vibe.sh setup.py .env.example; do
            [ -f "${src}/${f}" ] && cp "${src}/${f}" "${INSTALL_DIR}/${f}"
        done
    else
        vapor_error "Source files not found. Run from co-vibe directory."; exit 1
    fi
    chmod +x "${INSTALL_DIR}/co-vibe.sh" "${INSTALL_DIR}/co-vibe.py" "${INSTALL_DIR}/setup.py" 2>/dev/null
    echo ""; vapor_success "Deployed to ${INSTALL_DIR}"
}

step3_config() {
    step_header 3 "CONFIGURATION"
    vapor_progress "Generating config..." 0.5
    if [ ! -f "${INSTALL_DIR}/.env" ]; then
        cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
        chmod 600 "${INSTALL_DIR}/.env"
    fi
    echo ""; vapor_success "Config: ${INSTALL_DIR}/.env"
}

step4_link() {
    step_header 4 "COMMAND SETUP"
    vapor_progress "Creating symlinks..." 0.5
    ln -sf "${INSTALL_DIR}/co-vibe.sh" "${BIN_DIR}/co-vibe"
    echo ""; vapor_success "co-vibe -> ${BIN_DIR}/co-vibe"
    if ! echo "$PATH" | grep -q "${BIN_DIR}"; then
        echo ""; vapor_warn "Add to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

step5_keys() {
    step_header 5 "API KEY SETUP"
    local env="${INSTALL_DIR}/.env" n=0

    for provider_info in "Anthropic:ANTHROPIC_API_KEY:${PURPLE}" "OpenAI:OPENAI_API_KEY:${NEON_GREEN}" "Groq:GROQ_API_KEY:${CYAN}"; do
        IFS=: read -r name var color <<< "$provider_info"
        echo -e "  ${color}─────────────────────────────────${NC}"
        echo -e "  ${color}${BOLD}${name}${NC}"
        printf "  ${color}┃${NC} $(msg enter_key): "
        local key=""
        read -r key </dev/tty 2>/dev/null || read -r key || true
        if [ -n "$key" ]; then
            sed "s|^.*${var}=.*|${var}=${key}|" "$env" > "${env}.tmp" && mv "${env}.tmp" "$env"
            n=$((n+1)); vapor_success "${name} configured"
        else
            echo -e "  ${YELLOW}$(msg skip)${NC}"
        fi
        echo ""
    done

    if [ "$n" -eq 0 ]; then vapor_warn "No keys set. Edit: ${env}"; fi

    echo -e "  ${PURPLE}─────────────────────────────────${NC}"
    echo -e "  🎯 ${BOLD}Strategy${NC}"
    echo -e "  [1] auto ${NEON_GREEN}(recommended)${NC}  [2] strong  [3] fast  [4] cheap"
    printf "  Select [1]: "
    local sc="1"
    read -r sc </dev/tty 2>/dev/null || read -r sc || true
    local strat="auto"
    case "$sc" in 2) strat="strong" ;; 3) strat="fast" ;; 4) strat="cheap" ;; esac
    sed "s|^CO_VIBE_STRATEGY=.*|CO_VIBE_STRATEGY=${strat}|" "$env" > "${env}.tmp" && mv "${env}.tmp" "$env"
    vapor_success "Strategy: ${strat}"
}

step6_verify() {
    step_header 6 "VERIFICATION"
    vapor_progress "Running tests..." 1
    if python3 -c "import ast; ast.parse(open('${INSTALL_DIR}/co-vibe-proxy.py').read())" 2>/dev/null; then
        vapor_success "Proxy: valid Python"
    else
        vapor_error "Proxy: syntax error!"
    fi
    if [ -x "${BIN_DIR}/co-vibe" ]; then vapor_success "Command: co-vibe ready"; fi
}

show_complete() {
    echo ""; celebrate; echo ""; heart_line; echo ""
    rainbow_text "  ████████████████████████████████████████████████████████"
    echo -e "          🎉🎉🎉  ${BOLD}${MAGENTA}$(msg complete)${NC}  🎉🎉🎉"
    rainbow_text "  ████████████████████████████████████████████████████████"
    echo ""; heart_line; echo ""
    echo -e "    ${BOLD}${WHITE}🚀 Usage:${NC}"
    echo -e "    ${PINK}❯${NC} ${BOLD}${CYAN}co-vibe${NC}                    ${DIM}Launch Claude Code${NC}"
    echo -e "    ${PINK}❯${NC} ${BOLD}${CYAN}co-vibe -p \"question\"${NC}      ${DIM}One-shot mode${NC}"
    echo -e "    ${PINK}❯${NC} ${BOLD}${CYAN}co-vibe --strategy fast${NC}    ${DIM}Speed priority${NC}"
    echo -e "    ${PINK}❯${NC} ${BOLD}${CYAN}python3 setup.py${NC}           ${DIM}Reconfigure${NC}"
    echo ""
}

main() { show_banner; step1_scan; step2_deploy; step3_config; step4_link; step5_keys; step6_verify; show_complete; }
main "$@"
