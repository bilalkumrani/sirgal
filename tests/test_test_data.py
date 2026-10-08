"""End-to-end check: the detector must agree with the test data's answer key.

Generates the Acme Robotics files with a few different seeds and checks every
file is flagged (or not) exactly as manifest.json says.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sirgal.detectors import scan_text, worst_severity

SCRIPT = Path(__file__).parent.parent / "scripts" / "make_test_data.py"

pytest.importorskip("faker")  # the generator needs Faker (pip install -e ".[dev]")


@pytest.mark.parametrize("seed", [1, 42, 1234])
def test_detector_matches_manifest(tmp_path, seed):
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path), "--seed", str(seed)],
        check=True,
        capture_output=True,
    )
    root = tmp_path / "acme-robotics"
    manifest = json.loads((root / "manifest.json").read_text())

    for entry in manifest["files"]:
        path = root / entry["path"]
        found = scan_text(path.read_text(), path.name)
        flagged = worst_severity(found) in ("high", "medium")
        assert flagged == entry["sensitive"], f"{entry['path']}: found {found}"
