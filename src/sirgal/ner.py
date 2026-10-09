"""Layer 2 of detection: personal details in notes and documents.

Uses GLiNER-PII, a small model that runs on your machine. Nothing is sent
anywhere. Install it with:  pip install "sirgal[ner]"

A detail only counts when it is tied to a person in the same file:
a person plus a home address, or a person plus a health detail. An office
address, or a policy that mentions medical leave, is not sensitive on its own.
Like layer 1, this returns counts only, never the values themselves.
"""

import warnings

DEFAULT_MODEL = "knowledgator/gliner-pii-base-v1.0"
THRESHOLD = 0.3   # the model card's suggested starting point
MAX_WORDS = 200   # the model has a length limit, so long text is split

# The model picks the closest label from this list, so the list must include
# "decoy" labels too. Without "location city", a city name gets labelled as an
# address; without "medical process", "medical leave" gets labelled as a
# condition. Decoys are found but never counted.
LABELS = [
    "name",
    "location city",
    "location address",
    "location street",
    "condition",
    "injury",
    "medical process",
    "drug",
]
PERSON = {"name"}
ADDRESS = {"location address", "location street"}
HEALTH = {"condition", "injury", "drug"}


class ModelNotInstalled(RuntimeError):
    """Raised when the optional model packages are missing."""


def chunks(text, max_words=MAX_WORDS):
    """Split text on line breaks into pieces of at most ~max_words words."""
    piece, count = [], 0
    for line in text.splitlines():
        words = len(line.split())
        if piece and count + words > max_words:
            yield "\n".join(piece)
            piece, count = [], 0
        piece.append(line)
        count += words
    if piece:
        yield "\n".join(piece)


def tied_to_person(labels_found: dict) -> dict:
    """Turn raw model labels into Sirgal data types, only when a person is present.

    {'name': 3, 'location address': 1} -> {'home_address': 1}
    {'location street': 1}             -> {}   (an address with nobody attached)
    """
    if not PERSON & set(labels_found):
        return {}
    found = {}
    addresses = sum(n for label, n in labels_found.items() if label in ADDRESS)
    health = sum(n for label, n in labels_found.items() if label in HEALTH)
    if addresses:
        found["home_address"] = addresses
    if health:
        found["health_info"] = health
    return found


class ModelDetector:
    """Loads the model once, then checks text for personal details."""

    def __init__(self, model=DEFAULT_MODEL, threshold=THRESHOLD):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # quiet library deprecation notices
                from gliner import GLiNER
        except ImportError as exc:
            raise ModelNotInstalled(
                'The model layer needs extra packages. Install them with:\n'
                '    pip install "sirgal[ner]"'
            ) from exc
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._model = GLiNER.from_pretrained(model)
        self.threshold = threshold

    def scan_text(self, text: str) -> dict:
        """Return {data_type: count} for personal details tied to a person."""
        labels_found = {}
        for part in chunks(text):
            for entity in self._model.predict_entities(part, LABELS, threshold=self.threshold):
                label = entity["label"]
                labels_found[label] = labels_found.get(label, 0) + 1
        return tied_to_person(labels_found)
