"""Tests for what the command line prints when Google Drive can't be reached.

Each case runs the real `sirgal scan` in a child process, so the checks see exactly
what a person would: stdout, stderr and the exit code. Only Google's listing call
is faked. The first page lists a file, then the second page fails.
"""

import socket
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest import mock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from sirgal import cli

FILE_ID = "1ZxSecretFileIdQw7"
FILE_NAME = "payroll_2026.csv"
PAGE_TOKEN = "pageTokenSecret42"
LIST_URL = f"https://www.googleapis.com/drive/v3/files?pageToken={PAGE_TOKEN}&fileId={FILE_ID}"
GOOGLE_TEXT = "Backend Error while reading"
# Nothing from the failed request or the half-finished listing may be printed.
SECRETS = [FILE_ID, FILE_NAME, PAGE_TOKEN, "googleapis.com", GOOGLE_TEXT]

SCANNING = "Scanning Google Drive (read-only). Your browser may open to log in."
ADVICE = "Check your connection and run the scan again."
# google.api_core warns on import when Python is older than it supports. It's
# printed before Sirgal runs, says nothing about the scan, and would break the
# exact stderr check. Only that one warning is hidden; any other still shows.
OLD_PYTHON_WARNING = "ignore:You are using a non-supported Python version:FutureWarning"
CASES = {
    "timeout": "network timeout",
    "http-503": "Google returned 503",
    "dns": "network error",
}


def make_error(case):
    """A listing failure whose own text carries every secret, the way Google's errors do."""
    if case == "timeout":
        return TimeoutError(f"timed out reading {LIST_URL}: {GOOGLE_TEXT} {FILE_NAME}")
    if case == "http-503":
        body = f'{{"error": {{"message": "{GOOGLE_TEXT} {FILE_ID} {FILE_NAME}"}}}}'.encode()
        return HttpError(httplib2.Response({"status": 503}), body, uri=LIST_URL)
    if case == "dns":
        return socket.gaierror(8, f"nodename nor servname known: {LIST_URL} {GOOGLE_TEXT} {FILE_NAME}")
    raise ValueError(case)


DRIVER = textwrap.dedent("""
    import sys
    from unittest import mock

    sys.path.insert(0, {tests!r})
    from test_cli import FILE_ID, FILE_NAME, PAGE_TOKEN, make_error

    from sirgal import cli
    from sirgal.connectors import gdrive

    first_page = {{
        "files": [{{"id": FILE_ID, "name": FILE_NAME, "mimeType": "text/csv", "permissions": []}}],
        "nextPageToken": PAGE_TOKEN,
    }}
    service = mock.MagicMock()
    service.files.return_value.list.return_value.execute.side_effect = [first_page, make_error({case!r})]
    sys.argv = ["sirgal", "scan", "--source", "gdrive", "--report", "report.json"]
    with mock.patch.object(gdrive, "build", return_value=service), mock.patch.object(gdrive, "get_credentials"):
        cli.main()
""")


@pytest.fixture(scope="module", params=list(CASES))
def failed_scan(request, tmp_path_factory):
    case = request.param
    workdir = tmp_path_factory.mktemp(case)
    code = DRIVER.format(tests=str(Path(__file__).parent), case=case)
    run = subprocess.run([sys.executable, "-W", OLD_PYTHON_WARNING, "-c", code],
                         cwd=workdir, capture_output=True, text=True, timeout=60)
    return case, run, workdir


@pytest.mark.parametrize("case", list(CASES))
def test_fake_errors_really_carry_the_secrets(case):
    # Guards the checks below: they only prove something if the raw error holds the secrets.
    raw = f"{make_error(case)} {make_error(case)!r}"
    if case == "http-503":
        raw += make_error(case).content.decode()
    for secret in SECRETS:
        assert secret in raw


def test_exits_with_code_one(failed_scan):
    _, run, _ = failed_scan
    assert run.returncode == 1


def test_stderr_is_exactly_one_fixed_line(failed_scan):
    case, run, _ = failed_scan
    assert run.stderr.splitlines() == [f"Couldn't reach Google Drive ({CASES[case]}). {ADVICE}"]


def test_stdout_holds_only_the_opening_line(failed_scan):
    _, run, _ = failed_scan
    assert run.stdout.splitlines() == [SCANNING, ""]


def test_no_traceback_is_printed(failed_scan):
    _, run, _ = failed_scan
    output = run.stdout + run.stderr
    assert "Traceback" not in output
    assert 'File "' not in output
    assert "line " not in output
    for name in ("TimeoutError", "HttpError", "gaierror", "SystemExit"):
        assert name not in output


@pytest.mark.parametrize("secret", SECRETS)
def test_no_file_id_url_or_google_text_is_printed(failed_scan, secret):
    _, run, _ = failed_scan
    assert secret not in run.stdout
    assert secret not in run.stderr


def test_no_results_or_report_from_a_half_finished_listing(failed_scan):
    _, run, workdir = failed_scan
    assert "files scanned" not in run.stdout
    assert "RISK" not in run.stdout
    assert not (workdir / "report.json").exists()
    assert list(workdir.iterdir()) == []


@pytest.mark.parametrize("error", [PermissionError("token file is read-only"), ValueError("a bug")])
def test_local_problems_and_bugs_are_not_reported_as_network_failures(error):
    # Only failures talking to Google get the short message. Anything else must
    # stay visible, so a broken disk or a bug isn't hidden behind "check your connection".
    with mock.patch("sirgal.connectors.gdrive.scan", side_effect=error):
        with pytest.raises(type(error)) as raised:
            cli.run_scan("gdrive")
    assert raised.value is error
