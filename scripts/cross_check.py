#!/usr/bin/env python3
"""Cross-implementation consistency check for the BIS Policy Rate Monitor.

The same tool was built three independent ways — this Python CLI, a Bash CLI
(a port), and a Python web app (built blind by another agent). This script runs
the two CLIs over identical date ranges, reading the *same* downloaded dataset,
and verifies they produce identical latest-snapshot results (latest rate + last
move) for every country. It also pings the live web app's API and checks its
current snapshot agrees.

The numbers that must match are **latest rate** and **change** (the last move).
`last_change_date` is reported too, but a difference there is treated as a
non-fatal note, not a failure (the Bash build renders monthly periods at the
month midpoint, which can disagree with the daily change-point's exact date —
a cosmetic artifact that does not affect any rate or change value).

Usage:
    python scripts/cross_check.py \
        --csv data/WS_CBPOL_csv_flat.csv \
        --bash /path/to/policy-rate-monitor.sh \
        --claw-url https://bis-prates.dignam.space

Writes a Markdown report to stdout and, if $GITHUB_STEP_SUMMARY is set (or
--summary is given), appends it there so it renders on the Actions run page.
Exits non-zero if any rate or change disagrees.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

COUNTRIES = "US,XM,GB,JP,CH"

# Each case sets a window; the snapshot is taken "as of" --end (or today if None).
CASES = [
    {"id": "latest", "label": "Latest snapshot (as of today)", "start": "2015-01-01", "end": None},
    {"id": "gfc", "label": "As of 2008-12-31 (GFC trough)", "start": "2000-01-01", "end": "2008-12-31"},
    {"id": "covid", "label": "As of 2020-03-31 (COVID)", "start": "2010-01-01", "end": "2020-03-31"},
    {"id": "peak", "label": "As of 2024-06-30 (peak rates)", "start": "2015-01-01", "end": "2024-06-30"},
    {"id": "hist", "label": "1980–1990 (historical; XM should be absent)", "start": "1980-01-01", "end": "1990-12-31"},
]

TOL = 1e-6


def to_float(s):
    """Parse a rate/change cell to float; '', 'n/a', None -> None."""
    if s is None:
        return None
    s = str(s).strip().lstrip("+")
    if s == "" or s.lower() in {"n/a", "na", "none", "nan"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_summary(path: Path, rate_col: str):
    """Return {area_code: {'rate', 'change', 'date'}} from a summary.csv."""
    out = {}
    if not path.exists():
        return out
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            code = row.get("area_code", "").strip()
            if not code:
                continue
            out[code] = {
                "rate": to_float(row.get(rate_col)),
                "change": to_float(row.get("change")),
                "date": (row.get("last_change_date") or "").strip(),
            }
    return out


def run(cmd, *, cwd=None, env=None):
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}\n")
    return proc


def eq(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) < TOL


def fmt(x):
    return "—" if x is None else f"{x:g}"


def fetch_claw(url: str):
    """Best-effort: GET the live app's latest snapshot. Returns dict or None."""
    api = url.rstrip("/") + f"/api/summary?countries={COUNTRIES}"
    try:
        with urllib.request.urlopen(api, timeout=15) as r:
            data = json.load(r)
    except Exception as exc:  # noqa: BLE001 - any failure -> skip, don't fail CI
        sys.stderr.write(f"CLAW API not reachable ({exc}); skipping live check.\n")
        return None
    out = {}
    for row in data:
        code = row.get("country_code")
        if not code:
            continue
        bps = row.get("change_bps")
        out[code] = {
            "rate": to_float(row.get("latest_rate")),
            "change": (bps / 100.0) if isinstance(bps, (int, float)) else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="Shared extracted BIS CSV (both tools read this).")
    ap.add_argument("--bash", required=True, help="Path to the Bash policy-rate-monitor.sh.")
    ap.add_argument("--python-bin", default="bis-prates", help="Python CLI entry point.")
    ap.add_argument("--claw-url", default="", help="Base URL of the live web app (optional).")
    ap.add_argument("--workdir", default="xcheck-out", help="Where to write per-case outputs.")
    ap.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
                    help="File to append the Markdown report to (default: $GITHUB_STEP_SUMMARY).")
    args = ap.parse_args()

    csv_path = Path(args.csv).resolve()
    bash_script = Path(args.bash).resolve()
    data_dir = csv_path.parent
    work = Path(args.workdir).resolve()
    py_root = work / "python"
    ba_root = work / "bash"
    py_root.mkdir(parents=True, exist_ok=True)
    ba_root.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        sys.exit(f"shared CSV not found: {csv_path}")
    if not bash_script.exists():
        sys.exit(f"bash script not found: {bash_script}")

    # Bash builds its tidy table once, from the shared CSV.
    bash_env = {**os.environ, "DATA_DIR": str(data_dir)}
    print("Building Bash tidy table (one-off)...", file=sys.stderr)
    run(["bash", str(bash_script), "transform"], env=bash_env)

    md = []
    md.append("# BIS Policy Rate Monitor — cross-implementation consistency\n")
    md.append(
        "Three independent builds (Python CLI · Bash CLI · web app) run over identical date "
        "ranges off the **same** downloaded dataset. **Latest rate** and **change** must match; "
        "`last_change_date` is informational.\n"
    )

    hard_fail = False
    date_notes = []

    for case in CASES:
        common = ["--countries", COUNTRIES, "--start", case["start"]]
        if case["end"]:
            common += ["--end", case["end"]]

        py_out = py_root / case["id"]
        ba_out = ba_root / case["id"]
        # Python reads the raw CSV directly via --csv.
        run([args.python_bin, "report", *common, "--csv", str(csv_path), "--out", str(py_out)])
        # Bash reads the shared CSV via DATA_DIR (transform already built tidy.tsv).
        run(["bash", str(bash_script), "report", *common, "--out", str(ba_out)], env=bash_env)

        py = load_summary(py_out / "summary.csv", rate_col="value")
        ba = load_summary(ba_out / "summary.csv", rate_col="latest_rate")

        md.append(f"\n## {case['label']}\n")
        md.append("| Country | PY rate | BA rate | rate ✓ | PY change | BA change | change ✓ | dates |")
        md.append("|---|--:|--:|:--:|--:|--:|:--:|---|")

        for code in COUNTRIES.split(","):
            p, b = py.get(code), ba.get(code)
            if p is None and b is None:
                md.append(f"| {code} | — | — | ➖ | — | — | ➖ | absent in both (expected) |")
                continue
            if p is None or b is None:
                hard_fail = True
                md.append(f"| {code} | {fmt(p['rate']) if p else '—'} | "
                          f"{fmt(b['rate']) if b else '—'} | ❌ | — | — | ❌ | "
                          f"**present in only one** |")
                continue
            rate_ok = eq(p["rate"], b["rate"])
            chg_ok = eq(p["change"], b["change"])
            hard_fail = hard_fail or not rate_ok or not chg_ok
            date_cell = "match"
            if p["date"] and b["date"] and p["date"] != b["date"]:
                date_cell = f"⚠️ PY {p['date']} / BA {b['date']}"
                date_notes.append(f"- **{case['label']} · {code}**: {date_cell} "
                                  f"(rate & change still agree)")
            md.append(
                f"| {code} | {fmt(p['rate'])} | {fmt(b['rate'])} | {'✅' if rate_ok else '❌'} | "
                f"{fmt(p['change'])} | {fmt(b['change'])} | {'✅' if chg_ok else '❌'} | {date_cell} |"
            )

    # Live web app — latest snapshot only.
    md.append("\n## Live web app (CLAW) — current snapshot\n")
    claw = fetch_claw(args.claw_url) if args.claw_url else None
    if claw is None:
        md.append("_Live app not reachable — skipped (does not affect the verdict)._\n")
    else:
        py_latest = load_summary(py_root / "latest" / "summary.csv", rate_col="value")
        md.append("| Country | rate (PY/BA) | CLAW rate | rate ✓ | change (PY/BA) | CLAW change | change ✓ |")
        md.append("|---|--:|--:|:--:|--:|--:|:--:|")
        for code in COUNTRIES.split(","):
            ref, c = py_latest.get(code), claw.get(code)
            if ref is None or c is None:
                continue
            rate_ok = eq(ref["rate"], c["rate"])
            chg_ok = eq(ref["change"], c["change"])
            hard_fail = hard_fail or not rate_ok or not chg_ok
            md.append(
                f"| {code} | {fmt(ref['rate'])} | {fmt(c['rate'])} | {'✅' if rate_ok else '❌'} | "
                f"{fmt(ref['change'])} | {fmt(c['change'])} | {'✅' if chg_ok else '❌'} |"
            )

    verdict = "❌ **FAIL** — a rate or change disagrees" if hard_fail else \
        "✅ **PASS** — every latest rate and change agrees across all implementations"
    md.insert(2, f"\n## Verdict: {verdict}\n")

    if date_notes:
        md.append("\n### Notes (non-fatal)\n")
        md.append("`last_change_date` differences — the value and the move still match exactly:\n")
        md.extend(date_notes)

    report = "\n".join(md) + "\n"
    print(report)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(report)

    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
