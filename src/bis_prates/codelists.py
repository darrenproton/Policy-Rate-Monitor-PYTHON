"""REF_AREA helpers - official codelist validation, aliasing, did-you-mean suggestions.

Cross-organisation code drift is the trap: the exercise example asks for "EA", but BIS codes
the euro area as "XM". Validation is backed by the authoritative BIS SDMX codelist
(CL_BIS_GL_REF_AREA) fetched via pysdmx and cached; if that's unavailable (offline / pysdmx not
installed) callers fall back to the codes present in the downloaded dataset.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path

# Known aliases -> canonical BIS REF_AREA codes.
ALIASES = {"EA": "XM"}

# Explanatory guidance for common-but-invalid inputs - clearer than a fuzzy guess.
GUIDANCE = {
    "EU": (
        "there is no EU-wide region in this dataset. The euro area is represented as code "
        "XM - related but not the same as the EU (the euro area is the subset of EU members "
        "that use the euro)."
    ),
}

# The authoritative REF_AREA codelist used by the CBPOL data structure.
BIS_SDMX_ENDPOINT = "https://stats.bis.org/api/v2"
AREA_CODELIST = ("BIS", "CL_BIS_GL_REF_AREA", "1.0")
_CODELIST_CACHE = "CL_BIS_GL_REF_AREA.json"


@dataclass
class Resolution:
    """Outcome of resolving a requested country list against the valid codes."""

    resolved: list[str]  # valid, de-aliased, de-duplicated (request order preserved)
    unknown: list[str]  # requested tokens with no match
    suggestions: dict[str, list[str]]  # unknown token -> closest valid codes


def normalise(code: str) -> str:
    """Upper-case, trim, and apply aliases (EA -> XM)."""
    code = code.strip().upper()
    return ALIASES.get(code, code)


def guidance_for(token: str) -> str | None:
    """A human explanation for a known confusing input (e.g. EU), if any."""
    return GUIDANCE.get(normalise(token))


def official_area_codes(
    data_dir: str | Path = "data", *, refresh: bool = False, timeout: int = 30
) -> dict[str, str] | None:
    """The authoritative BIS REF_AREA codelist as ``{code: name}`` (via pysdmx, cached).

    Returns ``None`` if it can't be obtained (pysdmx missing or offline), so callers can
    fall back to the codes present in the dataset.
    """
    cache = Path(data_dir) / _CODELIST_CACHE
    if not refresh:
        try:
            return json.loads(cache.read_text())
        except (OSError, json.JSONDecodeError):
            pass  # not cached yet - fetch below

    codes = _fetch_area_codes(timeout)
    if codes is None:
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(codes, indent=2, ensure_ascii=False))
    except OSError:
        pass  # caching is best-effort
    return codes


def _fetch_area_codes(timeout: int) -> dict[str, str] | None:
    try:
        from pysdmx.api.qb import (
            ApiVersion,
            RestService,
            StructureDetail,
            StructureQuery,
            StructureType,
        )
        from pysdmx.io import read_sdmx
    except ImportError:
        return None
    try:
        svc = RestService(
            api_endpoint=BIS_SDMX_ENDPOINT, api_version=ApiVersion.V2_0_0
        )
        agency, resource_id, version = AREA_CODELIST
        query = StructureQuery(
            StructureType.CODELIST, agency, resource_id, version, detail=StructureDetail.FULL
        )
        message = read_sdmx(svc.structure(query).decode("utf-8"))
        codelist = message.get_codelists()[0]
        return {code.id: (code.name or code.id) for code in codelist}
    except Exception:  # noqa: BLE001 - any failure -> graceful fallback
        return None


def resolve(
    requested: list[str], valid: set[str], names: dict[str, str] | None = None
) -> Resolution:
    """Resolve requested codes against ``valid``; collect unknowns + close matches.

    ``names`` (code -> label) enables name-based suggestions, e.g. "germany" -> DE.
    """
    resolved: list[str] = []
    unknown: list[str] = []
    suggestions: dict[str, list[str]] = {}
    seen: set[str] = set()
    for raw in requested:
        code = normalise(raw)
        if code in valid:
            if code not in seen:
                resolved.append(code)
                seen.add(code)
        else:
            unknown.append(raw)
            suggestions[raw] = _suggest(raw, code, valid, names)
    return Resolution(resolved, unknown, suggestions)


def _suggest(raw: str, code: str, valid: set[str], names: dict[str, str] | None) -> list[str]:
    hits = difflib.get_close_matches(code, sorted(valid), n=3)
    if names:  # also match the raw token against names ("united states" -> US)
        by_name = {name.lower(): c for c, name in names.items()}
        for match in difflib.get_close_matches(raw.lower(), list(by_name), n=2):
            candidate = by_name[match]
            if candidate not in hits:
                hits.append(candidate)
    return hits[:3]
