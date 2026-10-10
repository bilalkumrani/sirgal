"""Tests for reading PDF, Word and Excel files in memory."""

import io

from docx import Document
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from sirgal.extract import DOCX, PDF, XLSX, extract_text, kind_for


def make_pdf(lines=(), shapes_only=False, password=None):
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, invariant=1)
    if password:
        from reportlab.lib import pdfencrypt

        page = canvas.Canvas(buffer, invariant=1, encrypt=pdfencrypt.StandardEncryption(password, canPrint=0))
    if shapes_only:
        page.rect(80, 600, 120, 160, fill=1)
    for i, line in enumerate(lines):
        page.drawString(60, 800 - i * 18, line)
    page.showPage()
    page.save()
    return buffer.getvalue()


def make_docx(paragraphs=(), table=None):
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def make_xlsx(sheets):
    workbook = Workbook()
    for i, (name, rows) in enumerate(sheets.items()):
        sheet = workbook.active if i == 0 else workbook.create_sheet()
        sheet.title = name
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_kind_from_mime_or_name():
    assert kind_for(mime="application/pdf") == PDF
    assert kind_for(name="Offer Letter.DOCX") == DOCX
    assert kind_for(name="payroll.xlsx") == XLSX
    assert kind_for(mime="image/png", name="photo.png") is None


def test_pdf_text_is_read():
    text = extract_text(make_pdf(["SSN 251-29-2287"]), PDF)
    assert "251-29-2287" in text


def test_scanned_pdf_has_no_text():
    assert extract_text(make_pdf(shapes_only=True), PDF) is None


def test_password_protected_pdf_is_not_readable():
    assert extract_text(make_pdf(["secret"], password="hunter2"), PDF) is None


def test_damaged_files_never_crash_the_scan():
    for kind in (PDF, DOCX, XLSX):
        assert extract_text(b"this is not a real file", kind) is None


def test_word_paragraphs_and_tables_are_read():
    data = make_docx(["Dear Ali,"], table=[["Salary", "95,000"], ["IBAN", "GB82WEST12345698765432"]])
    text = extract_text(data, DOCX)
    assert "Dear Ali," in text
    assert "95,000" in text and "GB82WEST12345698765432" in text


def test_every_excel_sheet_is_read_not_just_the_first():
    data = make_xlsx({"Summary": [["Team", "Headcount"], ["Sales", 4]],
                      "Detail": [["Name", "IBAN"], ["Ali", "GB82WEST12345698765432"]]})
    text = extract_text(data, XLSX)
    assert "Sales" in text
    assert "GB82WEST12345698765432" in text


def test_empty_workbook_counts_as_no_text():
    assert extract_text(make_xlsx({"Sheet1": []}), XLSX) is None
