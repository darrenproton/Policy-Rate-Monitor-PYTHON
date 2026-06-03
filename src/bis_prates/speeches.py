"""Stage 9 (Extension 2) - BIS central-bank speeches term analysis.

Pulls the BIS speeches corpus via gingado (flag-gated, cached). Rather than counting a
hard-coded word list, it *discovers* the interesting words: each monthly slice has its own
"standout" terms (top TF-IDF), those are pooled across all slices into a global set, and each
term is then charted as a volume-normalised rate (mentions per 1,000 words) so a busy speech
month no longer dominates. Speeches start in 1997, so earlier windows yield nothing.
"""
from __future__ import annotations

import re

import pandas as pd

DEFAULT_N_TERMS = 6
EARLIEST_YEAR = 1997

# Obvious speech boilerplate; topical words (inflation, rate, ...) are left for TF-IDF/max_df.
_EXTRA_STOPWORDS = {
    "mr", "ms", "dr", "thank", "ladies", "gentlemen", "governor", "president",
    "speech", "today", "said", "also", "would", "let", "like",
    "percent", "percentage", "cent",  # units words, not themes
}


def years_for_window(start: str | None, end: str | None, latest_year: int) -> list[int]:
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


def discover_terms(
    speeches: pd.DataFrame,
    *,
    n_terms: int = DEFAULT_N_TERMS,
    min_df: float = 0.10,
    max_df: float = 0.6,
) -> list[str]:
    """Discover interesting words: broadly-used terms whose monthly usage *moves* the most.

    Pure TF-IDF rewards rarity and surfaces bank-specific jargon (CNB, rupiah, ...). Instead we
    keep the mid-frequency band - words in ``min_df``..``max_df`` of speeches, i.e. common enough
    to be shared vocabulary but not ubiquitous boilerplate (bank, policy) - and rank them by the
    temporal variability of their monthly share: the words that rise and fall over time, which is
    what tracks policy shifts. Returns the top ``n_terms`` words.
    """
    if speeches.empty:
        return []
    month = speeches["date"].dt.to_period("M").dt.to_timestamp()
    if month.nunique() < 2:
        return []

    from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS

    stop = list(ENGLISH_STOP_WORDS | _EXTRA_STOPWORDS)
    vec = CountVectorizer(
        stop_words=stop,
        token_pattern=r"(?u)\b[a-z]{3,}\b",
        min_df=min_df,
        max_df=max_df,
    )
    try:
        counts = vec.fit_transform(speeches["text"].fillna(""))
    except ValueError:  # empty vocabulary after pruning
        return []

    monthly = pd.DataFrame(counts.toarray(), columns=vec.get_feature_names_out())
    monthly["_m"] = month.to_numpy()
    monthly = monthly.groupby("_m").sum()
    # Monthly share of words, then rank by how much each term's share moves over time.
    shares = monthly.div(monthly.sum(axis=1).replace(0, pd.NA), axis=0).fillna(0.0)
    variability = shares.std(axis=0).sort_values(ascending=False)
    return variability.head(n_terms).index.tolist()


def term_rates(speeches: pd.DataFrame, terms: list[str]) -> pd.DataFrame:
    """Per-month mentions per 1,000 words for each term (volume-normalised).

    Index = month start, one column per term, reindexed to a continuous monthly range.
    """
    if speeches.empty or not terms:
        return pd.DataFrame()
    month = speeches["date"].dt.to_period("M").dt.to_timestamp()
    text = speeches["text"].fillna("").str.lower()

    data = {"_month": month.to_numpy(), "_words": text.str.count(r"\b\w+\b").to_numpy()}
    for term in terms:
        pattern = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
        data[term] = text.map(lambda t, p=pattern: len(p.findall(t))).to_numpy()

    agg = pd.DataFrame(data).groupby("_month").sum()
    rates = pd.DataFrame(index=agg.index)
    words = agg["_words"].replace(0, pd.NA)
    for term in terms:
        rates[term] = (1000 * agg[term] / words).astype("float").fillna(0.0)

    full = pd.date_range(rates.index.min(), rates.index.max(), freq="MS")
    rates = rates.reindex(full, fill_value=0.0)
    rates.index.name = "month"
    return rates


def lead_lag(
    term: pd.Series,
    rate_change: pd.Series,
    *,
    max_lag: int = 6,
    min_points: int = 6,
) -> tuple[int | None, float, dict[int, float]]:
    """Correlate a term's monthly series against monthly rate changes at offsets.

    For lag L in -max_lag..+max_lag, correlate term[t] with rate_change[t+L]. A positive lag
    means the term *leads* the rate move by L months. Returns (best_lag, best_corr, profile),
    where best is chosen by largest absolute correlation over >= min_points overlapping months.
    """
    profile: dict[int, float] = {}
    for lag in range(-max_lag, max_lag + 1):
        joined = pd.concat([term, rate_change.shift(-lag)], axis=1, join="inner").dropna()
        if len(joined) >= min_points:
            corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])
            if pd.notna(corr):
                profile[lag] = float(corr)
    if not profile:
        return None, float("nan"), {}
    best = max(profile, key=lambda k: abs(profile[k]))
    return best, profile[best], profile


def lead_lag_table(term_freq: pd.DataFrame, rate_change: pd.Series, *, max_lag: int = 6):
    """Best lead/lag and correlation for each term vs the rate-change series."""
    rows = []
    for term in term_freq.columns:
        lag, corr, _ = lead_lag(term_freq[term], rate_change, max_lag=max_lag)
        rows.append({"term": term, "lag": lag, "corr": corr})
    return pd.DataFrame(rows)
