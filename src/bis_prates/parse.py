"""Stage 2 - parse and tidy the BIS CBPOL flat CSV into one long DataFrame.

The flat file is SDMX-CSV: selectively quoted (commas only inside quoted fields),
every coded cell is "CODE: Label", time periods come at two precisions, and missing
observations are carried as the literal string "NaN". parse() normalises all of that
into a tidy frame that the snapshot/report stages can consume directly.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# SDMX concept ids we keep. Matched against the prefix of each "CONCEPT:Label" header,
# so we never load the columns we don't need (TIME_FORMAT, OBS_PRE_BREAK, etc.).
_WANTED = {
    "FREQ",
    "REF_AREA",
    "TIME_PERIOD",
    "OBS_VALUE",
    "OBS_STATUS",
    "UNIT_MEASURE",
    "UNIT_MULT",
    "DECIMALS",
    "TITLE",
    "COMPILATION",
    "SOURCE_REF",
    "SUPP_INFO_BREAKS",
}

# Documented output schema - one row per observation.
_SCHEMA = [
    "freq_code",
    "freq_label",
    "area_code",
    "area_label",
    "date",
    "value",
    "unit_measure",
    "unit_mult",
    "decimals",
    "title",
    "compilation",
    "source_ref",
    "supp_info",
]


def _concept(col: str) -> str:
    # Header cells are "CONCEPT:Human label"; the SDMX concept id is the first token.
    return col.split(":", 1)[0]


def _split_code_label(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    # "US: United States" -> ("US", "United States"). n=1 because labels can contain ": ".
    parts = s.str.split(": ", n=1, expand=True)
    code = parts[0].str.strip()
    if parts.shape[1] > 1:
        label = parts[1].str.strip()
    else:  # series with no coded values at all
        label = pd.Series([pd.NA] * len(s), index=s.index)
    return code, label


def parse(csv_path: str | os.PathLike, *, drop_missing: bool = True) -> pd.DataFrame:
    """Load the flat CSV and return a tidy long frame (see ``_SCHEMA``).

    ``drop_missing`` (default) discards observations flagged ``OBS_STATUS=M`` / value
    ``NaN`` so downstream change/dedupe logic only sees real prints.
    """
    # Quote-aware read (pandas honours RFC-4180). Everything as text, NaN-detection off:
    # we keep the literal "NaN" intact and decide what "missing" means ourselves.
    raw = pd.read_csv(
        csv_path,
        usecols=lambda c: _concept(c) in _WANTED,
        dtype=str,
        na_filter=False,
    )
    # "FREQ:Frequency" -> "FREQ": address columns by concept id from here on.
    raw.columns = [_concept(c) for c in raw.columns]

    out = pd.DataFrame(index=raw.index)

    # Coded dimensions -> explicit code + label.
    out["freq_code"], out["freq_label"] = _split_code_label(raw["FREQ"])
    out["area_code"], out["area_label"] = _split_code_label(raw["REF_AREA"])
    # For unit of measure the label ("Per cent per year") is the useful part.
    _, out["unit_measure"] = _split_code_label(raw["UNIT_MEASURE"])
    unit_mult_code, _ = _split_code_label(raw["UNIT_MULT"])
    decimals_code, _ = _split_code_label(raw["DECIMALS"])
    obs_status_code, _ = _split_code_label(raw["OBS_STATUS"])

    # For these attributes the SDMX *code* is the number (0 = units, 4 = decimals).
    out["unit_mult"] = pd.to_numeric(unit_mult_code, errors="coerce").astype("Int64")
    out["decimals"] = pd.to_numeric(decimals_code, errors="coerce").astype("Int64")

    # Observation: blank or literal "NaN" -> NaN; everything else -> float.
    out["value"] = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")

    # TIME_PERIOD mixes YYYY-MM-DD (daily) and YYYY-MM (monthly); ISO8601 parses both
    # (month-only snaps to the first of the month).
    out["date"] = pd.to_datetime(raw["TIME_PERIOD"], format="ISO8601", errors="coerce")

    # Free-text enrichment, carried through untouched.
    out["title"] = raw["TITLE"].str.strip()
    out["compilation"] = raw["COMPILATION"]
    out["source_ref"] = raw["SOURCE_REF"]
    out["supp_info"] = raw["SUPP_INFO_BREAKS"]

    # Missing policy: drop rows with no real observation (status M or non-numeric value).
    if drop_missing:
        is_missing = out["value"].isna() | obs_status_code.eq("M")
        out = out.loc[~is_missing]

    # Sort by series then time so change-point/dedupe logic is deterministic.
    out = out.sort_values(["area_code", "freq_code", "date"]).reset_index(drop=True)
    return out[_SCHEMA]


def load_csv_path(data_dir: str | os.PathLike = "data") -> Path:
    """Resolve the extracted CSV produced by ``fetch`` within ``data_dir``."""
    return Path(data_dir) / "WS_CBPOL_csv_flat.csv"
