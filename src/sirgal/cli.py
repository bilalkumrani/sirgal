"""Command-line interface for Sirgal."""

import argparse
import time
from datetime import datetime

from sirgal import __version__
from sirgal.ner import DEFAULT_MODEL
from sirgal.progress import Progress
from sirgal.report import describe_found, not_checked_reason, sort_results, write_report

REPORT_TYPES = (".html", ".htm", ".csv")

def run_scan(source: str, model_name=None, report_path=None) -> None:
    # Imported here so `sirgal --version` stays fast.
    from sirgal.connectors import gdrive
    from sirgal.risk import OK, UNKNOWN

    model = None
    if model_name:
        from sirgal.ner import ModelDetector, ModelNotInstalled

        print(f"Loading the local model ({model_name})...")
        try:
            model = ModelDetector(model_name)
        except ModelNotInstalled as exc:
            raise SystemExit(str(exc)) from None

    print("Scanning Google Drive (read-only). Your browser may open to log in.\n", flush=True)
    progress = Progress()
    started, clock = datetime.now(), time.monotonic()
    try:
        results = gdrive.scan(model=model, progress=progress)
    finally:
        progress.clear()
    seconds = time.monotonic() - clock

    if not results:
        print("No files found.")
        return

    results = sort_results(results)
    path_w = max(len(r["path"]) for r in results)
    share_w = max(len(r["sharing"]) for r in results)

    print(f"{'RISK':<7} {'SHARED WITH'.ljust(share_w)}   {'FILE'.ljust(path_w)}   FOUND")
    for r in results:
        if not r["checked"]:
            found = f"(not checked: {not_checked_reason(r)})"
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
    if report_path:
        progress.status("Writing report...")
        write_report(results, report_path, {
            "source": "Google Drive", "model": model_name, "started": started, "seconds": seconds,
        })
        progress.clear()
        print(f"Report saved to {report_path} (readable only by you).")
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

    scan.add_argument(
        "--report",
        metavar="FILE",
        help="also save the results as a report: an .html page to share, or a .csv for spreadsheets",
    )

    args = parser.parse_args()
    if args.command == "scan":
        if args.report and not args.report.lower().endswith(REPORT_TYPES):
            scan.error("--report must end in .html or .csv")
        run_scan(args.source, args.model, args.report)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
