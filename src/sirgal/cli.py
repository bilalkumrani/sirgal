"""Command-line interface for Sirgal."""

import argparse

from sirgal import __version__
from sirgal.ner import DEFAULT_MODEL

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


def run_scan(source: str, model_name=None) -> None:
    # Imported here so `sirgal --version` stays fast.
    from sirgal.connectors import gdrive
    from sirgal.risk import OK, RISK_ORDER, UNKNOWN

    model = None
    if model_name:
        from sirgal.ner import ModelDetector, ModelNotInstalled

        print(f"Loading the local model ({model_name})...")
        try:
            model = ModelDetector(model_name)
        except ModelNotInstalled as exc:
            raise SystemExit(str(exc))

    print("Scanning Google Drive (read-only). Your browser may open to log in.\n")
    results = gdrive.scan(model=model)

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
    if model is None:
        print("Tip: add --model to also check notes and documents for personal details.")


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
    scan.add_argument(
        "--model",
        nargs="?",
        const=DEFAULT_MODEL,
        metavar="MODEL",
        help=(
            "also check notes and documents for personal details with a local model. "
            "Optionally give a model folder or Hugging Face id. "
            'Needs: pip install "sirgal[ner]"'
        ),
    )

    args = parser.parse_args()
    if args.command == "scan":
        run_scan(args.source, args.model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
