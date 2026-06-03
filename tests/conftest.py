"""Shared test fixtures - tiny in-memory data, never the 445 MB file."""
from __future__ import annotations

import pandas as pd
import pytest

from bis_prates.parse import _SCHEMA


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
