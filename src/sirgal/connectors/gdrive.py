"""Google Drive connector.

Logs in with read-only access and lists every file you own, together with
who it is shared with. It does not download any file contents.
"""

import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Read-only. With this scope Sirgal cannot change, delete or re-share anything.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CONFIG_DIR = Path.home() / ".config" / "sirgal"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "gdrive-token.json"

FOLDER_TYPE = "application/vnd.google-apps.folder"
FIELDS = "nextPageToken, files(id, name, mimeType, parents, webViewLink, permissions(type, role, domain))"

# Lower number = more exposed. Used to sort the worst files to the top.
ANYONE, DOMAIN, PEOPLE, PRIVATE = 0, 1, 2, 3


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


def _list_owned_items(service):
    """Every file and folder you own that isn't in the trash, page by page."""
    items, page_token = [], None
    while True:
        response = service.files().list(
            q="'me' in owners and trashed = false",
            fields=FIELDS,
            pageSize=100,
            pageToken=page_token,
        ).execute()
        items.extend(response.get("files", []))
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


def scan():
    """List owned files with their sharing, most exposed first."""
    service = build("drive", "v3", credentials=get_credentials(), cache_discovery=False)
    items = _list_owned_items(service)
    folders = {i["id"]: i for i in items if i["mimeType"] == FOLDER_TYPE}

    results = []
    for item in items:
        if item["mimeType"] == FOLDER_TYPE:
            continue
        level, label = describe_sharing(item.get("permissions", []))
        results.append({
            "path": build_path(item, folders),
            "link": item.get("webViewLink", ""),
            "level": level,
            "sharing": label,
        })
    results.sort(key=lambda r: (r["level"], r["path"]))
    return results
