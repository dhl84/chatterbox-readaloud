"""Pre-TTS text sanitization. Always runs, both raw and cleaned paths."""
import re

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SEPARATOR_RE = re.compile(r"([=\-_*])\1{3,}")  # 4+ in a row → single period
SYMBOL_REPLACEMENTS = [
    (re.compile(r"=>"), " implies "),
    (re.compile(r"->"), " to "),
    (re.compile(r"<-"), " from "),
    (re.compile(r"\s&\s"), " and "),
    (re.compile(r"\s\|\s"), " or "),
]
MAX_CHARS = 8000
TRUNCATE_SUFFIX = " ... (truncated)"


def sanitize(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = SEPARATOR_RE.sub(".", text)
    for pat, repl in SYMBOL_REPLACEMENTS:
        text = pat.sub(repl, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + TRUNCATE_SUFFIX
    return text
