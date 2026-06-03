"""Speeches tests: term counting + window->years, with no network."""
from __future__ import annotations

import pandas as pd

from bis_prates.speeches import term_frequency, years_for_window


def test_years_for_window_intersects_available():
    assert years_for_window("2020-01-01", "2022-12-31", 2026) == [2020, 2021, 2022]
    assert years_for_window(None, "1998-06-01", 2026) == [1997, 1998]  # clamped to 1997
    assert years_for_window("1970-01-01", "1990-12-31", 2026) == []  # before speeches exist


def test_term_frequency_counts_whole_words_by_month():
    speeches = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-10", "2024-01-20", "2024-02-05"]),
            "text": [
                "Inflation is high; inflation expectations matter.",  # 2 x inflation
                "We are tightening policy.",  # 1 x tightening
                "No change to inflationary pressure",  # whole-word: 0 'inflation'
            ],
        }
    )
    freq = term_frequency(speeches, ["inflation", "tightening"])
    assert list(freq.index) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert freq.loc[pd.Timestamp("2024-01-01"), "inflation"] == 2
    assert freq.loc[pd.Timestamp("2024-01-01"), "tightening"] == 1
    assert freq.loc[pd.Timestamp("2024-02-01"), "inflation"] == 0  # 'inflationary' != 'inflation'


def test_term_frequency_empty_input():
    assert term_frequency(pd.DataFrame(columns=["date", "text"]), ["inflation"]).empty
