"""Transform tests: change calculation, frequency choice, and definition parsing."""
from __future__ import annotations

import pandas as pd

from bis_prates.transform import (
    active_definition,
    parse_definitions,
    pick_frequency,
    snapshot,
)


def test_change_calculation(make_tidy):
    df = make_tidy(
        [
            {"area_code": "US", "date": "2020-01-01", "value": 1.0},
            {"area_code": "US", "date": "2020-01-02", "value": 1.0},
            {"area_code": "US", "date": "2020-01-03", "value": 1.25},  # +0.25 move
        ]
    )
    row = snapshot(df, ["US"]).iloc[0]
    assert row["value"] == 1.25
    assert row["prev_level"] == 1.0
    assert row["change"] == 0.25
    assert row["direction"] == "up"
    assert row["last_change_date"] == pd.Timestamp("2020-01-03")


def test_snapshot_asof_clamps_history(make_tidy):
    df = make_tidy(
        [
            {"area_code": "US", "date": "2020-01-01", "value": 1.0},
            {"area_code": "US", "date": "2021-01-01", "value": 2.0},
        ]
    )
    row = snapshot(df, ["US"], asof="2020-06-01").iloc[0]
    assert row["value"] == 1.0  # the later print is excluded by asof
    assert row["date"] == pd.Timestamp("2020-01-01")


def test_pick_frequency_prefers_daily(make_tidy):
    df = make_tidy(
        [
            {"area_code": "US", "freq_code": "M", "date": "2020-01", "value": 1.0},
            {"area_code": "US", "freq_code": "D", "date": "2020-01-02", "value": 1.0},
        ]
    )
    assert pick_frequency(df, "US") == "D"
    assert pick_frequency(df, "ZZ") is None


def test_parse_definitions_handles_missing_colons():
    # CH-style: clauses without a colon, and a full month name ("June").
    text = (
        "From 13 June 2019 onwards SNB Policy rate; "
        "from 1 Jan 1946 to 31 Dec 1999: discount rate."
    )
    defs = parse_definitions(text)
    assert len(defs) == 2
    assert defs[0].start == pd.Timestamp("1946-01-01")  # sorted oldest first
    assert defs[-1].start == pd.Timestamp("2019-06-13")
    assert defs[-1].end is None  # "onwards"
    assert defs[-1].text == "SNB Policy rate"


def test_active_definition_prefers_most_recent():
    # The "31 July" clause has no year, so it mis-parses as open-ended. The current
    # definition must still win for a recent date.
    text = (
        "From 22 Dec 2025 onwards: rate at 0.75 percent; "
        "From 21 Mar 2024 to 31 July: rate at 0.1 percent"
    )
    defs = parse_definitions(text)
    active = active_definition(defs, pd.Timestamp("2026-05-01"))
    assert active is not None
    assert "0.75" in active.text
