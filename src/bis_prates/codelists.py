"""REF_AREA helpers - alias resolution, validation, and did-you-mean suggestions.

Cross-organisation code drift is the trap here: the exercise example asks for "EA",
but BIS codes the euro area as "XM". Stage 8 can back validation with the live SDMX
codelist; for now we validate against the codes actually present in the dataset.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

# Known aliases -> canonical BIS REF_AREA codes.
ALIASES = {"EA": "XM"}


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


def resolve(requested: list[str], valid: set[str]) -> Resolution:
    """Resolve requested codes against ``valid``; collect unknowns + close matches."""
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
            suggestions[raw] = difflib.get_close_matches(code, sorted(valid), n=3)
    return Resolution(resolved, unknown, suggestions)
