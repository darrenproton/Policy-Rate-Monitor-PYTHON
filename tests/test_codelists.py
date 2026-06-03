"""Codelist tests: EA->XM aliasing, validation, and did-you-mean suggestions."""
from __future__ import annotations

from bis_prates.codelists import normalise, resolve


def test_ea_aliases_to_xm():
    assert normalise("ea") == "XM"
    assert normalise(" gb ") == "GB"  # trim + upper-case


def test_resolve_validates_dedupes_and_suggests():
    valid = {"US", "XM", "GB"}
    res = resolve(["us", "EA", "ZZ", "US"], valid)
    assert res.resolved == ["US", "XM"]  # EA->XM, duplicate US dropped, order kept
    assert res.unknown == ["ZZ"]
    assert "ZZ" in res.suggestions  # close-match list (may be empty) is present
