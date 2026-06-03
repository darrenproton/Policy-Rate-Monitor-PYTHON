"""Stage 3 - turn the tidy frame into change-points and a latest snapshot.

Policy-rate series are forward-filled: a rate is repeated every day until it moves, so
the signal lives in the change-points, not the raw observations. change_points() does the
dedupe; snapshot() reports each country's current rate and its most recent move.

Also parses the COMPILATION attribute into structured definition segments - the metadata
that explains, e.g., why the US series is noisy pre-1985 (effective vs target rate).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

# A distinct series is one reference area at one frequency.
_GROUP = ["area_code", "freq_code"]

# COMPILATION clauses look like: "From 19 Dec 1985 onwards: <def>; from 1 Jul 1954 to
# 18 Dec 1985: <def>". Parse each clause's date span and definition text.
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
_CLAUSE_RE = re.compile(
    r"from\s+(\d{1,2}\s+\w{3,}\s+\d{4})"  # start date
    r"(?:\s+onwards|\s+to\s+(\d{1,2}\s+\w{3,}\s+\d{4}))?"  # optional end date
    r"\s*:?\s*(.*)",  # optional ':' then the definition text (BIS punctuation varies)
    re.IGNORECASE,
)


@dataclass
class Definition:
    """One period of a series' methodology, parsed from COMPILATION."""

    start: pd.Timestamp
    end: pd.Timestamp | None  # None = "onwards"
    text: str


@dataclass
class SeriesMeta:
    """Per-series provenance/definition bundle for the report."""

    area_code: str
    area_label: str
    source_ref: str
    compilation: str
    supp_info: str
    definitions: list[Definition]

    def breaks(self) -> list[pd.Timestamp]:
        """Internal boundaries = where the definition changes (all starts but the earliest)."""
        starts = sorted(d.start for d in self.definitions if d.start is not None)
        return starts[1:]

    def relevant_definitions(
        self, start: str | None = None, end: str | None = None
    ) -> list[Definition]:
        """Definitions overlapping [start, end] - i.e. in force during the window.

        Overlap naturally includes the definition active *when the window begins*, so the
        reader sees each country's policy at the graph's start plus any changes within it.
        """
        lo = pd.Timestamp(start) if start else pd.Timestamp.min
        hi = pd.Timestamp(end) if end else pd.Timestamp.max
        return [
            d
            for d in self.definitions
            if d.start is not None and d.start <= hi and (d.end is None or d.end >= lo)
        ]


def _to_date(text: str | None) -> pd.Timestamp | None:
    # Locale-free "DD Mon YYYY" parse (don't rely on strptime %b honouring the locale).
    if not text:
        return None
    parts = text.strip().split()
    if len(parts) != 3:
        return None
    day, mon, year = parts
    month = _MONTHS.get(mon.lower()[:3])
    if month is None:
        return None
    try:
        return pd.Timestamp(int(year), month, int(day))
    except ValueError:
        return None


def parse_definitions(compilation: str | None) -> list[Definition]:
    """Split a COMPILATION string into date-bounded Definition segments (oldest first)."""
    defs: list[Definition] = []
    for clause in (compilation or "").split(";"):
        match = _CLAUSE_RE.search(clause.strip())
        if match:
            defs.append(
                Definition(
                    _to_date(match.group(1)),
                    _to_date(match.group(2)),
                    match.group(3).strip(),
                )
            )
    defs.sort(key=lambda d: (d.start is None, d.start))
    return defs


def active_definition(defs: list[Definition], asof: pd.Timestamp) -> Definition | None:
    """The definition in force on ``asof`` - the most recent match wins.

    Picking the latest start (not the first hit) is robust to messy source text where a
    bounded clause fails to parse its end date and looks open-ended (e.g. JP "to 31 July").
    """
    covering = [
        d
        for d in defs
        if d.start is not None and d.start <= asof and (d.end is None or asof <= d.end)
    ]
    return max(covering, key=lambda d: d.start) if covering else None


def series_metadata(df: pd.DataFrame, areas: list[str]) -> list[SeriesMeta]:
    """Build a SeriesMeta (source, compilation, parsed definitions, breaks) per area."""
    metas: list[SeriesMeta] = []
    for area in areas:
        sub = df[df["area_code"] == area]
        if sub.empty:
            continue
        row = sub.iloc[0]  # these attributes are constant within a series
        comp = row["compilation"] or ""
        metas.append(
            SeriesMeta(
                area_code=area,
                area_label=row["area_label"],
                source_ref=row["source_ref"] or "",
                compilation=comp,
                supp_info=row["supp_info"] or "",
                definitions=parse_definitions(comp),
            )
        )
    return metas


def change_points(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows where the rate differs from the previous date in the same series.

    Collapses forward-filled runs to the moments the policy rate actually changed.
    """
    df = df.sort_values(_GROUP + ["date"])
    prev = df.groupby(_GROUP, sort=False)["value"].shift()
    # First observation of a series has no predecessor, so it always counts as a change.
    changed = prev.isna() | df["value"].ne(prev)
    return df.loc[changed].reset_index(drop=True)


def pick_frequency(df: pd.DataFrame, area_code: str) -> str | None:
    """Prefer Daily, fall back to Monthly; None if the area is absent."""
    freqs = set(df.loc[df["area_code"] == area_code, "freq_code"])
    for freq in ("D", "M"):
        if freq in freqs:
            return freq
    return None


def snapshot(
    df: pd.DataFrame, areas: list[str], *, asof: str | None = None
) -> pd.DataFrame:
    """One row per area: current rate, latest date, and the most recent change.

    "change" is the size of the last move = current level minus the prior change-point.
    ``asof`` clamps the upper date bound so the snapshot reflects a point in history
    (full prior history is kept for the change calculation); a country with no data on
    or before ``asof`` is simply omitted.
    """
    if asof:
        df = df[df["date"] <= pd.Timestamp(asof)]
    cps = change_points(df)
    rows: list[dict] = []
    for area in areas:
        freq = pick_frequency(df, area)
        if freq is None:
            continue
        series = df[(df["area_code"] == area) & (df["freq_code"] == freq)]
        latest = series.sort_values("date").iloc[-1]

        moves = cps[(cps["area_code"] == area) & (cps["freq_code"] == freq)]
        moves = moves.sort_values("date")
        last_move = moves.iloc[-1]
        # Need at least two change-points to measure the size of the last move.
        prev_level = moves.iloc[-2]["value"] if len(moves) >= 2 else pd.NA
        change = last_move["value"] - prev_level if pd.notna(prev_level) else pd.NA
        direction = _direction(change)

        # Which methodology produced this as-of value (e.g. US "effective" vs "target").
        active = active_definition(parse_definitions(latest["compilation"]), latest["date"])

        rows.append(
            {
                "area_code": area,
                "area_label": latest["area_label"],
                "freq_code": freq,
                "date": latest["date"],
                "value": latest["value"],
                "prev_level": prev_level,
                "change": change,
                "direction": direction,
                "last_change_date": last_move["date"],
                "unit_measure": latest["unit_measure"],
                "unit_mult": latest["unit_mult"],
                "decimals": latest["decimals"],
                "title": latest["title"],
                "definition": active.text if active else None,
                "source_ref": latest["source_ref"],
                "compilation": latest["compilation"],
                "supp_info": latest["supp_info"],
            }
        )
    return pd.DataFrame(rows)


def select_series(
    df: pd.DataFrame,
    areas: list[str],
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Preferred-frequency series for ``areas``, optionally clipped to [start, end]."""
    frames = []
    for area in areas:
        freq = pick_frequency(df, area)
        if freq is not None:
            frames.append(df[(df["area_code"] == area) & (df["freq_code"] == freq)])
    out = pd.concat(frames) if frames else df.iloc[0:0]
    if start:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end:
        out = out[out["date"] <= pd.Timestamp(end)]
    return out.sort_values(["area_code", "date"]).reset_index(drop=True)


def _direction(change) -> str:
    if pd.isna(change):
        return "unchanged"
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"
