"""Tests for the HTML and CSV reports."""

import csv
import io
import os
import stat
import subprocess
import sys

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


def test_report_option_only_accepts_html_or_csv():
    run = subprocess.run([sys.executable, "-m", "sirgal.cli", "scan", "--source", "gdrive", "--report", "out.pdf"],
                         capture_output=True, text=True)
    assert run.returncode != 0
    assert "must end in .html or .csv" in run.stderr
