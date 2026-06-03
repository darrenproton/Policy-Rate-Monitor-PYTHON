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
    metas: list | None = None,
    *,
    out_dir: str | os.PathLike = "out",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Path]:
    """Write all four deliverables and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chart = _plot_series(series, out, metas or [])
    return {
        "summary_csv": _write_summary_csv(snapshot, out),
        "summary_json": _write_summary_json(snapshot, out),
        "chart": chart,
        "report": _write_report_md(snapshot, provenance, chart, out, start, end, metas or []),
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


def _plot_series(series: pd.DataFrame, out: Path, metas: list) -> Path:
    path = out / "policy_rates.png"
    fig, ax = plt.subplots(figsize=(9, 5))
    colors: dict[str, str] = {}
    for code, grp in series.groupby("area_code"):
        label = grp["area_label"].iloc[0]
        # steps-post: the rate holds until the next change - the honest shape for this data.
        line = ax.step(grp["date"], grp["value"], where="post", label=f"{label} ({code})")[0]
        colors[code] = line.get_color()

    _annotate_breaks(ax, series, metas, colors)

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


def _annotate_breaks(ax, series: pd.DataFrame, metas: list, colors: dict[str, str]) -> None:
    """Draw a dashed line where each visible series changes definition (methodology break)."""
    if series.empty or not metas:
        return
    lo, hi = series["date"].min(), series["date"].max()
    top = ax.get_ylim()[1]
    for meta in metas:
        color = colors.get(meta.area_code)
        if color is None:  # area not plotted (e.g. no data in window)
            continue
        for brk in meta.breaks():
            if lo <= brk <= hi:
                ax.axvline(brk, color=color, linestyle=":", linewidth=1, alpha=0.6)
                ax.text(
                    brk, top, f" {meta.area_code}",
                    color=color, fontsize=7, rotation=90, va="top", ha="left", alpha=0.8,
                )


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


def _series_notes(metas: list, start: str | None = None, end: str | None = None) -> str:
    """Definitions, source, and structural-break notes per series (from the attributes).

    Definitions are limited to those in force during the report window (incl. the one active
    when the window begins); with no window, the full history is shown.
    """
    if not metas:
        return ""
    scoped = " (in force during the report window)" if (start or end) else ""
    lines = [f"## Series definitions & notes{scoped}", ""]
    for m in metas:
        defs = m.relevant_definitions(start, end)
        lines.append(f"**{m.area_label} ({m.area_code})** — source: {m.source_ref or 'n/a'}.")
        if defs:
            for d in defs:
                span = (
                    f"from {d.start.date()}"
                    + (f" to {d.end.date()}" if d.end is not None else " onwards")
                    if d.start is not None
                    else "(undated)"
                )
                lines.append(f"  - {span}: {d.text}")
        elif m.compilation:
            lines.append(f"  - {m.compilation}")
        if m.supp_info:
            lines.append(f"  - Note: {m.supp_info}")
        lines.append("")
    return "\n".join(lines).rstrip()


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
    metas: list | None = None,
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
            _series_notes(metas or [], start, end),
            "",
            _provenance_footer(provenance),
            "",
        ]
    )
    path.write_text(body)
    return path
