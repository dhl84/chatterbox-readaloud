#!/bin/bash
# Unload + remove LaunchAgents installed by scripts/install.sh.
# Leaves the venv, the Ollama model, and Homebrew packages alone.

set -euo pipefail

LA_DIR="$HOME/Library/LaunchAgents"

for label in com.chatterbox.menubar com.chatterbox.mlx-audio-server com.chatterbox.ollama; do
    plist="$LA_DIR/${label}.plist"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm -f "$plist"
        echo "Removed $plist"
    fi
done

rm -f /tmp/readaloud.state /tmp/readaloud.wav

echo "Done. The venv, Ollama models, and Homebrew packages were left in place."
