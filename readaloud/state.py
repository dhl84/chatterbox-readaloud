"""Single-writer state file for the menu bar indicator to poll."""
from pathlib import Path

STATE_FILE = Path("/tmp/readaloud.state")


def set_state(state: str) -> None:
    STATE_FILE.write_text(state)
