"""Google Drive connector.

Logs in with read-only access, lists every file you own with who it is shared
with, and checks text files for sensitive data. File contents are read in
memory, checked, and discarded. Only counts of what was found are kept.
"""

import io
import os
from pathlib import Path

import httplib2
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from sirgal.detectors import HIGH, scan_text, worst_severity
from sirgal.extract import XLSX, extract_text, kind_for
from sirgal.risk import ANYONE, DOMAIN, PEOPLE, PRIVATE, rate

# Read-only. With this scope Sirgal cannot change, delete or re-share anything.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CONFIG_DIR = Path.home() / ".config" / "sirgal"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "gdrive-token.json"

FOLDER_TYPE = "application/vnd.google-apps.folder"
FIELDS = "nextPageToken, files(id, name, mimeType, size, parents, webViewLink, permissions(type, role, domain))"

# Files we can read as plain text.
TEXT_TYPES = {"text/plain", "text/csv", "text/markdown", "text/tab-separated-values", "application/json"}
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Google's own formats are exported first. Sheets go out as Excel so that every
# tab is checked, not just the first one.
EXPORT_AS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": XLSX_MIME,
}
MAX_BYTES = 10 * 1024 * 1024  # skip files bigger than 10 MB for now
RETRY_COUNT = 3
DOWNLOAD_ERRORS = (
    HttpError,
    httplib2.HttpLib2Error,
    TransportError,
    TimeoutError,
    OSError,
)


def get_credentials():
    """Return valid credentials, asking the user to log in only when needed."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except RefreshError:
            pass  # token was revoked or expired for good, so log in again

    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            f"Missing {CREDENTIALS_FILE}\n"
            "Create a Desktop OAuth client in Google Cloud Console and save its JSON there."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds):
    """Save the login token so only this user account can read it."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)


def _list_owned_items(service, progress=None):
    """Every file and folder you own that isn't in the trash, page by page."""
    items, page_token = [], None
    while True:
        response = service.files().list(
            q="'me' in owners and trashed = false",
            fields=FIELDS,
            pageSize=100,
            pageToken=page_token,
        ).execute(num_retries=RETRY_COUNT)
        items.extend(response.get("files", []))
        if progress:
            progress.status(f"Listing files... {len(items)} found")
        page_token = response.get("nextPageToken")
        if not page_token:
            return items


def describe_sharing(permissions):
    """Turn Drive's permission list into (exposure level, readable label)."""
    others = [p for p in permissions if p.get("role") != "owner"]
    if any(p.get("type") == "anyone" for p in others):
        return ANYONE, "anyone with the link"
    domains = [p.get("domain") for p in others if p.get("type") == "domain"]
    if domains:
        return DOMAIN, f"everyone at {domains[0]}"
    people = [p for p in others if p.get("type") in ("user", "group")]
    if people:
        noun = "person" if len(people) == 1 else "people"
        return PEOPLE, f"{len(people)} {noun}"
    return PRIVATE, "private"


def build_path(item, folders):
    """Folder path like acme-robotics/HR/salaries_2026.csv, built from parent IDs."""
    parts = [item["name"]]
    parent_ids = item.get("parents") or []
    seen = set()
    while parent_ids and parent_ids[0] in folders and parent_ids[0] not in seen:
        seen.add(parent_ids[0])
        folder = folders[parent_ids[0]]
        parts.append(folder["name"])
        parent_ids = folder.get("parents") or []
    return "/".join(reversed(parts))


def supported(item):
    """True if Sirgal knows how to read this kind of file."""
    mime = item["mimeType"]
    return mime in TEXT_TYPES or mime in EXPORT_AS or kind_for(mime) is not None


def _download(request):
    buffer = io.BytesIO()  # in memory only, never written to disk
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk(num_retries=RETRY_COUNT)
    return buffer.getvalue()


def _download_problem(error):
    """Return a short, non-sensitive reason for a failed download."""
    if isinstance(error, HttpError):
        return f"Google returned {error.resp.status}"
    if (
        isinstance(error, TimeoutError)
        or "timeout" in str(error).lower()
        or "timed out" in str(error).lower()
    ):
        return "network timeout"
    return "network error"


def _read_text(service, item):
    """Download a file into memory and return its text, or None if there is none to read."""
    mime = item["mimeType"]
    if mime in EXPORT_AS:
        target = EXPORT_AS[mime]
        data = _download(service.files().export_media(fileId=item["id"], mimeType=target))
    elif supported(item):
        if int(item.get("size", 0)) > MAX_BYTES:
            return None
        target = mime
        data = _download(service.files().get_media(fileId=item["id"]))
    else:
        return None

    kind = XLSX if target == XLSX_MIME else kind_for(target)
    if kind:
        return extract_text(data, kind)  # PDF, Word, Excel: None if no text inside
    return data.decode("utf-8", errors="replace")


def scan(model=None, progress=None):
    """Check every owned file's sharing and content.

    model: an optional sirgal.ner.ModelDetector. When given, it also checks
    shared files that the rules haven't already rated high. Private files are
    always OK, so the model never needs to read them.
    progress: an optional sirgal.progress.Progress to show how far along we are.
    """
    service = build("drive", "v3", credentials=get_credentials(), cache_discovery=False)
    items = _list_owned_items(service, progress)
    folders = {i["id"]: i for i in items if i["mimeType"] == FOLDER_TYPE}
    files = [i for i in items if i["mimeType"] != FOLDER_TYPE]

    results = []
    for done, item in enumerate(files):
        path = build_path(item, folders)
        if progress:
            progress.step(done, len(files), path)
        exposure, sharing = describe_sharing(item.get("permissions", []))

        download_error = None
        try:
            text = _read_text(service, item)
        except DOWNLOAD_ERRORS as error:
            text = None
            download_error = error
        checked = text is not None
        found = scan_text(text, item["name"]) if checked else {}
        if model is not None and checked and exposure != PRIVATE and worst_severity(found) != HIGH:
            for kind, count in model.scan_text(text).items():
                found[kind] = found.get(kind, 0) + count
        del text  # the contents are not kept anywhere

        note = ""
        if download_error is not None:
            note = "couldn't download: " + _download_problem(download_error)
        elif not checked:
            if not supported(item):
                note = "file type not supported yet"
            elif int(item.get("size", 0)) > MAX_BYTES:
                note = "larger than 10 MB, skipped for now"
            else:
                note = "no readable text, maybe a scan or a protected file"

        results.append({
            "path": path,
            "note": note,
            "link": item.get("webViewLink", ""),
            "exposure": exposure,
            "sharing": sharing,
            "checked": checked,
            "found": found,
            "risk": rate(exposure, worst_severity(found), checked),
        })
    if progress:
        progress.step(len(files), len(files))
    return results
