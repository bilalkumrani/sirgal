"""Tests for the HTML, CSV and JSON reports."""

import csv
import io
import json
import os
import stat
import subprocess
import sys
from datetime import datetime

from sirgal.report import describe_found, what_to_do, write_report
from sirgal.risk import ANYONE, DOMAIN, PEOPLE, PRIVATE


def result(path, risk, exposure, sharing, found=None, checked=True, note="", link="https://drive.google.com/file/d/abc/view"):
    return {"path": path, "risk": risk, "exposure": exposure, "sharing": sharing,
            "found": found or {}, "checked": checked, "note": note, "link": link}


RESULTS = [
    result("acme/HR/salaries.csv", "high", ANYONE, "anyone with the link", {"iban": 25, "salary": 1}),
    result("acme/HR/exit.txt", "medium", PEOPLE, "1 person", {"home_address": 1}),
    result("acme/HR/passport.pdf", "unknown", PEOPLE, "1 person", checked=False,
           note="no readable text, maybe a scan or a protected file"),
    result("acme/General/lunch.txt", "ok", PEOPLE, "1 person"),
    result("acme/Sales/customers.csv", "ok", PRIVATE, "private", {"credit_card": 40}),
]


def test_describe_found_reads_naturally():
    assert describe_found({"ssn": 25, "email": 1}) == "25 SSNs, 1 email"
    assert describe_found({"salary": 1, "iban": 2}) == "2 bank IBANs, salary data"


def test_what_to_do_depends_on_who_can_open_it():
    assert "Restricted" in what_to_do(result("a", "high", ANYONE, "anyone with the link"))
    assert "whole organization" in what_to_do(result("a", "high", DOMAIN, "everyone at acme.example"))
    assert "everyone who has access" in what_to_do(result("a", "medium", PEOPLE, "1 person"))
    assert "by hand" in what_to_do(result("a", "unknown", PEOPLE, "1 person", checked=False))
    assert what_to_do(result("a", "ok", PRIVATE, "private")) == ""


def test_html_report_summarises_and_lists_risky_files_first(tmp_path):
    page = (tmp_path / "r.html")
    write_report(RESULTS, page)
    text = page.read_text()
    assert "Needs attention (3)" in text
    assert "OK files (2)" in text
    assert text.index("salaries.csv") < text.index("exit.txt") < text.index("passport.pdf")
    assert "25 bank IBANs, salary data" in text
    assert "Open in Drive" in text
    assert "<script" not in text  # works offline with no scripts at all


def test_report_is_readable_only_by_the_user(tmp_path):
    page = tmp_path / "r.html"
    page.write_text("old")
    os.chmod(page, 0o644)
    write_report(RESULTS, page)
    assert stat.S_IMODE(os.stat(page).st_mode) == 0o600


def test_booby_trapped_file_names_stay_plain_text_in_html(tmp_path):
    evil = result('<script>alert("x")</script>.txt', "high", ANYONE, "anyone with the link", {"password": 1},
                  link="javascript:alert(1)")
    page = tmp_path / "r.html"
    write_report([evil], page)
    text = page.read_text()
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in text
    assert "javascript:" not in text  # only https links are kept


def test_booby_trapped_file_names_cannot_become_spreadsheet_formulas(tmp_path):
    evil = result('=HYPERLINK("http://evil.example","click").csv', "high", ANYONE, "anyone with the link", {"ssn": 1})
    sheet = tmp_path / "r.csv"
    write_report([evil] + RESULTS, sheet)
    rows = list(csv.DictReader(io.StringIO(sheet.read_text())))
    assert rows[0]["file"].startswith("'=")
    assert all(not row[col].startswith(("=", "+", "-", "@")) for row in rows for col in row)


def test_csv_report_has_one_row_per_file(tmp_path):
    sheet = tmp_path / "r.csv"
    write_report(RESULTS, sheet)
    rows = list(csv.DictReader(io.StringIO(sheet.read_text())))
    assert len(rows) == len(RESULTS)
    assert rows[0]["risk"] == "high" and rows[0]["file"] == "acme/HR/salaries.csv"
    assert rows[2]["found"].startswith("Not checked")


def test_empty_attention_list_says_so(tmp_path):
    page = tmp_path / "r.html"
    write_report([RESULTS[3]], page)
    assert "Nothing needs attention" in page.read_text()


def test_json_report_has_meta_and_one_entry_per_file(tmp_path):
    out = tmp_path / "r.json"
    started = datetime(2026, 10, 16, 9, 30, 0)
    write_report(RESULTS, out, {"source": "Google Drive", "model": "gliner", "started": started, "seconds": 12.5})
    with open(out, encoding="utf-8") as f:
        report = json.load(f)
    assert set(report) == {"meta", "files"}
    meta = report["meta"]
    assert meta["source"] == "Google Drive"
    assert meta["started"] == "2026-10-16T09:30:00"
    assert meta["seconds"] == 12.5
    assert meta["model"] is True
    assert meta["sirgal_version"]
    files = report["files"]
    assert len(files) == len(RESULTS)
    assert all(set(f) == {"risk", "path", "sharing", "exposure", "checked", "note", "found", "link"} for f in files)
    assert files[0]["path"] == "acme/HR/salaries.csv" and files[0]["risk"] == "high"
    assert files[2]["checked"] is False and "no readable text" in files[2]["note"]


def test_json_report_writes_exposure_as_a_word(tmp_path):
    out = tmp_path / "r.json"
    domain = result("acme/all-hands.txt", "low", DOMAIN, "everyone at acme.example", {"email": 2})
    write_report(RESULTS + [domain], out)
    by_path = {f["path"]: f["exposure"] for f in json.loads(out.read_text())["files"]}
    assert by_path["acme/HR/salaries.csv"] == "anyone"
    assert by_path["acme/all-hands.txt"] == "domain"
    assert by_path["acme/HR/exit.txt"] == "people"
    assert by_path["acme/Sales/customers.csv"] == "private"


def test_json_report_keeps_counts_never_values(tmp_path):
    out = tmp_path / "r.json"
    leaky = result("a.txt", "high", ANYONE, "anyone with the link", {"ssn": 25, "password": "hunter2", "email": True})
    write_report([leaky], out)
    text = out.read_text()
    assert json.loads(text)["files"][0]["found"] == {"ssn": 25}
    assert "hunter2" not in text


def test_json_report_without_meta_or_model(tmp_path):
    out = tmp_path / "r.json"
    write_report(RESULTS, out)
    meta = json.loads(out.read_text())["meta"]
    assert meta["model"] is False and meta["seconds"] is None
    datetime.fromisoformat(meta["started"])


def test_json_report_is_readable_only_by_the_user(tmp_path):
    out = tmp_path / "r.json"
    out.write_text("old")
    os.chmod(out, 0o644)
    write_report(RESULTS, out)
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600


def test_json_report_keeps_only_https_links(tmp_path):
    out = tmp_path / "r.json"
    rows = [
        result("a.txt", "high", ANYONE, "anyone with the link", {"ssn": 1}, link="javascript:alert(1)"),
        result("b.txt", "high", ANYONE, "anyone with the link", {"ssn": 1}, link="http://drive.google.com/x"),
        result("c.txt", "high", ANYONE, "anyone with the link", {"ssn": 1}, link=None),
        result("d.txt", "high", ANYONE, "anyone with the link", {"ssn": 1}),
    ]
    write_report(rows, out)
    links = {f["path"]: f["link"] for f in json.loads(out.read_text())["files"]}
    assert links == {"a.txt": "", "b.txt": "", "c.txt": "", "d.txt": "https://drive.google.com/file/d/abc/view"}


def test_report_option_only_accepts_html_csv_or_json():
    run = subprocess.run([sys.executable, "-m", "sirgal.cli", "scan", "--source", "gdrive", "--report", "out.pdf"],
                         capture_output=True, text=True)
    assert run.returncode != 0
    assert "must end in .html, .csv or .json" in run.stderr
