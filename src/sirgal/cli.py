"""Command-line interface for Sirgal."""

import argparse

from sirgal import __version__

# (one, many). Types without a count are described in words only.
LABELS = {
    "ssn": ("SSN", "SSNs"),
    "credit_card": ("card number", "card numbers"),
    "iban": ("bank IBAN", "bank IBANs"),
    "password": ("password", "passwords"),
    "phone": ("phone number", "phone numbers"),
    "email": ("email", "emails"),
}
NO_COUNT = {"salary": "salary data", "date_of_birth": "dates of birth"}


def describe_found(found: dict) -> str:
    """{'ssn': 25, 'email': 1} -> '25 SSNs, 1 email'"""
    from sirgal.detectors import SEVERITY

    order = {"high": 0, "medium": 1, "low": 2}
    parts = []
    for kind in sorted(found, key=lambda k: (order[SEVERITY[k]], k)):
        if kind in NO_COUNT:
            parts.append(NO_COUNT[kind])
        else:
            one, many = LABELS[kind]
            parts.append(f"{found[kind]} {one if found[kind] == 1 else many}")
    return ", ".join(parts)


def run_scan(source: str) -> None:
    # Imported here so `sirgal --version` stays fast.
    from sirgal.connectors import gdrive
    from sirgal.risk import OK, RISK_ORDER, UNKNOWN

    print("Scanning Google Drive (read-only). Your browser may open to log in.\n")
    results = gdrive.scan()

    if not results:
        print("No files found.")
        return

    results.sort(key=lambda r: (RISK_ORDER[r["risk"]], r["exposure"], r["path"]))
    path_w = max(len(r["path"]) for r in results)
    share_w = max(len(r["sharing"]) for r in results)

    print(f"{'RISK':<7} {'SHARED WITH'.ljust(share_w)}   {'FILE'.ljust(path_w)}   FOUND")
    for r in results:
        if not r["checked"]:
            found = "(not checked: file type not supported yet)"
        else:
            found = describe_found(r["found"]) or "-"
        print(f"{r['risk'].upper():<7} {r['sharing'].ljust(share_w)}   {r['path'].ljust(path_w)}   {found}")

    counts = {}
    for r in results:
        counts[r["risk"]] = counts.get(r["risk"], 0) + 1
    summary = [f"{counts[k]} {k} risk" for k in ("high", "medium", "low") if counts.get(k)]
    if counts.get(UNKNOWN):
        summary.append(f"{counts[UNKNOWN]} shared but not checked")
    summary.append(f"{counts.get(OK, 0)} ok")
    print(f"\n{len(results)} files scanned: " + ", ".join(summary) + ".")
    print("File contents were read in memory and not saved.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sirgal",
        description=(
            "Sirgal finds sensitive files that AI assistants like "
            "Copilot and Gemini can see because they are overshared."
        ),
        epilog="Project home: https://github.com/bilalkumrani/sirgal",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"sirgal {__version__}",
    )

    commands = parser.add_subparsers(dest="command")
    scan = commands.add_parser("scan", help="scan a source for overshared files")
    scan.add_argument(
        "--source",
        choices=["gdrive"],
        required=True,
        help="where to scan (only gdrive for now)",
    )

    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args.source)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
