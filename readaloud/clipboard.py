"""Read text from the macOS clipboard via pbpaste."""
import subprocess


def read_clipboard() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
    return r.stdout
