"""Parsing tests: quote-aware read, code:label split, NaN/M handling, date shapes."""
from __future__ import annotations

import pandas as pd

from bis_prates.parse import parse

# Minimal SDMX-flat fixture: a quoted comma in COMPILATION, a missing (M/NaN) row,
# and both a daily (YYYY-MM-DD) and a monthly (YYYY-MM) date.
_CSV = (
    "FREQ:Frequency,REF_AREA:Reference area,TIME_PERIOD:Time period or range,"
    "OBS_VALUE:Observation Value,UNIT_MEASURE:Unit of measure,UNIT_MULT:Unit Multiplier,"
    "DECIMALS:Decimals,TITLE:Title,COMPILATION:Compilation,SOURCE_REF:Publication Source,"
    "SUPP_INFO_BREAKS:Supplemental information and breaks,OBS_STATUS:Observation Status\n"
    "D: Daily,US: United States,2020-01-02,1.5,368: Per cent per year,0: Units,4: Four,"
    'US title,"From 1 Jan 2000 onwards: market rate, repo.",US Fed,,A: Normal value\n'
    "D: Daily,US: United States,2020-01-03,NaN,368: Per cent per year,0: Units,4: Four,"
    'US title,"From 1 Jan 2000 onwards: market rate, repo.",US Fed,,'
    "M: Missing value; data cannot exist\n"
    "M: Monthly,US: United States,2019-12,1.25,368: Per cent per year,0: Units,4: Four,"
    'US title,"From 1 Jan 2000 onwards: market rate, repo.",US Fed,,A: Normal value\n'
)


def _csv(tmp_path):
    path = tmp_path / "cbpol.csv"
    path.write_text(_CSV)
    return path


def test_quote_aware_and_code_label_split(tmp_path):
    df = parse(_csv(tmp_path))
    # The M/NaN row is dropped by default -> 2 observations remain.
    assert len(df) == 2
    daily = df[(df.area_code == "US") & (df.freq_code == "D")].iloc[0]
    # code:label split
    assert daily["area_label"] == "United States"
    assert daily["unit_measure"] == "Per cent per year"
    # quote-aware: the embedded comma stayed inside COMPILATION (no mis-split)
    assert daily["value"] == 1.5
    assert "market rate, repo." in daily["compilation"]


def test_both_date_precisions(tmp_path):
    df = parse(_csv(tmp_path))
    monthly = df[df.freq_code == "M"].iloc[0]
    assert monthly["date"] == pd.Timestamp("2019-12-01")  # YYYY-MM -> first of month


def test_missing_kept_when_requested(tmp_path):
    df = parse(_csv(tmp_path), drop_missing=False)
    assert len(df) == 3
    assert df["value"].isna().sum() == 1  # the literal "NaN" became a real NaN
