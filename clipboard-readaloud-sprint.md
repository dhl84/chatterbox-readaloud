# Sprint: clipboard read-aloud

> **Status: shipped** (2026-04-30). Code lives in [`readaloud/`](readaloud/). User-facing
> behaviour described below is reflected in the [README](README.md) under "What it can read"
> and "Wire the global hotkeys". Keeping this file as a historical record of the spec —
> further changes should land directly in code + README, not here.

Extend the existing `readaloud` pipeline to read whatever is on the macOS clipboard. Goal: select text in any app (Terminal, Mail, browser, Slack), copy, trigger, hear it.

## Scope

In:
- New CLI entrypoint that reads `pbpaste` instead of fetching a URL.
- Smart routing: short text → speak directly; long or messy text → run cleanup pass first.
- Skip cleanup for terminal output (preserve technical detail).
- Hotkey trigger via macOS Shortcuts.
- Stop/interrupt currently-playing audio.

Out:
- Clipboard history.
- Auto-watching the clipboard.
- Reading images / rich content. Plain text only.
- Replacing the URL fetcher — keep both.

## Architecture

Refactor `readaloud.py` into a package:

```
~/tts/
  readaloud/
    __init__.py
    fetch.py      # existing URL fetcher
    clipboard.py  # new
    clean.py      # extracted Ollama cleanup
    speak.py      # extracted TTS call
    cli.py        # argparse dispatch
  pyproject.toml  # already exists from uv init
```

Single entrypoint `readaloud` with subcommands: `url <URL>`, `clip`, `stop`.

## Tasks

### 1. Refactor existing script into package (~30 min)

Extract `fetch()`, `clean()`, `speak()` from `readaloud.py` into the modules above. `cli.py` wires subcommands. Update the alias to call `python -m readaloud`. Verify `readaloud url https://example.com` still works before moving on.

Acceptance: existing URL flow unchanged from the user's perspective.

### 2. Clipboard subcommand (~20 min)

`readaloud/clipboard.py`:

```python
import subprocess

def read_clipboard() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
    return r.stdout
```

`cli.py` adds `clip` subcommand. If clipboard is empty or whitespace-only, exit with a clear message — do not call TTS.

Acceptance: `pbcopy < some.txt && readaloud clip` plays the file's contents.

### 3. Smart routing — cleanup or raw (~30 min)

Heuristic in `cli.py` for the `clip` command, with a `--raw` and `--clean` override:

- If text matches terminal-output patterns (lines starting with `$`, `>`, `+`, `-`, contains `Traceback`, has many `\t` or aligned columns, >40% non-alpha chars on a line) → speak raw.
- If text is < 200 words → speak raw.
- Otherwise → run through Ollama cleanup.

Implement as `should_clean(text: str) -> bool`. Keep it simple — 5–10 lines. Easy to tune later.

Acceptance: copying a stack trace reads the stack trace verbatim. Copying a long email reads a cleaned summary.

### 4. Pre-TTS sanitization (always, both paths) (~15 min)

Even raw text needs minor fixes for TTS not to sound terrible:

- Collapse runs of `=`, `-`, `*`, `_` (separator lines) to a single period.
- Replace common symbols: `->` → "to", `=>` → "implies", `&` → "and".
- Strip ANSI escape codes (`\x1b\[[0-9;]*m`).
- Truncate to 8000 chars with a "...truncated" suffix to prevent runaway TTS jobs.

One function `sanitize(text: str) -> str` in `speak.py`, called before every synthesis.

Acceptance: `echo -e "\x1b[31merror\x1b[0m: foo -> bar" | pbcopy && readaloud clip` does not pronounce escape codes or arrows literally.

### 5. Stop command (~20 min)

Currently `afplay` blocks the script. Switch to backgrounded playback with PID tracking:

- `speak.py` writes the playing process's PID to `/tmp/readaloud.pid` and launches `afplay` with `subprocess.Popen` (non-blocking).
- New `stop` subcommand reads the PID, sends SIGTERM, removes the file.
- Before each new playback, run `stop` to kill any prior instance.

Acceptance: `readaloud clip` then `readaloud stop` mid-sentence silences immediately. Triggering a new `readaloud clip` while one is playing replaces it cleanly.

### 6. Hotkey via macOS Shortcuts (~15 min, manual)

Document, do not script. Steps for the user:

1. Open Shortcuts.app → new shortcut "Read Clipboard".
2. Add action "Run Shell Script". Shell: `/bin/zsh`. Script:
   ```bash
   source ~/.zshrc && readaloud clip
   ```
3. Settings → "Use as Quick Action" + assign keyboard shortcut (suggest ⌃⌥R).
4. Repeat for "Stop Reading" → `readaloud stop` → ⌃⌥S.

Acceptance: select text anywhere, ⌘C, ⌃⌥R → audio plays. ⌃⌥S stops it.

## Verification suite

Run all five before declaring done:

1. `pbcopy <<< "Hello world" && readaloud clip` — speaks "Hello world", no cleanup.
2. Copy a long article from a browser → `readaloud clip` — speaks a summary, not the raw text.
3. Copy a Python stack trace → `readaloud clip` — speaks the trace including "Traceback", "line", function names.
4. `readaloud clip` on a 10k-word document — truncates, does not hang.
5. Start playback, run `readaloud stop` — silence within 1 second.

## Known sharp edges to handle

- `pbpaste` returns empty string for non-text clipboard (image, file). Detect and exit cleanly.
- The cleanup LLM occasionally adds preamble like "Here is the summary:". Strip leading lines that look like meta-commentary in `clean.py` before returning.
- Long Slack pastes include username/timestamp prefixes on every line — the cleanup pass handles this fine; raw mode will sound cluttered. Acceptable for v1.

---
Cut: clipboard history feature, auto-watching daemon, image-OCR-then-read, multi-language detection, voice switching per content type, integration with specific apps (Slack/Mail) bypassing clipboard. All deferrable.
Status: shipped 2026-04-30
