"""Pull plain text out of PDF, Word and Excel files, entirely in memory.

Files arrive as bytes and never touch the disk. When a file has no text to
read (a scanned image, a password-protected PDF, a damaged file), this returns
None, so the scan reports it as UNKNOWN instead of calling it safe.
"""

import io
import warnings

PDF = "pdf"
DOCX = "docx"
XLSX = "xlsx"

MIME_TYPES = {
    "application/pdf": PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XLSX,
}
SUFFIXES = {".pdf": PDF, ".docx": DOCX, ".xlsx": XLSX}

MAX_CHARS = 2_000_000  # stop collecting text past this, to keep memory bounded


def kind_for(mime=None, name=None):
    """The document kind for a MIME type or file name, or None if not supported."""
    if mime in MIME_TYPES:
        return MIME_TYPES[mime]
    if name:
        for suffix, kind in SUFFIXES.items():
            if name.lower().endswith(suffix):
                return kind
    return None


def extract_text(data: bytes, kind: str):
    """Return the text in a PDF, Word or Excel file, or None if there is none to read."""
    readers = {PDF: _pdf_text, DOCX: _docx_text, XLSX: _xlsx_text}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # damaged files trigger library warnings
            text = readers[kind](io.BytesIO(data))
    except Exception:  # a damaged or unusual file must never stop the scan
        return None
    text = text[:MAX_CHARS]
    return text if text.strip() else None


def _pdf_text(stream):
    from pypdf import PdfReader

    reader = PdfReader(stream)
    if reader.is_encrypted and not reader.decrypt(""):
        return ""  # password-protected: nothing we can read
    parts, size = [], 0
    for page in reader.pages:
        part = page.extract_text() or ""
        parts.append(part)
        size += len(part)
        if size > MAX_CHARS:
            break
    return "\n".join(parts)


def _docx_text(stream):
    from docx import Document

    doc = Document(stream)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:  # offer letters and forms often keep details in tables
        for row in table.rows:
            parts.append(",".join(cell.text for cell in row.cells))
    for section in doc.sections:
        for block in (section.header, section.footer):
            parts.extend(p.text for p in block.paragraphs)
    return "\n".join(parts)


def _xlsx_text(stream):
    from openpyxl import load_workbook

    workbook = load_workbook(stream, read_only=True, data_only=True)
    parts, size = [], 0
    try:
        for sheet in workbook.worksheets:  # every sheet, not just the first
            for row in sheet.iter_rows(values_only=True):
                line = ",".join("" if v is None else str(v) for v in row)
                parts.append(line)
                size += len(line)
                if size > MAX_CHARS:
                    return "\n".join(parts)
    finally:
        workbook.close()
    return "\n".join(parts)
