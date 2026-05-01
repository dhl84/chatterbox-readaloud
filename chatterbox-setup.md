# Chatterbox TTS + Ollama pipeline — setup

Set up a local read-aloud pipeline on an M4 Max: fetch a URL, clean the text via Ollama, synthesize speech via Chatterbox Turbo running on MLX-Audio. Existing assumptions: Apple Silicon, Homebrew installed, Ollama installed and running.

## Decisions already made

- **Model**: `mlx-community/chatterbox-turbo-fp16` — faster than base Chatterbox, expressive event tags supported, default voice is fine (no reference audio).
- **Python**: 3.12, managed via `uv`. Do not use 3.13 — spaCy's `blis` fails to compile.
- **Cleanup LLM**: `qwen2.5:14b` via Ollama. Pull it if missing.
- **Server**: MLX-Audio's OpenAI-compatible server on `127.0.0.1:8000`.
- **Project root**: `~/tts`.

## Step 1 — System dependencies

```bash
brew install espeak-ng ffmpeg
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 2 — Project + Python env

```bash
mkdir -p ~/tts && cd ~/tts
uv init --no-readme
uv venv --python 3.12
source .venv/bin/activate
uv pip install "mlx-audio[tts]" requests beautifulsoup4 openai
```

## Step 3 — HuggingFace token

The user must create a read-only token at https://huggingface.co/settings/tokens, then:

```bash
echo 'export HF_TOKEN=<paste-token-here>' >> ~/.zshrc
source ~/.zshrc
```

If `HF_TOKEN` is unset, prompt the user before continuing.

## Step 4 — Verify Ollama + pull cleanup model

```bash
ollama list | grep -q qwen2.5:14b || ollama pull qwen2.5:14b
curl -s http://localhost:11434/api/tags >/dev/null || echo "Ollama not running — start with: ollama serve"
```

## Step 5 — Smoke test Chatterbox

```bash
cd ~/tts && source .venv/bin/activate
mlx_audio.tts.generate \
  --model mlx-community/chatterbox-turbo-fp16 \
  --text "If this works, the pipeline is ready." \
  --play
```

First run downloads ~2.7 GB. Audio saves to `~/.mlx_audio/outputs/`.

## Step 6 — Start the server

Run in a dedicated terminal (or `tmux`/`screen`):

```bash
cd ~/tts && source .venv/bin/activate
mlx_audio.server --host 127.0.0.1 --port 8000
```

Verify from another shell:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"mlx-community/chatterbox-turbo-fp16","input":"Server is up.","voice":"default"}' \
  --output /tmp/test.wav && afplay /tmp/test.wav
```

## Step 7 — The pipeline script

Create `~/tts/readaloud.py`:

```python
#!/usr/bin/env python3
"""Fetch a URL, clean via Ollama, speak via Chatterbox."""
import sys
import subprocess
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

TTS_MODEL = "mlx-community/chatterbox-turbo-fp16"
TTS_URL = "http://127.0.0.1:8000/v1"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"
OUTPUT = "/tmp/readaloud.wav"

CLEAN_PROMPT = """You will be given the raw text of a web page. Rewrite it as a
short spoken summary suitable for text-to-speech. Rules:
- Strip nav, ads, cookie banners, footers, related-article lists.
- Keep claims, numbers, names, decisions, and instructions.
- Cut hedging ("it's worth noting", "important to consider").
- Expand acronyms on first use (API -> A P I) so TTS pronounces them.
- Output plain prose only. No markdown, no headers, no bullets.
- Target 200-400 words unless the source is very short.
Source text follows.
---
"""

def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    return " ".join(soup.get_text().split())

def clean(raw: str) -> str:
    r = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": CLEAN_PROMPT + raw[:20000],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 16384},
    }, timeout=300)
    r.raise_for_status()
    return r.json()["response"].strip()

def speak(text: str, out: str) -> None:
    client = OpenAI(base_url=TTS_URL, api_key="not-needed")
    resp = client.audio.speech.create(model=TTS_MODEL, voice="default", input=text)
    resp.stream_to_file(out)

def main():
    if len(sys.argv) != 2:
        sys.exit("usage: readaloud.py <url>")
    url = sys.argv[1]
    print(f"Fetching {url}...")
    raw = fetch(url)
    print(f"Cleaning {len(raw)} chars via {OLLAMA_MODEL}...")
    cleaned = clean(raw)
    print(f"--- Cleaned ({len(cleaned)} chars) ---\n{cleaned}\n---")
    print("Synthesizing...")
    speak(cleaned, OUTPUT)
    subprocess.run(["afplay", OUTPUT])

if __name__ == "__main__":
    main()
```

Make it executable and test:

```bash
chmod +x ~/tts/readaloud.py
~/tts/readaloud.py https://en.wikipedia.org/wiki/Apple_silicon
```

## Step 8 — Convenience alias

Append to `~/.zshrc`:

```bash
alias readaloud='cd ~/tts && source .venv/bin/activate && python readaloud.py'
```

Reload shell. Usage: `readaloud <url>`.

## Verification checklist for Claude Code

After setup, confirm each:

1. `mlx_audio.tts.generate --model mlx-community/chatterbox-turbo-fp16 --text "test" --play` produces audio.
2. `curl http://127.0.0.1:8000/v1/audio/speech ...` (Step 6) produces a non-empty WAV.
3. `~/tts/readaloud.py https://en.wikipedia.org/wiki/Apple_silicon` plays cleaned audio end-to-end.

If any step fails, stop and report the exact error — do not invent fixes.

## Known sharp edges

- Long inputs: Chatterbox handles paragraphs but degrades past ~1000 words per call. The cleanup step should keep output under 400 words; if you bypass cleanup for raw text, chunk on paragraph breaks and concatenate WAVs.
- Server cold start: first request after launch takes ~10 s while the model loads.
- Pronunciation of internal jargon and acronyms is poor. The `CLEAN_PROMPT` expansion rule helps; for product names that still mangle, add explicit substitutions in `clean()` before the LLM call.

---
Cut: rationale for model choice (decided upstream), reference-voice setup (user opted out), LaunchAgent autostart (user opted out), troubleshooting tree for failures that haven't occurred, alternative models, voice listing.
Status: draft
