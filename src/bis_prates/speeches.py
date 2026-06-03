"""Stage 9 (Extension 2) - BIS central-bank speeches term-frequency analysis.

Pulls the BIS speeches corpus via gingado (flag-gated, cached) and counts monthly mentions
of a set of terms, so the report can compare central-bank rhetoric with policy-rate moves.
Speeches start in 1997, so windows before that yield nothing.
"""
from __future__ import annotations

import re

import pandas as pd

DEFAULT_TERMS = ["inflation", "rate", "tightening", "easing"]
EARLIEST_YEAR = 1997


def years_for_window(
    start: str | None, end: str | None, latest_year: int
) -> list[int]:
    """Years to load = the report window intersected with the available speech years."""
    lo = pd.Timestamp(start).year if start else EARLIEST_YEAR
    hi = pd.Timestamp(end).year if end else latest_year
    lo, hi = max(lo, EARLIEST_YEAR), min(hi, latest_year)
    return list(range(lo, hi + 1)) if hi >= lo else []


def load_speeches(years: list[int], *, timeout: float = 120) -> pd.DataFrame:
    """Load BIS speeches for ``years`` via gingado (cached). Returns at least [date, text]."""
    from gingado.datasets import load_CB_speeches

    frames = []
    for year in years:
        try:
            frames.append(load_CB_speeches(year, timeout=timeout))
        except Exception:  # noqa: BLE001 - skip a year that fails to download
            continue
    if not frames:
        return pd.DataFrame(columns=["date", "text", "author", "title"])
    df = pd.concat(frames, ignore_index=True).dropna(subset=["date", "text"]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).reset_index(drop=True)


def term_frequency(speeches: pd.DataFrame, terms: list[str]) -> pd.DataFrame:
    """Monthly count of whole-word term mentions across all speeches.

    Index = month start, one column per term. Reindexed to a continuous monthly range.
    """
    if speeches.empty:
        return pd.DataFrame()
    text = speeches["text"].fillna("").str.lower()
    month = speeches["date"].dt.to_period("M").dt.to_timestamp()

    data = {}
    for term in terms:
        pattern = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
        data[term] = text.map(lambda t, p=pattern: len(p.findall(t)))
    counts = pd.DataFrame(data)
    counts["month"] = month.values

    out = counts.groupby("month").sum().sort_index()
    if not out.empty:
        full = pd.date_range(out.index.min(), out.index.max(), freq="MS")
        out = out.reindex(full, fill_value=0)
        out.index.name = "month"
    return out
