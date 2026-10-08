"""Tests for the Google Drive connector. Google is replaced by a fake, so no login is needed."""

from unittest import mock

from sirgal.connectors import gdrive
from sirgal.risk import ANYONE, DOMAIN, PEOPLE, PRIVATE

OWNER = {"type": "user", "role": "owner"}
FRIEND = {"type": "user", "role": "reader"}
ANYONE_LINK = {"type": "anyone", "role": "reader"}
FOLDER = gdrive.FOLDER_TYPE


def test_describe_sharing():
    assert gdrive.describe_sharing([OWNER]) == (PRIVATE, "private")
    assert gdrive.describe_sharing([OWNER, FRIEND]) == (PEOPLE, "1 person")
    assert gdrive.describe_sharing([OWNER, FRIEND, FRIEND]) == (PEOPLE, "2 people")
    assert gdrive.describe_sharing([OWNER, FRIEND, ANYONE_LINK]) == (ANYONE, "anyone with the link")
    domain = {"type": "domain", "role": "reader", "domain": "acme.example"}
    assert gdrive.describe_sharing([OWNER, domain]) == (DOMAIN, "everyone at acme.example")


def test_build_path_walks_up_folders():
    folders = {
        "a": {"id": "a", "name": "acme-robotics", "parents": ["ROOT"]},
        "b": {"id": "b", "name": "HR", "parents": ["a"]},
    }
    item = {"name": "salaries.csv", "parents": ["b"]}
    assert gdrive.build_path(item, folders) == "acme-robotics/HR/salaries.csv"


def test_build_path_survives_a_folder_loop():
    folders = {
        "a": {"id": "a", "name": "A", "parents": ["b"]},
        "b": {"id": "b", "name": "B", "parents": ["a"]},
    }
    assert gdrive.build_path({"name": "f.txt", "parents": ["a"]}, folders) == "B/A/f.txt"


def _fake_drive(items, contents):
    """Patch Google out: listing returns `items`, reading returns `contents[id]`."""
    service = mock.MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": items}

    def fake_read(_service, item):
        return contents.get(item["id"])

    return [
        mock.patch.object(gdrive, "build", return_value=service),
        mock.patch.object(gdrive, "get_credentials"),
        mock.patch.object(gdrive, "_read_text", side_effect=fake_read),
    ]


def test_scan_rates_each_file():
    items = [
        {"id": "f", "name": "HR", "mimeType": FOLDER, "parents": ["ROOT"]},
        {"id": "1", "name": "ssn.csv", "mimeType": "text/csv", "parents": ["f"], "permissions": [OWNER, ANYONE_LINK]},
        {"id": "2", "name": "notes.txt", "mimeType": "text/plain", "parents": ["f"], "permissions": [OWNER, ANYONE_LINK]},
        {"id": "3", "name": "cards.csv", "mimeType": "text/csv", "parents": ["f"], "permissions": [OWNER]},
        {"id": "4", "name": "scan.pdf", "mimeType": "application/pdf", "parents": ["f"], "permissions": [OWNER, FRIEND]},
    ]
    contents = {
        "1": "name,ssn\nAli,251-29-2287",
        "2": "Team lunch on Friday.",
        "3": "card\n4111 1111 1111 1111",
        # "4" is a PDF, which we can't read yet
    }
    patches = _fake_drive(items, contents)
    for p in patches:
        p.start()
    try:
        results = {r["path"]: r for r in gdrive.scan()}
    finally:
        for p in patches:
            p.stop()

    assert set(results) == {"HR/ssn.csv", "HR/notes.txt", "HR/cards.csv", "HR/scan.pdf"}  # folder not listed
    assert results["HR/ssn.csv"]["risk"] == "high"
    assert results["HR/notes.txt"]["risk"] == "ok"
    assert results["HR/cards.csv"]["risk"] == "ok"  # sensitive but private
    assert results["HR/scan.pdf"]["risk"] == "unknown"
    assert results["HR/scan.pdf"]["checked"] is False


def test_scan_results_hold_no_file_contents():
    items = [{"id": "1", "name": "ssn.csv", "mimeType": "text/csv", "permissions": [OWNER, FRIEND]}]
    patches = _fake_drive(items, {"1": "Ali,251-29-2287"})
    for p in patches:
        p.start()
    try:
        results = gdrive.scan()
    finally:
        for p in patches:
            p.stop()
    assert "251-29-2287" not in str(results)
