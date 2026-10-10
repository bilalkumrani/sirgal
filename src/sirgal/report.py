"""Save scan results as a shareable HTML report or a CSV file.

Reports list file names, links and sharing settings, never file contents.
File names come from users, so everything is escaped: in HTML, a file named
<script>...</script> stays plain text; in CSV, a name starting with "=" can't
turn into a spreadsheet formula. The report is readable only by the user who
ran the scan, because file names and links can be sensitive too.
"""

import csv
import html
import io
import os
from datetime import datetime

from sirgal import __version__
from sirgal.detectors import HIGH, LOW, MEDIUM, SEVERITY
from sirgal.risk import ANYONE, DOMAIN, OK, RISK_ORDER, UNKNOWN

# (one, many). Types without a count are described in words only.
LABELS = {
    "ssn": ("SSN", "SSNs"),
    "credit_card": ("card number", "card numbers"),
    "iban": ("bank IBAN", "bank IBANs"),
    "password": ("password", "passwords"),
    "phone": ("phone number", "phone numbers"),
    "email": ("email", "emails"),
    "home_address": ("home address", "home addresses"),
    "health_info": ("health detail", "health details"),
}
NO_COUNT = {"salary": "salary data", "date_of_birth": "dates of birth"}
LEVELS = [HIGH, MEDIUM, LOW, UNKNOWN, OK]


def describe_found(found: dict) -> str:
    """{'ssn': 25, 'email': 1} -> '25 SSNs, 1 email'"""
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    parts = []
    for kind in sorted(found, key=lambda k: (order[SEVERITY[k]], k)):
        if kind in NO_COUNT:
            parts.append(NO_COUNT[kind])
        else:
            one, many = LABELS[kind]
            parts.append(f"{found[kind]} {one if found[kind] == 1 else many}")
    return ", ".join(parts)


def sort_results(results):
    """Riskiest first, then most exposed, then by path."""
    return sorted(results, key=lambda r: (RISK_ORDER[r["risk"]], r["exposure"], r["path"]))


def count_by_risk(results) -> dict:
    counts = {level: 0 for level in LEVELS}
    for r in results:
        counts[r["risk"]] += 1
    return counts


def not_checked_reason(r) -> str:
    return r.get("note") or "file type not supported yet"


def found_text(r) -> str:
    if not r["checked"]:
        return f"Not checked: {not_checked_reason(r)}"
    return describe_found(r["found"])


def what_to_do(r) -> str:
    """A short, concrete next step for one file."""
    if r["risk"] == OK:
        return ""
    if r["risk"] == UNKNOWN:
        return "Open it and check by hand"
    if r["exposure"] == ANYONE:
        return "Turn off link sharing: set General access to Restricted"
    if r["exposure"] == DOMAIN:
        return "Share it only with the people who need it, not the whole organization"
    return "Check that everyone who has access needs it"


def safe_link(url) -> str:
    """Only plain https links make it into the report."""
    return url if isinstance(url, str) and url.startswith("https://") else ""


def write_report(results, path, meta=None) -> str:
    """Write an .html or .csv report, readable only by the current user. Returns the path."""
    meta = meta or {}
    rows = sort_results(results)
    if str(path).lower().endswith(".csv"):
        content = _csv(rows)
    else:
        content = _html(rows, meta)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    os.chmod(path, 0o600)
    return str(path)


# ---------- CSV ----------

def _csv_cell(value) -> str:
    """Stop spreadsheet apps from treating a cell as a formula."""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text


def _csv(rows) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["risk", "file", "shared_with", "found", "what_to_do", "link"])
    for r in rows:
        writer.writerow([_csv_cell(v) for v in (
            r["risk"], r["path"], r["sharing"], found_text(r), what_to_do(r), safe_link(r.get("link")),
        )])
    return out.getvalue()


# ---------- HTML ----------

def _e(value) -> str:
    return html.escape(str(value), quote=True)


STYLE = """
:root { --paper:#FFFFFF; --wash:#F2F5F8; --ink:#14213A; --slate:#5A6A80; --rule:#D9DFE6;
        --mark:#FFE04A; --mark-ink:#14213A;
        --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
@media (prefers-color-scheme: dark) {
  :root { --paper:#101A2C; --wash:#16233A; --ink:#E6EBF2; --slate:#9AA8BA; --rule:#2A3850; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 16px/1.5 var(--sans); }
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }
header { display: flex; align-items: center; gap: 10px; }
.glyph { width: 22px; height: 22px; border-radius: 5px; background: var(--ink); position: relative; }
.glyph::after { content: ""; position: absolute; left: 4px; right: 4px; top: 8px; height: 6px;
                border-radius: 1px; background: var(--mark); }
header strong { font-size: 20px; }
h1 { font-size: 30px; line-height: 1.2; margin: 18px 0 6px; }
.meta { color: var(--slate); margin: 0 0 24px; }
.tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
.tile { border: 1.5px solid var(--rule); border-radius: 10px; padding: 14px 16px; }
.tile .n { font-size: 30px; font-weight: 700; font-family: var(--mono); }
.tile .l { color: var(--slate); font-size: 14px; }
.tile.high { background: var(--mark); color: var(--mark-ink); border-color: var(--mark); }
.tile.high .l { color: var(--mark-ink); }
.note { background: var(--wash); border-radius: 8px; padding: 12px 16px; color: var(--slate);
        font-size: 14px; margin-bottom: 32px; }
h2 { font-size: 22px; margin: 0 0 12px; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 15px; min-width: 760px; }
th { text-align: left; font-weight: 600; color: var(--slate); font-size: 13px; text-transform: uppercase;
     letter-spacing: .03em; padding: 8px 10px; border-bottom: 1.5px solid var(--rule); white-space: nowrap; }
td { padding: 12px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }
.file { font-family: var(--mono); font-size: 14px; word-break: break-all; }
.found { color: var(--slate); font-size: 14px; margin-top: 2px; }
.badge { display: inline-block; font-weight: 700; font-size: 13px; padding: 2px 8px; border-radius: 4px;
         border: 1.5px solid var(--ink); white-space: nowrap; }
.badge.high { background: var(--mark); color: var(--mark-ink); border-color: var(--mark); }
.badge.unknown { border-style: dashed; }
a { color: inherit; text-underline-offset: 3px; }
.open { white-space: nowrap; }
.empty { color: var(--slate); }
details { margin-top: 32px; }
summary { cursor: pointer; font-weight: 700; font-size: 18px; }
footer { margin-top: 40px; color: var(--slate); font-size: 14px; border-top: 1px solid var(--rule); padding-top: 16px; }
@media (max-width: 720px) { .tiles { grid-template-columns: repeat(2, 1fr); } h1 { font-size: 24px; } }
"""


def _html(rows, meta) -> str:
    counts = count_by_risk(rows)
    started = meta.get("started") or datetime.now()
    source = meta.get("source", "Google Drive")
    model = meta.get("model")
    seconds = meta.get("seconds")

    meta_parts = [f"{len(rows)} files", started.strftime("%d %b %Y, %H:%M")]
    if seconds is not None:
        meta_parts.append(f"took {seconds:.0f} s" if seconds >= 1 else "took under 1 s")
    meta_parts.append("local model on" if model else "rules only")
    meta_parts.append(f"Sirgal {__version__}")

    tile_names = {HIGH: "High risk", MEDIUM: "Medium risk", LOW: "Low risk", UNKNOWN: "Not checked", OK: "OK"}
    tiles = "".join(
        f'<div class="tile {level}"><div class="n">{counts[level]}</div><div class="l">{tile_names[level]}</div></div>'
        for level in LEVELS
    )

    attention = [r for r in rows if r["risk"] != OK]
    fine = [r for r in rows if r["risk"] == OK]

    def link_cell(r):
        url = safe_link(r.get("link"))
        if not url:
            return ""
        return f' · <a class="open" href="{_e(url)}" target="_blank" rel="noopener noreferrer">Open in Drive</a>'

    attention_rows = "".join(
        f"<tr>"
        f'<td><span class="badge {_e(r["risk"])}">{_e(r["risk"].upper())}</span></td>'
        f'<td><div class="file">{_e(r["path"])}</div><div class="found">{_e(found_text(r) or "-")}</div></td>'
        f"<td>{_e(r['sharing'])}</td>"
        f"<td>{_e(what_to_do(r))}{link_cell(r)}</td>"
        f"</tr>"
        for r in attention
    )
    if attention:
        attention_html = (
            '<div class="scroll"><table><thead><tr><th>Risk</th><th>File and what was found</th>'
            f"<th>Who can open it</th><th>What to do</th></tr></thead><tbody>{attention_rows}</tbody></table></div>"
        )
    else:
        attention_html = '<p class="empty">Nothing needs attention. No shared file holds sensitive data.</p>'

    fine_rows = "".join(
        f'<tr><td><div class="file">{_e(r["path"])}</div></td><td>{_e(r["sharing"])}</td>'
        f'<td class="found">{_e(found_text(r) or "-")}</td></tr>'
        for r in fine
    )
    fine_html = (
        f"<details><summary>OK files ({len(fine)})</summary>"
        '<p class="empty">Private, or shared with nothing sensitive inside.</p>'
        '<div class="scroll"><table><thead><tr><th>File</th><th>Who can open it</th><th>Found</th></tr></thead>'
        f"<tbody>{fine_rows}</tbody></table></div></details>"
        if fine else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Sirgal scan report</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
<header><span class="glyph" aria-hidden="true"></span><strong>Sirgal</strong></header>
<h1>Scan report: {_e(source)}</h1>
<p class="meta">{" · ".join(_e(p) for p in meta_parts)}</p>
<div class="tiles">{tiles}</div>
<p class="note">This report lists file names, links and sharing settings only. File contents were read in
memory during the scan and not saved. File names can still be sensitive, so keep this report private.</p>
<h2>Needs attention ({len(attention)})</h2>
{attention_html}
{fine_html}
<footer>Generated by Sirgal {_e(__version__)}, an open-source scanner for overshared files.
github.com/bilalkumrani/sirgal</footer>
</div>
</body>
</html>
"""
