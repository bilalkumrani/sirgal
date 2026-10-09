"""Find sensitive data in text using rules only.

This is layer 1 of detection: regular expressions plus checksums where the
data type has one (card numbers, IBANs). It never sends text anywhere and
never returns the matched values, only how many of each type were found.
"""

import re

HIGH, MEDIUM, LOW = "high", "medium", "low"

# Which data types count as how serious.
SEVERITY = {
    "ssn": HIGH,
    "credit_card": HIGH,
    "iban": HIGH,
    "password": HIGH,
    "salary": HIGH,
    "date_of_birth": MEDIUM,
    "phone": MEDIUM,
    "email": LOW,
    # Found by the optional model layer (sirgal.ner), tied to a person.
    "health_info": HIGH,
    "home_address": MEDIUM,
}

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# US Social Security number. Skips numbers that are never issued (000, 666, 9xx).
SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)")

# (?<![a-z]) instead of \b, so column names like annual_salary_usd still match.
SALARY_WORDS = re.compile(r"(?<![a-z])(salary|salaries|compensation|payroll)(?![a-z])", re.I)
DOB_WORDS = re.compile(r"(?<![a-z])(date[_ ]of[_ ]birth|dob|birth[_ ]?date)(?![a-z])", re.I)
CREDENTIAL_WORDS = re.compile(r"\b(passwords?|passwd|pwd|logins?|credentials?|secrets?)\b", re.I)
# "Stripe: vlopez / 9xK!..." or "password = hunter2"
CREDENTIAL_LINE = re.compile(
    r"^\s*[^:=\n]{1,40}[:=]\s*\S+\s*/\s*\S+\s*$"
    r"|\b(password|passwd|pwd)\s*[:=]\s*\S+",
    re.I | re.M,
)


def luhn_ok(number: str) -> bool:
    """Card number checksum. Filters out random long numbers."""
    digits = [int(d) for d in number if d.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(iban: str) -> bool:
    """IBAN checksum (mod 97)."""
    rearranged = iban[4:] + iban[:4]
    as_digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(as_digits) % 97 == 1


def scan_text(text: str, filename: str = "") -> dict:
    """Return {data_type: count} for everything sensitive found in the text."""
    found = {}

    def add(kind, count):
        if count:
            found[kind] = found.get(kind, 0) + count

    add("email", len(EMAIL.findall(text)))
    add("ssn", len(SSN.findall(text)))

    cards = [m for m in CARD.findall(text) if 13 <= sum(c.isdigit() for c in m) <= 19 and luhn_ok(m)]
    add("credit_card", len(cards))
    add("iban", sum(1 for m in IBAN.findall(text) if iban_ok(m)))

    # Remove SSNs and card numbers first so their digits aren't counted as phones.
    rest = SSN.sub(" ", CARD.sub(" ", text))
    add("phone", len(PHONE.findall(rest)))

    # Keyword-based types: the word alone isn't enough, the file must look like data.
    if SALARY_WORDS.search(text) and re.search(r"\b\d{2,3},?\d{3}\b", text):
        add("salary", 1)
    if DOB_WORDS.search(text) and re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", text):
        add("date_of_birth", 1)
    if CREDENTIAL_WORDS.search(text + " " + filename):
        add("password", len(CREDENTIAL_LINE.findall(text)))

    return found


def worst_severity(found: dict):
    """The most serious severity among the types found, or None."""
    for level in (HIGH, MEDIUM, LOW):
        if any(SEVERITY[kind] == level for kind in found):
            return level
    return None