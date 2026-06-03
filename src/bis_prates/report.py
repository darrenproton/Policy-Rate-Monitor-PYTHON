"""Stage 4 - render the snapshot and series into the required deliverables.

Writes out/summary.csv, out/summary.json, out/policy_rates.png (a step chart - correct
for forward-filled rates), and out/report.md with a data-provenance footer.
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: render straight to a file, never to a screen

import matplotlib.pyplot as plt  # noqa: E402  (import must follow backend selection)
import pandas as pd  # noqa: E402


def build_report(
    snapshot: pd.DataFrame,
    series: pd.DataFrame,
    provenance: dict | None = None,
    *,
    out_dir: str | os.PathLike = "out",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Path]:
    """Write all four deliverables and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chart = _plot_series(series, out)
    return {
        "summary_csv": _write_summary_csv(snapshot, out),
        "summary_json": _write_summary_json(snapshot, out),
        "chart": chart,
        "report": _write_report_md(snapshot, provenance, chart, out, start, end),
    }


def _window_label(start: str | None, end: str | None) -> str:
    if start and end:
        return f" ({start} to {end})"
    if start:
        return f" (from {start})"
    if end:
        return f" (up to {end})"
    return ""


def _write_summary_csv(snapshot: pd.DataFrame, out: Path) -> Path:
    path = out / "summary.csv"
    snapshot.to_csv(path, index=False)
    return path


def _write_summary_json(snapshot: pd.DataFrame, out: Path) -> Path:
    path = out / "summary.json"
    # ISO dates, NA -> null; records orient = one object per country.
    path.write_text(snapshot.to_json(orient="records", date_format="iso", indent=2))
    return path


def _plot_series(series: pd.DataFrame, out: Path) -> Path:
    path = out / "policy_rates.png"
    fig, ax = plt.subplots(figsize=(9, 5))
    for code, grp in series.groupby("area_code"):
        label = grp["area_label"].iloc[0]
        # steps-post: the rate holds until the next change - the honest shape for this data.
        ax.step(grp["date"], grp["value"], where="post", label=f"{label} ({code})")
    ax.set_title("Central bank policy rates")
    ax.set_ylabel("Per cent per year")
    ax.set_xlabel("Date")
    ax.grid(True, alpha=0.3)
    if not series.empty:
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _fmt(value, decimals: int = 3) -> str:
    return "n/a" if pd.isna(value) else f"{value:.{decimals}f}"


def _md_table(snapshot: pd.DataFrame) -> str:
    rows = [
        "| Country | Rate (%) | As of | Last change | Change (pp) |",
        "|---|---:|---|---|---:|",
    ]
    for _, r in snapshot.iterrows():
        delta = "n/a" if pd.isna(r["change"]) else f"{r['change']:+.3f} ({r['direction']})"
        last = "" if pd.isna(r["last_change_date"]) else r["last_change_date"].date()
        rows.append(
            f"| {r['area_label']} ({r['area_code']}) | {_fmt(r['value'])} | "
            f"{r['date'].date()} | {last} | {delta} |"
        )
    return "\n".join(rows)


def _provenance_footer(provenance: dict | None) -> str:
    if not provenance:
        return "_Source provenance unavailable (run `bis-prates fetch`)._"
    p = provenance
    name = p.get("dataflow_name")
    version = p.get("version")
    return "\n".join(
        [
            "## Data provenance",
            "",
            f"- Dataset: {p.get('dataflow_id')} v{version} ({p.get('source_url')})",
            f"- Title: {name}",
            f"- Downloaded: {p.get('downloaded_at')}",
            f"- Last-Modified: {p.get('last_modified')}",
            f"- Size: {p.get('content_length')} bytes",
            f"- SHA-256: `{p.get('sha256')}`",
        ]
    )


def _write_report_md(
    snapshot: pd.DataFrame,
    provenance: dict | None,
    chart: Path,
    out: Path,
    start: str | None,
    end: str | None = None,
) -> Path:
    path = out / "report.md"
    window = _window_label(start, end)
    unit = snapshot["unit_measure"].iloc[0] if not snapshot.empty else ""
    body = "\n".join(
        [
            "# BIS Policy Rate Monitor",
            "",
            f"Latest central bank policy-rate snapshot{window}. Unit: {unit}.",
            "",
            "## Snapshot",
            "",
            _md_table(snapshot),
            "",
            "## Policy rates over time",
            "",
            f"![Policy rates]({chart.name})",
            "",
            _provenance_footer(provenance),
            "",
        ]
    )
    path.write_text(body)
    return path
