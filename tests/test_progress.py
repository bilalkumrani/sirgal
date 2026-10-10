"""Tests for the one-line progress display."""

import io
from unittest import mock

from sirgal.connectors import gdrive
from sirgal.progress import Progress


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


def test_silent_when_not_a_terminal():
    out = io.StringIO()  # like a pipe, a log file or CI
    progress = Progress(out)
    progress.status("Listing files... 3 found")
    progress.step(1, 3, "a.txt")
    progress.clear()
    assert out.getvalue() == ""


def test_shows_a_bar_with_counts_and_the_current_file():
    out = FakeTerminal()
    Progress(out).step(5, 10, "HR/payroll.xlsx")
    line = out.getvalue()
    assert "5/10" in line and "HR/payroll.xlsx" in line
    assert "██████████░░░░░░░░░░" in line  # half the bar filled


def test_redraws_the_same_line_instead_of_printing_new_ones():
    out = FakeTerminal()
    progress = Progress(out)
    for i in range(4):
        progress.step(i, 4)
    assert "\n" not in out.getvalue()
    assert out.getvalue().count("\r") == 4


def test_long_lines_are_cut_to_the_terminal_width():
    out = FakeTerminal()
    with mock.patch("shutil.get_terminal_size", return_value=mock.Mock(columns=40)):
        Progress(out).step(1, 2, "a/very/long/path/" * 10)
    last = out.getvalue().split("\033[K")[-1]
    assert len(last) <= 39 and last.endswith("…")


def test_scan_reports_progress_for_every_file():
    items = [{"id": str(i), "name": f"f{i}.txt", "mimeType": "text/plain",
              "permissions": [{"type": "user", "role": "owner"}]} for i in range(3)]
    service = mock.MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": items}
    progress = mock.MagicMock()
    with mock.patch.object(gdrive, "build", return_value=service), \
         mock.patch.object(gdrive, "get_credentials"), \
         mock.patch.object(gdrive, "_read_text", return_value="hello"):
        gdrive.scan(progress=progress)
    progress.status.assert_called_with("Listing files... 3 found")
    steps = [c.args[:2] for c in progress.step.call_args_list]
    assert steps == [(0, 3), (1, 3), (2, 3), (3, 3)]
