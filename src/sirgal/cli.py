"""Command-line interface for Sirgal."""

import argparse

from sirgal import __version__


def run_scan(source: str) -> None:
    # Imported here so `sirgal --version` stays fast and works without Google libraries loaded.
    from sirgal.connectors import gdrive

    print("Scanning Google Drive (read-only). Your browser may open to log in.\n")
    results = gdrive.scan()

    if not results:
        print("No files found.")
        return

    width = max(len(r["sharing"]) for r in results)
    print(f"{'SHARED WITH'.ljust(width)}   FILE")
    for r in results:
        print(f"{r['sharing'].ljust(width)}   {r['path']}")

    shared = sum(1 for r in results if r["level"] != gdrive.PRIVATE)
    print(f"\n{len(results)} files scanned, {shared} shared beyond the owner.")
    print("Content checks are not built yet, so this only shows sharing.")


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
