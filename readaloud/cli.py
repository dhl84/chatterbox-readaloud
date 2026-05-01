"""argparse dispatch for the readaloud package."""
import argparse
import sys

from . import clean as clean_mod
from . import clipboard as clipboard_mod
from . import fetch as fetch_mod
from . import speak as speak_mod
from .state import set_state


def _do_url(args: argparse.Namespace) -> int:
    try:
        set_state("preparing")
        print(f"Fetching {args.url}...")
        raw = fetch_mod.fetch(args.url)
        print(f"Cleaning {len(raw)} chars via {clean_mod.OLLAMA_MODEL}...")
        cleaned = clean_mod.clean(raw)
        print(f"--- Cleaned ({len(cleaned)} chars) ---\n{cleaned}\n---")
        print("Synthesizing...")
        speak_mod.synthesize(cleaned)
        speak_mod.play()
    finally:
        set_state("idle")
    return 0


def _do_clip(args: argparse.Namespace) -> int:
    text = clipboard_mod.read_clipboard()
    if not text.strip():
        print("Clipboard is empty (or contains non-text content).", file=sys.stderr)
        return 1
    if args.raw:
        do_clean = False
    elif args.clean:
        do_clean = True
    else:
        do_clean = clean_mod.should_clean(text)
    try:
        set_state("preparing")
        if do_clean:
            print(f"Cleaning {len(text)} chars via {clean_mod.OLLAMA_MODEL}...")
            text = clean_mod.clean(text)
            print(f"--- Cleaned ({len(text)} chars) ---\n{text}\n---")
        else:
            print(f"Speaking {len(text)} chars raw.")
        speak_mod.synthesize(text)
        speak_mod.play()
    finally:
        set_state("idle")
    return 0


def _do_stop(_args: argparse.Namespace) -> int:
    killed = speak_mod.stop_existing()
    set_state("idle")
    print("stopped" if killed else "nothing playing")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="readaloud")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("url", help="Fetch a URL, clean it, speak it.")
    p_url.add_argument("url")
    p_url.set_defaults(func=_do_url)

    p_clip = sub.add_parser("clip", help="Read whatever is on the macOS clipboard.")
    g = p_clip.add_mutually_exclusive_group()
    g.add_argument("--raw", action="store_true", help="Skip the LLM cleanup pass.")
    g.add_argument("--clean", action="store_true", help="Force the LLM cleanup pass.")
    p_clip.set_defaults(func=_do_clip)

    p_stop = sub.add_parser("stop", help="Interrupt the current playback.")
    p_stop.set_defaults(func=_do_stop)

    args = p.parse_args(argv)
    return args.func(args)
