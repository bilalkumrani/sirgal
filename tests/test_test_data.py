"""End-to-end check: the detector must agree with the test data's answer key.

Generates the Acme Robotics files with a few different seeds and checks every
file is flagged (or not) exactly as manifest.json says. Files marked
"layer": "model" need a local model, so the rules layer is not checked on them.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sirgal.detectors import scan_text, worst_severity
from sirgal.extract import extract_text, kind_for

SCRIPT = Path(__file__).parent.parent / "scripts" / "make_test_data.py"

pytest.importorskip("faker")  # the generator needs Faker (pip install -e ".[dev]")


def read_like_sirgal(path):
    """Text the way the scan sees it: documents go through the extractor."""
    kind = kind_for(name=path.name)
    if kind:
        return extract_text(path.read_bytes(), kind)
    return path.read_text(encoding="utf-8")


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
        text = read_like_sirgal(path)
        if entry["layer"] == "unreadable":
            assert text is None, f"{entry['path']}: expected no readable text"
            continue
        if entry["layer"] == "model":
            continue
        found = scan_text(text, path.name)
        flagged = worst_severity(found) in ("high", "medium")
        assert flagged == entry["sensitive"], f"{entry['path']}: found {found}"


def test_manifest_includes_cases_for_the_model_layer(tmp_path):
    """The written documents exist, and names alone are never marked sensitive."""
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    files = json.loads((tmp_path / "acme-robotics" / "manifest.json").read_text())["files"]
    assert any(f["layer"] == "model" and f["sensitive"] for f in files)
    names_only = [f for f in files if f["contains"] == ["person_name"]]
    assert names_only and not any(f["sensitive"] for f in names_only)
