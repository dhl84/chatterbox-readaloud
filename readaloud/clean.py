"""Ollama-backed cleanup pass + heuristic for when to run it."""
import re

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"

CLEAN_PROMPT = """You will be given the raw text of a web page or document.
Rewrite it as a short spoken summary suitable for text-to-speech. Rules:
- Strip nav, ads, cookie banners, footers, related-article lists.
- Keep claims, numbers, names, decisions, and instructions.
- Cut hedging ("it's worth noting", "important to consider").
- Expand acronyms on first use (API -> A P I) so TTS pronounces them.
- Output plain prose only. No markdown, no headers, no bullets.
- Do not preface the output with phrases like "Here is the summary:".
- Target 200-400 words unless the source is very short.
Source text follows.
---
"""

# Models often slip in a leading meta-comment; strip it before returning.
PREAMBLE_PATTERNS = [
    re.compile(r"^\s*here(?:'s| is) (?:a |the |my )?(?:summary|cleaned[-\s]up version|spoken version)[^\n]*\n", re.IGNORECASE),
    re.compile(r"^\s*sure[^\n]*\n", re.IGNORECASE),
    re.compile(r"^\s*okay[^\n]*\n", re.IGNORECASE),
]


def _strip_preamble(text: str) -> str:
    for pat in PREAMBLE_PATTERNS:
        text = pat.sub("", text, count=1)
    return text.strip()


def clean(raw: str) -> str:
    r = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL,
        "prompt": CLEAN_PROMPT + raw[:20000],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 16384},
    }, timeout=300)
    r.raise_for_status()
    return _strip_preamble(r.json()["response"])


_TERMINAL_HINTS = re.compile(
    r"(?m)"
    r"^(?:\$|>|\+\+\+|---|\s*at\s)|"  # shell prompts, diff markers, stack-trace 'at' lines
    r"\bTraceback\b|"
    r"^\s*File \"[^\"]+\", line \d+|"  # python tracebacks
    r"^\s*[A-Za-z]+Error:"
)


def _is_terminalish(text: str) -> bool:
    if _TERMINAL_HINTS.search(text):
        return True
    # Mostly tab-aligned columnar output
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    tabby = sum(1 for ln in lines if ln.count("\t") >= 2)
    if tabby >= max(3, len(lines) // 4):
        return True
    return False


def should_clean(text: str) -> bool:
    """Decide whether to route through the LLM cleanup or speak raw."""
    if _is_terminalish(text):
        return False
    if len(text.split()) < 200:
        return False
    return True
