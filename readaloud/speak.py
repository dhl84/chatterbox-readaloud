"""TTS synthesis + audio playback with PID-tracked stop support."""
import os
import signal
import subprocess
from pathlib import Path

from openai import OpenAI

from .sanitize import sanitize
from .state import set_state

TTS_MODEL = "mlx-community/chatterbox-turbo-fp16"
TTS_URL = "http://127.0.0.1:8000/v1"
OUTPUT = "/tmp/readaloud.wav"
PID_FILE = Path("/tmp/readaloud.pid")


def synthesize(text: str, out: str = OUTPUT) -> str:
    client = OpenAI(base_url=TTS_URL, api_key="not-needed")
    resp = client.audio.speech.create(model=TTS_MODEL, voice="default", input=sanitize(text))
    resp.stream_to_file(out)
    return out


def stop_existing() -> bool:
    """Kill any prior afplay tracked by /tmp/readaloud.pid. Returns True if it killed something."""
    killed = False
    try:
        pid = int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        pid = None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            pass
    PID_FILE.unlink(missing_ok=True)
    return killed


def play(path: str = OUTPUT) -> None:
    stop_existing()
    proc = subprocess.Popen(["afplay", path])
    PID_FILE.write_text(str(proc.pid))
    try:
        set_state("playing")
        proc.wait()
    finally:
        PID_FILE.unlink(missing_ok=True)
