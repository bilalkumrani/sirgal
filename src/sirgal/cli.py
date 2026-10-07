"""Command-line interface for Sirgal."""

import argparse

from sirgal import __version__


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
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
