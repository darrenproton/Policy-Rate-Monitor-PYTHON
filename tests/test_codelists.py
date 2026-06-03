"""Codelist tests: EA->XM aliasing, validation, and did-you-mean suggestions."""
from __future__ import annotations

import json

from bis_prates.codelists import (
    _CODELIST_CACHE,
    guidance_for,
    normalise,
    official_area_codes,
    resolve,
)


def test_ea_aliases_to_xm():
    assert normalise("ea") == "XM"
    assert normalise(" gb ") == "GB"  # trim + upper-case


def test_resolve_validates_dedupes_and_suggests():
    valid = {"US", "XM", "GB"}
    res = resolve(["us", "EA", "ZZ", "US"], valid)
    assert res.resolved == ["US", "XM"]  # EA->XM, duplicate US dropped, order kept
    assert res.unknown == ["ZZ"]
    assert "ZZ" in res.suggestions  # close-match list (may be empty) is present


def test_resolve_suggests_by_name():
    valid = {"US", "DE", "GB"}
    names = {"US": "United States", "DE": "Germany", "GB": "United Kingdom"}
    res = resolve(["germany"], valid, names)
    assert res.unknown == ["germany"]
    assert "DE" in res.suggestions["germany"]  # name match -> code


def test_guidance_for_eu():
    note = guidance_for("eu")  # case-insensitive
    assert note is not None
    assert "XM" in note and "euro area" in note.lower()
    assert guidance_for("ZZ") is None


def test_official_area_codes_reads_cache(tmp_path):
    # A cached file means no network is touched.
    (tmp_path / _CODELIST_CACHE).write_text(json.dumps({"US": "United States", "XM": "Euro area"}))
    codes = official_area_codes(tmp_path)
    assert codes == {"US": "United States", "XM": "Euro area"}
