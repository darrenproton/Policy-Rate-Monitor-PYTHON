"""Stage 3 - turn the tidy frame into change-points and a latest snapshot.

Policy-rate series are forward-filled: a rate is repeated every day until it moves, so
the signal lives in the change-points, not the raw observations. change_points() does the
dedupe; snapshot() reports each country's current rate and its most recent move.
"""
from __future__ import annotations

import pandas as pd

# A distinct series is one reference area at one frequency.
_GROUP = ["area_code", "freq_code"]


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
