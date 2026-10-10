"""A one-line progress display for the terminal, with no extra packages.

It redraws a single line on stderr, so the scan results printed to stdout stay
clean. In a pipe, a log file or CI there's no terminal, so it stays silent.
"""

import shutil
import sys
import time

BAR_WIDTH = 20


class Progress:
    def __init__(self, stream=None, enabled=None):
        self.stream = stream or sys.stderr
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self._started = None

    def status(self, text):
        """Show a short message, like "Listing files... 120 found"."""
        self._draw(text)

    def step(self, done, total, label=""):
        """Show a bar for `done` out of `total`, with a rough time left."""
        if self._started is None or done == 0:
            self._started = time.monotonic()
        filled = BAR_WIDTH if not total else int(BAR_WIDTH * done / total)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        text = f"Checking files  {bar}  {done}/{total}"
        left = self._time_left(done, total)
        if left:
            text += f"  {left}"
        if label:
            text += f"  {label}"
        self._draw(text)

    def clear(self):
        """Remove the progress line before printing results."""
        if self.enabled:
            self.stream.write("\r\033[K")
            self.stream.flush()

    def _time_left(self, done, total):
        if not self._started or done < 3 or done >= total:
            return ""
        elapsed = time.monotonic() - self._started
        seconds = elapsed / done * (total - done)
        if seconds < 60:
            return f"about {max(1, round(seconds))} s left"
        return f"about {round(seconds / 60)} min left"

    def _draw(self, text):
        if not self.enabled:
            return
        width = shutil.get_terminal_size((100, 20)).columns - 1
        if len(text) > width:
            text = text[: width - 1] + "…"
        self.stream.write("\r\033[K" + text)
        self.stream.flush()
