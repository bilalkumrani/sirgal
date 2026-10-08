"""Combine who can see a file with what's inside it into one risk level.

Shared by every connector, so Google Drive and Microsoft 365 are rated the same way.
"""

from sirgal.detectors import HIGH, LOW, MEDIUM

# How exposed a file is. Lower number = more people can see it.
ANYONE, DOMAIN, PEOPLE, PRIVATE = 0, 1, 2, 3

OK = "ok"
UNKNOWN = "unknown"  # shared, but we couldn't read the contents, so we can't say it's fine
RISK_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2, UNKNOWN: 3, OK: 4}


def rate(exposure: int, severity, checked: bool = True) -> str:
    """Risk of one file, from its exposure and the worst data type found in it."""
    if exposure == PRIVATE:
        return OK
    if not checked:
        return UNKNOWN
    if severity is None:
        return OK
    public = exposure == ANYONE
    if severity == HIGH:
        return HIGH
    if severity == MEDIUM:
        return HIGH if public else MEDIUM
    return MEDIUM if public else LOW
