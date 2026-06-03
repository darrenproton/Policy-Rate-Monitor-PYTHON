"""Report tests: build_report writes the four deliverables; helpers behave."""
from __future__ import annotations

import json

from bis_prates.parse import parse
from bis_prates.report import _window_label, build_report
from bis_prates.transform import select_series, series_metadata, snapshot

_PROV = {
    "dataflow_id": "WS_CBPOL",
    "dataflow_name": "Central bank policy rates",
    "version": "1.0",
    "source_url": "https://example/WS_CBPOL_csv_flat.zip",
    "last_modified": "Wed, 27 May 2026 14:33:36 GMT",
    "content_length": 4077523,
    "sha256": "deadbeef",
    "downloaded_at": "2026-06-03T00:00:00+00:00",
}


def _build(sample_csv, out, provenance=_PROV, areas=("US", "GB"), **kw):
    df = parse(sample_csv)
    areas = list(areas)
    snap = snapshot(df, areas)
    series = select_series(df, areas)
    metas = series_metadata(df, areas)
    return build_report(snap, series, provenance, metas, out_dir=out, **kw)


def test_build_report_writes_all_outputs(sample_csv, tmp_path):
    out = tmp_path / "out"
    paths = _build(sample_csv, out)

    assert set(paths) == {"summary_csv", "summary_json", "chart", "report"}
    for p in paths.values():
        assert p.exists()

    # summary.csv carries both countries + enrichment columns
    csv_text = paths["summary_csv"].read_text()
    assert "US" in csv_text and "GB" in csv_text
    assert "definition" in csv_text and "source_ref" in csv_text

    # summary.json is valid and records both
    data = json.loads(paths["summary_json"].read_text())
    assert {r["area_code"] for r in data} == {"US", "GB"}

    # report.md has the expected sections + provenance
    md = paths["report"].read_text()
    assert "## Snapshot" in md
    assert "## Series definitions & notes" in md
    assert "## Data provenance" in md
    assert "WS_CBPOL" in md

    # chart is a real PNG
    assert paths["chart"].read_bytes().startswith(b"\x89PNG")


def test_report_without_provenance(sample_csv, tmp_path):
    paths = _build(sample_csv, tmp_path / "out", provenance=None)
    assert "provenance unavailable" in paths["report"].read_text().lower()


def test_window_label():
    assert _window_label("2020", "2021") == " (2020 to 2021)"
    assert _window_label("2020", None) == " (from 2020)"
    assert _window_label(None, "2021") == " (up to 2021)"
    assert _window_label(None, None) == ""
