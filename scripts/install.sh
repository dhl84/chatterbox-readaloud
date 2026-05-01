#!/bin/bash
# Idempotent installer for chatterbox-readaloud.
# Renders launchd plists from templates with this checkout's path and your $HF_TOKEN,
# installs them into ~/Library/LaunchAgents, and (re)loads them.
#
# Skips the ollama LaunchAgent if the macOS Ollama.app already has port 11434 bound.

set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LA_DIR="$HOME/Library/LaunchAgents"
TMPL_DIR="$PROJECT/launchagents"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note()  { printf '\033[36m==> %s\033[0m\n' "$*"; }

require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        red "Missing: $1 — $2"
        exit 1
    fi
}

note "Checking prerequisites"
require brew    "install native arm64 Homebrew at /opt/homebrew (https://brew.sh)"
require uv      "install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
require ollama  "brew install ollama (or download Ollama.app from https://ollama.com)"
require ffmpeg  "brew install ffmpeg"

if ! command -v espeak-ng >/dev/null 2>&1; then
    note "Installing espeak-ng"
    brew install espeak-ng
fi

if [ -z "${HF_TOKEN:-}" ]; then
    red "HF_TOKEN not set. Create one at https://huggingface.co/settings/tokens then:"
    red "    echo 'export HF_TOKEN=hf_...' >> ~/.zshrc && source ~/.zshrc"
    exit 1
fi

OLLAMA_BIN="$(command -v ollama)"

note "Creating Python venv (3.12) at $PROJECT/.venv"
cd "$PROJECT"
uv venv --python 3.12
# shellcheck disable=SC1091
source .venv/bin/activate
note "Installing the readaloud package and its deps"
uv pip install -e .

# Make sure ollama daemon is up before pulling.
if ! lsof -ti:11434 >/dev/null 2>&1; then
    note "Starting ollama serve in background (no daemon detected)"
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
fi

note "Pulling Ollama model qwen2.5:14b (skips if present)"
if ! ollama list | awk '{print $1}' | grep -qx "qwen2.5:14b"; then
    ollama pull qwen2.5:14b
else
    green "qwen2.5:14b already present"
fi

note "Rendering and installing LaunchAgents into $LA_DIR"
mkdir -p "$LA_DIR"
for tmpl in "$TMPL_DIR"/*.plist.tmpl; do
    name="$(basename "${tmpl%.tmpl}")"

    # Skip the ollama agent if Ollama.app (or anything else) is already serving 11434.
    if [[ "$name" == "com.chatterbox.ollama.plist" ]] && lsof -ti:11434 >/dev/null 2>&1; then
        existing_pid="$(lsof -ti:11434 | head -1)"
        existing_cmd="$(ps -p "$existing_pid" -o command= 2>/dev/null || true)"
        if [[ "$existing_cmd" != *"$PROJECT"* ]] && [[ "$existing_cmd" == *"ollama"* ]]; then
            green "Skipping $name — port 11434 already served by: $existing_cmd"
            continue
        fi
    fi

    out="$LA_DIR/$name"
    sed \
        -e "s|__PROJECT__|$PROJECT|g" \
        -e "s|__HOME__|$HOME|g" \
        -e "s|__OLLAMA_BIN__|$OLLAMA_BIN|g" \
        -e "s|__HF_TOKEN__|$HF_TOKEN|g" \
        "$tmpl" > "$out"
    launchctl unload "$out" 2>/dev/null || true
    launchctl load -w "$out"
    green "Loaded $name"
done

note "Smoke-testing the MLX server"
sleep 6
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/ | grep -q 200; then
    green "MLX server responding on 127.0.0.1:8000"
else
    red "MLX server not responding yet — tail /tmp/mlx-server.log"
fi

cat <<EOF

$(green "Install complete.")

Next:
  1. Test from CLI:    $PROJECT/bin/readaloud url https://en.wikipedia.org/wiki/Apple_silicon
  2. Optional alias:   echo "alias readaloud='$PROJECT/bin/readaloud'" >> ~/.zshrc
  3. Wire macOS Shortcuts as described in README.md (one for url, one for clip, one for stop).

Logs:
  /tmp/mlx-server.log
  /tmp/readaloud-menubar.log
EOF
