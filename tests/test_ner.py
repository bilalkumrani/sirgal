"""Tests for the optional model layer. The real model is replaced by a fake,
so these run without installing GLiNER or downloading anything."""

import sys
import types
from unittest import mock

import pytest

from sirgal import ner
from sirgal.connectors import gdrive
from sirgal.risk import PRIVATE


def test_decoy_labels_stay_in_the_list():
    """Without them the model labels cities as addresses (seen in a real scan)."""
    assert {"location city", "medical process"} <= set(ner.LABELS)
    assert not ({"location city", "medical process"} & (ner.ADDRESS | ner.HEALTH))


def test_names_alone_are_not_sensitive():
    assert ner.tied_to_person({"name": 4}) == {}


def test_address_or_health_without_a_person_is_not_sensitive():
    assert ner.tied_to_person({"location street": 1}) == {}
    assert ner.tied_to_person({"condition": 2}) == {}


def test_details_tied_to_a_person_are_counted():
    assert ner.tied_to_person({"name": 1, "location address": 1}) == {"home_address": 1}
    assert ner.tied_to_person({"name": 4, "condition": 2, "injury": 1, "drug": 1}) == {"health_info": 4}


def test_long_text_is_split_into_chunks():
    text = "\n".join(["word " * 50] * 10)  # 500 words over 10 lines
    parts = list(ner.chunks(text, max_words=200))
    assert len(parts) == 3
    assert all(len(p.split()) <= 200 for p in parts)
    assert sum(len(p.split()) for p in parts) == 500


class FakeGLiNER:
    """Mimics GLiNER: tags a few known words in the text."""

    @classmethod
    def from_pretrained(cls, model):
        return cls()

    def predict_entities(self, text, labels, threshold):
        found = []
        if "Jason Cooper" in text:
            found.append({"label": "name", "text": "Jason Cooper"})
        if "Karen Trail" in text:
            found.append({"label": "location address", "text": "06738 Karen Trail"})
        if "surgery" in text:
            found.append({"label": "condition", "text": "knee surgery"})
        return found


@pytest.fixture
def fake_gliner(monkeypatch):
    monkeypatch.setitem(sys.modules, "gliner", types.SimpleNamespace(GLiNER=FakeGLiNER))


def test_detector_returns_counts_never_values(fake_gliner):
    detector = ner.ModelDetector("any-model")
    found = detector.scan_text("Jason Cooper lives at 06738 Karen Trail. Recovering from knee surgery.")
    assert found == {"home_address": 1, "health_info": 1}
    assert "Karen Trail" not in str(found)


def test_missing_packages_give_a_clear_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "gliner", None)  # makes "import gliner" fail
    with pytest.raises(ner.ModelNotInstalled, match="sirgal\\[ner\\]"):
        ner.ModelDetector()


def test_cli_explains_how_to_install_the_model(monkeypatch):
    from sirgal import cli

    monkeypatch.setitem(sys.modules, "gliner", None)
    with pytest.raises(SystemExit, match="sirgal\\[ner\\]"):
        cli.run_scan("gdrive", "any-model")


OWNER = {"type": "user", "role": "owner"}
FRIEND = {"type": "user", "role": "reader"}


def _scan_with(items, contents, model):
    service = mock.MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": items}
    with mock.patch.object(gdrive, "build", return_value=service), \
         mock.patch.object(gdrive, "get_credentials"), \
         mock.patch.object(gdrive, "_read_text", side_effect=lambda _s, item: contents.get(item["id"])):
        return {r["path"]: r for r in gdrive.scan(model=model)}


def test_model_only_reads_shared_files_that_rules_did_not_already_flag():
    items = [
        {"id": "1", "name": "exit.txt", "mimeType": "text/plain", "permissions": [OWNER, FRIEND]},
        {"id": "2", "name": "private.txt", "mimeType": "text/plain", "permissions": [OWNER]},
        {"id": "3", "name": "ssn.csv", "mimeType": "text/csv", "permissions": [OWNER, FRIEND]},
    ]
    contents = {
        "1": "Jason Cooper, home address 06738 Karen Trail",
        "2": "Jason Cooper, home address 06738 Karen Trail",
        "3": "name,ssn\nAli,251-29-2287",
    }
    model = mock.MagicMock()
    model.scan_text.return_value = {"home_address": 1}

    results = _scan_with(items, contents, model)

    model.scan_text.assert_called_once_with(contents["1"])  # not the private file, not the SSN file
    assert results["exit.txt"]["found"] == {"home_address": 1}
    assert results["exit.txt"]["risk"] == "medium"
    assert results["private.txt"]["risk"] == "ok"
    assert results["ssn.csv"]["risk"] == "high"


def test_health_details_on_a_shared_file_are_high_risk():
    items = [{"id": "1", "name": "leave.txt", "mimeType": "text/plain", "permissions": [OWNER, FRIEND]}]
    model = mock.MagicMock()
    model.scan_text.return_value = {"health_info": 3}
    results = _scan_with(items, {"1": "notes"}, model)
    assert results["leave.txt"]["risk"] == "high"
    assert gdrive.describe_sharing([OWNER])[0] == PRIVATE


def test_scan_without_model_is_unchanged():
    items = [{"id": "1", "name": "exit.txt", "mimeType": "text/plain", "permissions": [OWNER, FRIEND]}]
    results = _scan_with(items, {"1": "Jason Cooper, 06738 Karen Trail"}, None)
    assert results["exit.txt"]["risk"] == "ok"
