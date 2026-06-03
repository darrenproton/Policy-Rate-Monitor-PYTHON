"""Speeches tests: window->years, discovery, and normalised rates (no network)."""
from __future__ import annotations

import pandas as pd

from bis_prates.speeches import discover_terms, term_rates, years_for_window


def test_years_for_window_intersects_available():
    assert years_for_window("2020-01-01", "2022-12-31", 2026) == [2020, 2021, 2022]
    assert years_for_window(None, "1998-06-01", 2026) == [1997, 1998]  # clamped to 1997
    assert years_for_window("1970-01-01", "1990-12-31", 2026) == []  # before speeches exist


def test_term_rates_are_volume_normalised():
    # Same term density, different speech volume -> same per-1k-words rate.
    speeches = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-10", "2024-02-05", "2024-02-25"]),
            "text": ["inflation rises", "inflation rises", "inflation rises"],
        }
    )
    rates = term_rates(speeches, ["inflation"])
    jan = rates.loc[pd.Timestamp("2024-01-01"), "inflation"]  # 1 speech
    feb = rates.loc[pd.Timestamp("2024-02-01"), "inflation"]  # 2 speeches, same density
    assert jan == feb == 500.0  # 1 of 2 words -> 500 per 1,000


def test_discover_terms_finds_distinctive_words():
    # 'inflation'/'tightening' are concentrated; 'outlook' is everywhere (uninformative).
    speeches = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]
            ),
            "text": [
                "inflation inflation outlook",
                "inflation outlook prices prices",
                "tightening tightening outlook cycle",
                "tightening cycle outlook",
            ],
        }
    )
    terms = discover_terms(speeches, n_terms=4, min_df=1, max_df=1.0)
    assert "inflation" in terms
    assert "tightening" in terms
    assert "outlook" not in terms  # steady/ubiquitous word is ranked out by low variability


def test_discover_terms_needs_multiple_months():
    speeches = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-05"]), "text": ["inflation rises"]}
    )
    assert discover_terms(speeches) == []
