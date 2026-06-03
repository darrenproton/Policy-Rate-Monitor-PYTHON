"""Shared test fixtures - tiny in-memory data, never the 445 MB file."""
from __future__ import annotations

import pandas as pd
import pytest

from bis_prates.parse import _SCHEMA

# A small but realistic SDMX-flat file: two countries, each with a rate change, quoted
# COMPILATION, and a missing (M/NaN) row. Enough for parse -> transform -> report.
_SAMPLE_CSV = (
    "FREQ:Frequency,REF_AREA:Reference area,TIME_PERIOD:Time period or range,"
    "OBS_VALUE:Observation Value,UNIT_MEASURE:Unit of measure,UNIT_MULT:Unit Multiplier,"
    "DECIMALS:Decimals,TITLE:Title,COMPILATION:Compilation,SOURCE_REF:Publication Source,"
    "SUPP_INFO_BREAKS:Supplemental information and breaks,OBS_STATUS:Observation Status\n"
    "D: Daily,US: United States,2020-01-01,1.0,368: Per cent per year,0: Units,4: Four,"
    'US,"From 1 Jan 2000 onwards: Fed target rate",US Fed,,A: Normal value\n'
    "D: Daily,US: United States,2020-01-02,1.0,368: Per cent per year,0: Units,4: Four,"
    'US,"From 1 Jan 2000 onwards: Fed target rate",US Fed,,A: Normal value\n'
    "D: Daily,US: United States,2020-01-03,1.25,368: Per cent per year,0: Units,4: Four,"
    'US,"From 1 Jan 2000 onwards: Fed target rate",US Fed,,A: Normal value\n'
    "D: Daily,US: United States,2020-01-04,NaN,368: Per cent per year,0: Units,4: Four,"
    'US,"From 1 Jan 2000 onwards: Fed target rate",US Fed,,M: Missing value; data cannot exist\n'
    "D: Daily,GB: United Kingdom,2020-01-01,5.0,368: Per cent per year,0: Units,4: Four,"
    'GB,"From 1 Jan 2000 onwards: official bank rate",Bank of England,,A: Normal value\n'
    "D: Daily,GB: United Kingdom,2020-01-02,5.5,368: Per cent per year,0: Units,4: Four,"
    'GB,"From 1 Jan 2000 onwards: official bank rate",Bank of England,,A: Normal value\n'
)


@pytest.fixture
def sample_csv(tmp_path):
    """Path to a small SDMX-flat CSV written to a temp dir."""
    path = tmp_path / "WS_CBPOL_csv_flat.csv"
    path.write_text(_SAMPLE_CSV)
    return path


@pytest.fixture
def make_tidy():
    """Factory: build a tidy DataFrame from minimal records (defaults fill the rest)."""

    def _make(records: list[dict]) -> pd.DataFrame:
        rows = []
        for r in records:
            freq = r.get("freq_code", "D")
            rows.append(
                {
                    "freq_code": freq,
                    "freq_label": "Daily" if freq == "D" else "Monthly",
                    "area_code": r["area_code"],
                    "area_label": r.get("area_label", r["area_code"]),
                    "date": pd.Timestamp(r["date"]),
                    "value": r["value"],
                    "unit_measure": r.get("unit_measure", "Per cent per year"),
                    "unit_mult": r.get("unit_mult", 0),
                    "decimals": r.get("decimals", 4),
                    "title": r.get("title", ""),
                    "compilation": r.get("compilation", ""),
                    "source_ref": r.get("source_ref", ""),
                    "supp_info": r.get("supp_info", ""),
                }
            )
        return pd.DataFrame(rows, columns=_SCHEMA)

    return _make
