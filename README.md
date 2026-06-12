# chatterbox-readaloud

Local "read this aloud" pipeline for Apple Silicon Macs. Hit a global hotkey, hand it a URL or copy text to your clipboard, hear it narrated by [Chatterbox Turbo](https://huggingface.co/mlx-community/chatterbox-turbo-fp16) running on-device via [MLX-Audio](https://github.com/Blaizzy/mlx-audio). A small menu-bar indicator shows when it's preparing vs. playing.

Everything runs locally. No cloud TTS, no telemetry. The only outbound calls are HTTP `GET` for URL fetches plus the one-time model downloads from Hugging Face and Ollama.

---

## What it can read

- **Any URL.** Fetches, strips chrome, runs the page through a cleanup LLM (Ollama / `gemma4:latest`), then synthesizes a 200–400 word spoken summary.
- **Whatever's on your clipboard.** Auto-routes: short text or terminal output (stack traces, shell sessions, diff hunks) gets spoken raw; long prose gets summarized first.

---

## Architecture

```
   global hotkey (macOS Shortcut)
            │
            ▼
   bin/readaloud  url <URL>     ─┐
   bin/readaloud  clip [--raw]   │
   bin/readaloud  stop          ─┘
            │
            ▼
   readaloud/cli.py  ──► fetch | clipboard
                          │
                          ▼
                       clean.should_clean(text)?
                          │            │
                       cleanup       (skip)
                          │            │
                          └──► sanitize ──► speak.synthesize ──► speak.play
                                                                     │
                                                                     ├─ /tmp/readaloud.wav
                                                                     ├─ /tmp/readaloud.pid  (for stop)
                                                                     └─ /tmp/readaloud.state  (preparing/playing/idle)
                                                                                                  │
                                                                                                  ▼
                                                                                          menubar.py polls
                                                                                          ⏳ / ▶ / ·
```

Two services run via `launchd`:

| Label | What | Port |
| --- | --- | --- |
| `com.chatterbox.mlx-audio-server` | OpenAI-compatible TTS server | 8000 |
| `com.chatterbox.menubar` | Menu-bar status indicator | — |

Ollama runs separately. If you have **Ollama.app** installed, it manages its own daemon on port 11434 and the installer skips installing a redundant agent. If you don't, the installer falls back to a `com.chatterbox.ollama` LaunchAgent that runs `ollama serve`.

---

## Requirements

- **Apple Silicon** Mac (tested on M4 Max, macOS 26 / Tahoe). MLX needs native `arm64`.
- **Native arm64 Homebrew** at `/opt/homebrew`. If you only have the Intel Homebrew at `/usr/local`, install the native one first — MLX falls back to CPU under Rosetta and gets very slow.
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
- **Ollama** ([Ollama.app from ollama.com](https://ollama.com) or `brew install ollama`). Disk: ~10 GB for `gemma4:latest`.
- **ffmpeg** (`brew install ffmpeg`). Used by MLX-Audio.
- **A Hugging Face read token** in `HF_TOKEN`. Create one at <https://huggingface.co/settings/tokens>.

The installer verifies all of the above and bails with a clear message if anything is missing.

---

## Install

```bash
git clone <your-fork-url> chatterbox && cd chatterbox
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx
./scripts/install.sh
```

What it does, in order:

1. Verifies `brew`, `uv`, `ollama`, `ffmpeg`, `espeak-ng`, `HF_TOKEN`.
2. Creates `.venv/` with Python 3.12 (3.13 is **not** supported — spaCy's `blis` fails to compile).
3. `uv pip install -e .` — installs the `readaloud` package and all deps.
4. `ollama pull gemma4:latest` if not already present.
5. Renders the plists in `launchagents/*.plist.tmpl` with this checkout's path and your `HF_TOKEN`, writes them to `~/Library/LaunchAgents/`, and `launchctl load -w`s each one. Skips the ollama plist if Ollama.app is already serving 11434.
6. Curls the MLX server to confirm it came up.

First MLX-server start downloads the Chatterbox model (~2.7 GB) on the first synthesis call, not at install time.

To remove the LaunchAgents (leaves the venv, models, and brew packages alone):

```bash
./scripts/uninstall.sh
```

---

## Wire the global hotkeys (manual, ~5 minutes)

Apple has no clean CLI to create Shortcuts, so this is one-time UI work. Create three shortcuts, replacing `$HOME/chatterbox` with your checkout's absolute path (Shortcuts does not expand `~` or shell variables):

### 1. "Read URL"

1. Open **Shortcuts.app**, hit **+**, name it `Read URL`.
2. Add **Ask for Input**. Prompt: `URL to read aloud`. Input Type: `Text`.
3. Add **Run Shell Script**. Shell: `/bin/bash`. Pass Input: `as arguments`. Script:
   ```bash
   $HOME/chatterbox/bin/readaloud url "$1" >/tmp/readaloud.log 2>&1 &
   ```
4. Click the **(i) info icon** → **Add Keyboard Shortcut** → press your chord (suggestion: **⌥⇧R**).

### 2. "Read Clipboard"

1. New shortcut, name `Read Clipboard`.
2. Add a single **Run Shell Script**:
   ```bash
   $HOME/chatterbox/bin/readaloud clip >/tmp/readaloud.log 2>&1 &
   ```
3. Bind to e.g. **⌥⇧C** (Control+Option+C).

### 3. "Stop Reading"

1. New shortcut, name `Stop Reading`.
2. **Run Shell Script**:
   ```bash
   $HOME/chatterbox/bin/readaloud stop
   ```
3. Bind to e.g. **⌥⇧S**.

The trailing `&` in (1) and (2) returns control to the Shortcuts UI immediately so it doesn't hang during the ~5–30 s pipeline.

---

## Usage

### From a terminal

```bash
./bin/readaloud url   https://en.wikipedia.org/wiki/Apple_silicon
./bin/readaloud clip                  # auto-decides cleanup vs raw
./bin/readaloud clip --raw            # force raw — never call the cleanup LLM
./bin/readaloud clip --clean          # force cleanup even for short text
./bin/readaloud stop                  # interrupt current playback
```

Or after `pip install -e .` (which the installer runs), there's a console script on the venv path:

```bash
source .venv/bin/activate
readaloud url https://example.com
```

### From the menu bar

Look for `·` in the top-right of the menu bar:

| Glyph | Meaning |
| --- | --- |
| `·` | Idle |
| `⏳` | Preparing (fetching → cleanup LLM → TTS synthesis) |
| `▶` | Playing audio |

The menu (click the icon) has:

- **Read clipboard** — equivalent to `readaloud clip`.
- **Stop reading** — equivalent to `readaloud stop`.
- **Quit** — stops the menu bar app. Bring it back with `launchctl load -w ~/Library/LaunchAgents/com.chatterbox.menubar.plist`.

### Smart routing for clipboard

When you run `readaloud clip` without flags, it picks raw vs. cleanup with a few heuristics in [`readaloud/clean.py`](readaloud/clean.py):

- **Raw** if the text looks like terminal output: shell prompts (`$`, `>`), Python `Traceback`, diff markers (`+++`, `---`), tab-aligned columns.
- **Raw** if shorter than 200 words.
- **Cleanup** otherwise.

Override with `--raw` or `--clean`.

Both paths run through `sanitize()` before TTS (strips ANSI escapes, replaces `->` / `&` / `=>`, collapses separator lines, truncates to 8000 chars).

---

## Configuration

Knobs live at the top of each module:

- **Models / endpoints**: [`readaloud/clean.py`](readaloud/clean.py) (`OLLAMA_MODEL`, `OLLAMA_URL`), [`readaloud/speak.py`](readaloud/speak.py) (`TTS_MODEL`, `TTS_URL`).
- **Cleanup prompt**: [`readaloud/clean.py`](readaloud/clean.py) (`CLEAN_PROMPT`). Edit if you want longer summaries or domain-specific style.
- **Routing heuristics**: [`readaloud/clean.py`](readaloud/clean.py) (`should_clean`, `_TERMINAL_HINTS`).
- **Sanitization rules**: [`readaloud/sanitize.py`](readaloud/sanitize.py) (`SYMBOL_REPLACEMENTS`, `MAX_CHARS`).

`HF_TOKEN` is baked into the rendered MLX-Audio server plist at install time. To rotate:

1. Update `~/.zshrc`, `export HF_TOKEN=...` in your current shell.
2. Re-run `./scripts/install.sh` (it re-renders + reloads).

---

## Logs and diagnostics

| Service | Log |
| --- | --- |
| MLX-Audio server | `/tmp/mlx-server.log` |
| Ollama (if managed by `com.chatterbox.ollama`) | `/tmp/ollama.log` |
| Menu bar app | `/tmp/readaloud-menubar.log` |
| Last pipeline run from a Shortcut | `/tmp/readaloud.log` |

```bash
launchctl list | grep chatterbox     # are the agents alive?
lsof -i :8000 -i :11434              # are the ports bound?
curl -s http://127.0.0.1:8000/       # MLX server health
curl -s http://127.0.0.1:11434/      # Ollama health
```

---

## Troubleshooting

**"HTTP 000" or "connection refused" on port 8000.** The MLX server crashed. Check `/tmp/mlx-server.log`. Common causes:

- Missing system deps (`uvicorn`, `fastapi`, `webrtcvad`) — re-run `uv pip install -e .`.
- `pkg_resources` import error — `setuptools` got upgraded past 81. The pin in `pyproject.toml` should prevent this; re-run install if it slipped.

**Ollama responds but `gemma4:latest` not found.** `ollama pull gemma4:latest`. Check disk: the model is ~10 GB.

**The menu bar icon doesn't appear.** Tail `/tmp/readaloud-menubar.log`. If the Python process keeps respawning, the rumps app may have crashed on a state-file format error. State file format is plain text containing one of `idle`, `preparing`, `playing` — nothing else.

**Clipboard reading is empty.** `pbpaste` returns nothing for non-text clipboard contents (images, files). Copy text and try again.

**Audio is poor or pronounces acronyms wrong.** The cleanup LLM is supposed to expand acronyms (e.g. `API` → `A P I`) but isn't perfect. Tighten `CLEAN_PROMPT` or add explicit substitutions in `clean()` before the LLM call.

**Long articles feel cut off.** Cleanup truncates raw HTML to 20k chars before the LLM, and Chatterbox itself degrades past ~1000 words per call. The 200–400-word cleanup target keeps you under both. For raw text bypass, `sanitize()` truncates at 8000 chars with a "(truncated)" suffix to prevent runaway TTS jobs.

**First synthesis after a reboot takes ~10 s longer.** The MLX server lazy-loads Chatterbox on the first request — expected. Similarly, the first cleanup after Ollama has been idle adds ~30 s while `gemma4:latest` cold-loads.

**Playback won't stop with `readaloud stop`.** Stop targets the PID in `/tmp/readaloud.pid`. If you started `afplay` outside this pipeline, use `killall afplay`.

---

## Project layout

```
.
├── README.md
├── LICENSE                          # MIT
├── pyproject.toml                   # explicit deps with the install gotchas pinned
├── .gitignore
├── readaloud/                       # the package
│   ├── __init__.py
│   ├── __main__.py                  # python -m readaloud
│   ├── cli.py                       # argparse: url | clip | stop
│   ├── fetch.py                     # URL fetcher
│   ├── clipboard.py                 # pbpaste reader
│   ├── clean.py                     # Ollama cleanup + should_clean() heuristic
│   ├── sanitize.py                  # ANSI strip, symbol replace, truncate
│   ├── speak.py                     # TTS synth + Popen-based play with PID tracking
│   └── state.py                     # /tmp/readaloud.state writer
├── menubar.py                       # rumps menu bar app
├── bin/
│   └── readaloud                    # venv-activating wrapper for Shortcuts/launchd
├── launchagents/
│   ├── com.chatterbox.ollama.plist.tmpl
│   ├── com.chatterbox.mlx-audio-server.plist.tmpl
│   └── com.chatterbox.menubar.plist.tmpl
├── scripts/
│   ├── install.sh
│   └── uninstall.sh
└── clipboard-readaloud-sprint.md    # clipboard-mode sprint plan (shipped — see header)
```

---

## Known limitations / not-yet-built

- **No queue.** Triggering a new read while one is playing first calls `stop_existing()` (so the old playback ends), then starts the new one. Two reads in quick succession won't stack.
- **Single voice.** Default Chatterbox voice. Custom voice cloning is supported by the model but not wired up here.
- **No Google Docs or Slack adapter yet.** Both are easy: Docs published-to-web works through the URL fetcher today; Slack and private Docs need OAuth.
- **HF token in the plist.** It's stored in `~/Library/LaunchAgents/com.chatterbox.mlx-audio-server.plist` after install. If you rotate it, re-run the installer.
- **Apple Silicon only.** No Intel/Linux/Windows support; this leans hard on MLX + macOS launchd + macOS Shortcuts.

---

## License

MIT. See [LICENSE](LICENSE).
