"""Compare local models for layer 2 of Sirgal's detection.

Runs three setups on the Acme Robotics test files and scores each one
against manifest.json:

    rules              Sirgal's current rules only (the baseline)
    rules + presidio   Microsoft Presidio with a spaCy model
    rules + gliner     GLiNER-PII, a small zero-shot model

A file counts as "flagged" when the rules find something high or medium,
or the model finds personal details tied to a person: a person plus a home
address, or a person plus a health detail. A single signal is not enough.
Names alone, an office address, or a policy that mentions medical leave
never flag a file.

This is a developer tool. It is not part of the installed package.

Setup (run once, inside the project's .venv):
    pip install presidio-analyzer gliner
    python3 -m spacy download en_core_web_md
    python3 -c "from huggingface_hub import snapshot_download; snapshot_download(
        'knowledgator/gliner-pii-edge-v1.0', local_dir='models/gliner-pii-edge',
        allow_patterns=['*.json', '*.bin', '*.model'])"

Usage:
    python3 scripts/make_test_data.py
    python3 scripts/compare_detectors.py
"""

import argparse
import json
import sys
import time
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sirgal import ner  # noqa: E402
from sirgal.detectors import scan_text, worst_severity  # noqa: E402

# GLiNER uses Sirgal's own labels and rule (sirgal.ner), so this comparison
# always measures exactly what Sirgal ships.

PRESIDIO_ENTITIES = ["PERSON", "LOCATION", "NRP"]
# Presidio has no street-address or health recognizer. LOCATION is the only
# way it can notice an address, so it is used as the stand-in.
PRESIDIO_PERSON = {"PERSON"}
PRESIDIO_ADDRESS = {"LOCATION"}


def presidio_tied_to_person(found):
    """Presidio version of Sirgal's rule: a person plus a place."""
    kinds = set(found)
    return bool(kinds & PRESIDIO_PERSON) and bool(kinds & PRESIDIO_ADDRESS)


class Presidio:
    name = "rules + presidio"
    packages = ["presidio-analyzer", "spacy", "thinc", "en-core-web-md"]

    def __init__(self, spacy_model):
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": spacy_model}],
        })
        self.engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self.packages = self.packages[:3] + [spacy_model.replace("_", "-")]

    def find(self, text):
        found = {}
        for part in ner.chunks(text):
            for r in self.engine.analyze(text=part, language="en", entities=PRESIDIO_ENTITIES):
                found[r.entity_type] = found.get(r.entity_type, 0) + 1
        return found

    def sensitive(self, found):
        return presidio_tied_to_person(found)


class Gliner:
    name = "rules + gliner"
    packages = ["gliner", "torch", "transformers", "onnxruntime"]

    def __init__(self, model_id, threshold):
        from gliner import GLiNER

        self.model = GLiNER.from_pretrained(model_id)
        self.threshold = threshold
        self.model_id = model_id

    def find(self, text):
        found = {}
        for part in ner.chunks(text):
            for e in self.model.predict_entities(part, ner.LABELS, threshold=self.threshold):
                found[e["label"]] = found.get(e["label"], 0) + 1
        return found

    def sensitive(self, found):
        return bool(ner.tied_to_person(found))


def installed_mb(packages):
    """Rough size on disk of the given pip packages."""
    total = 0
    for name in packages:
        try:
            for f in metadata.distribution(name).files or []:
                path = f.locate()
                if path.is_file():
                    total += path.stat().st_size
        except metadata.PackageNotFoundError:
            pass
    return total / 1e6


def model_mb(model_id):
    """Size of a GLiNER model: a local folder, or the Hugging Face cache."""
    folder = Path(model_id)
    if not folder.exists():
        folder = Path.home() / ".cache" / "huggingface" / "hub" / ("models--" + model_id.replace("/", "--"))
    if not folder.exists():
        return 0.0
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file() and not p.is_symlink()) / 1e6


def evaluate(files, root, model=None):
    """Score one setup. Returns per-file rows and a summary."""
    rows, times = [], []
    for entry in files:
        text = (root / entry["path"]).read_text(encoding="utf-8")
        rules_found = scan_text(text, Path(entry["path"]).name)
        flagged = worst_severity(rules_found) in ("high", "medium")
        model_found = {}
        if model is not None:
            start = time.perf_counter()
            model_found = model.find(text)
            times.append(time.perf_counter() - start)
            flagged = flagged or model.sensitive(model_found)
        rows.append({"entry": entry, "flagged": flagged, "rules": rules_found, "model": model_found})

    sensitive = [r for r in rows if r["entry"]["sensitive"]]
    harmless = [r for r in rows if not r["entry"]["sensitive"]]
    summary = {
        "caught": sum(r["flagged"] for r in sensitive),
        "sensitive": len(sensitive),
        "false_alarms": sum(r["flagged"] for r in harmless),
        "harmless": len(harmless),
        "ms_per_file": (sum(times) / len(times) * 1000) if times else 0.0,
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description="Compare local models for Sirgal's layer 2.")
    parser.add_argument("--data", default="test-data/acme-robotics", help="folder made by make_test_data.py")
    parser.add_argument("--spacy-model", default="en_core_web_lg", help="spaCy model for Presidio")
    parser.add_argument("--gliner-model", default="models/gliner-pii-base-v1.0",
                        help="local folder or Hugging Face model id")
    parser.add_argument("--threshold", type=float, default=ner.THRESHOLD, help="GLiNER confidence threshold")
    args = parser.parse_args()

    root = Path(args.data)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No {manifest_path}. Run: python3 scripts/make_test_data.py")
    files = json.loads(manifest_path.read_text())["files"]

    setups = [("rules", None, 0.0, 0.0)]
    for label, make in [
        ("rules + presidio", lambda: Presidio(args.spacy_model)),
        ("rules + gliner", lambda: Gliner(args.gliner_model, args.threshold)),
    ]:
        try:
            start = time.perf_counter()
            model = make()
            load_s = time.perf_counter() - start
        except Exception as exc:  # missing package or model: report and keep going
            print(f"Skipping {label}: {exc}\n")
            continue
        disk = installed_mb(model.packages)
        if isinstance(model, Gliner):
            disk += model_mb(args.gliner_model)
        setups.append((label, model, load_s, disk))

    results = []
    for label, model, load_s, disk in setups:
        rows, summary = evaluate(files, root, model)
        results.append((label, rows, summary, load_s, disk))

    # Per-file detail for the written documents, where the models matter.
    print("WRITTEN DOCUMENTS (what each model found)\n")
    for entry in files:
        if not entry["path"].endswith(".txt") or entry["layer"] == "rules":
            continue
        truth = "sensitive" if entry["sensitive"] else "harmless"
        print(f"{entry['path']}  ({truth})")
        for label, rows, *_ in results[1:]:
            row = next(r for r in rows if r["entry"] is entry)
            verdict = "FLAGGED" if row["flagged"] else "ok"
            print(f"    {label:<18} {verdict:<8} {row['model'] or '-'}")
        print()

    print("SUMMARY (all files, scored against manifest.json)\n")
    print(f"{'SETUP':<18}  {'SENSITIVE CAUGHT':<17} {'FALSE ALARMS':<13} {'MS/FILE':>8} {'LOAD S':>7} {'DISK MB':>8}")
    for label, rows, s, load_s, disk in results:
        caught = f"{s['caught']}/{s['sensitive']}"
        false = f"{s['false_alarms']}/{s['harmless']}"
        print(f"{label:<18}  {caught:<17} {false:<13} {s['ms_per_file']:>8.0f} {load_s:>7.1f} {disk:>8.0f}")
    print("\nDisk is approximate: the main packages plus the downloaded model.")


if __name__ == "__main__":
    main()
