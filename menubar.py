#!/usr/bin/env python3
"""Menu bar indicator for the readaloud pipeline.

Polls /tmp/readaloud.state every ~400ms; the pipeline writes one of
'preparing', 'playing', or 'idle' there. Icon updates accordingly.
"""
import subprocess
from pathlib import Path

import rumps

STATE_FILE = Path("/tmp/readaloud.state")
HERE = Path(__file__).resolve().parent
READALOUD_BIN = HERE / "bin" / "readaloud"
IDLE_GLYPH = "·"  # tiny middle-dot, keeps the menu clickable when nothing is playing
GLYPHS = {"idle": IDLE_GLYPH, "preparing": "⏳", "playing": "▶"}


class ReadAloudApp(rumps.App):
    def __init__(self):
        super().__init__("ReadAloud", title=IDLE_GLYPH, quit_button=None)
        self.menu = ["Read clipboard", "Stop reading", None, "Quit"]
        self._state = "idle"
        self._timer = rumps.Timer(self._tick, 0.4)
        self._timer.start()

    def _tick(self, _):
        try:
            state = STATE_FILE.read_text().strip() or "idle"
        except FileNotFoundError:
            state = "idle"
        if state == self._state:
            return
        self._state = state
        self.title = GLYPHS.get(state, IDLE_GLYPH)

    @rumps.clicked("Read clipboard")
    def _read_clip(self, _):
        subprocess.Popen([str(READALOUD_BIN), "clip"])

    @rumps.clicked("Stop reading")
    def _stop(self, _):
        subprocess.run([str(READALOUD_BIN), "stop"], check=False)

    @rumps.clicked("Quit")
    def _quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    ReadAloudApp().run()
