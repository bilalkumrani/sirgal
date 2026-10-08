"""Tests for combining exposure and content into a risk level."""

import pytest

from sirgal.risk import ANYONE, DOMAIN, PEOPLE, PRIVATE, rate


@pytest.mark.parametrize("severity", ["high", "medium", "low", None])
def test_private_files_are_always_ok(severity):
    assert rate(PRIVATE, severity) == "ok"
    assert rate(PRIVATE, severity, checked=False) == "ok"


@pytest.mark.parametrize("exposure", [ANYONE, DOMAIN, PEOPLE])
def test_shared_high_severity_is_high(exposure):
    assert rate(exposure, "high") == "high"


def test_public_link_raises_medium_and_low():
    assert rate(ANYONE, "medium") == "high"
    assert rate(PEOPLE, "medium") == "medium"
    assert rate(ANYONE, "low") == "medium"
    assert rate(PEOPLE, "low") == "low"


def test_shared_with_nothing_found_is_ok():
    assert rate(ANYONE, None) == "ok"


def test_shared_but_unreadable_is_unknown_not_ok():
    assert rate(ANYONE, None, checked=False) == "unknown"
