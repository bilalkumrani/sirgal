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


def test_office_files_are_read_and_scans_are_unknown():
    from test_extract import make_pdf, make_xlsx

    files = {
        "1": make_xlsx({"Summary": [["Team"]], "Detail": [["Name", "SSN"], ["Ali", "251-29-2287"]]}),
        "2": make_pdf(shapes_only=True),
        "3": make_pdf(["Team lunch on Friday"]),
    }
    items = [
        {"id": "1", "name": "payroll.xlsx", "size": "5000", "permissions": [OWNER, FRIEND],
         "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"id": "2", "name": "passport.pdf", "size": "1500", "permissions": [OWNER, FRIEND], "mimeType": "application/pdf"},
        {"id": "3", "name": "lunch.pdf", "size": "1500", "permissions": [OWNER, ANYONE_LINK], "mimeType": "application/pdf"},
        {"id": "4", "name": "logo.png", "size": "900", "permissions": [OWNER, ANYONE_LINK], "mimeType": "image/png"},
    ]
    service = mock.MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": items}
    downloads = {}

    def get_media(fileId):
        downloads["last"] = fileId
        return fileId

    service.files.return_value.get_media.side_effect = get_media
    with mock.patch.object(gdrive, "build", return_value=service), \
         mock.patch.object(gdrive, "get_credentials"), \
         mock.patch.object(gdrive, "_download", side_effect=lambda request: files[request]):
        results = {r["path"]: r for r in gdrive.scan()}

    assert results["payroll.xlsx"]["risk"] == "high"          # SSN on the second sheet
    assert results["passport.pdf"]["risk"] == "unknown"       # a scan: never OK
    assert "no readable text" in results["passport.pdf"]["note"]
    assert results["lunch.pdf"]["risk"] == "ok"
    assert results["logo.png"]["note"] == "file type not supported yet"
    assert "251-29-2287" not in str(results)


def test_google_sheets_are_exported_as_excel_so_every_tab_is_checked():
    item = {"id": "s", "name": "Payroll", "mimeType": "application/vnd.google-apps.spreadsheet"}
    service = mock.MagicMock()
    with mock.patch.object(gdrive, "_download", return_value=b"not a real file"):
        gdrive._read_text(service, item)
    service.files.return_value.export_media.assert_called_once_with(fileId="s", mimeType=gdrive.XLSX_MIME)
