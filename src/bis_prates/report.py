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
    term_freq=None,
    *,
    out_dir: str | os.PathLike = "out",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Path]:
    """Write all four deliverables and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chart = _plot_series(series, out, metas or [], term_freq)
    return {
        "summary_csv": _write_summary_csv(snapshot, out),
        "summary_json": _write_summary_json(snapshot, out),
        "chart": chart,
        "report": _write_report_md(
            snapshot, provenance, chart, out, start, end, metas or [], term_freq
        ),
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


# Colour cycle for the speech-term lanes.
_TERM_PALETTE = plt.get_cmap("tab10").colors


def _plot_series(series: pd.DataFrame, out: Path, metas: list, term_freq=None) -> Path:
    path = out / "policy_rates.png"
    n_terms = 0 if term_freq is None or term_freq.empty else term_freq.shape[1]

    if n_terms:
        # Rates on top (taller), then one short lane per term, all sharing the time axis.
        fig, axes = plt.subplots(
            1 + n_terms,
            1,
            sharex=True,
            figsize=(9, 5 + 1.0 * n_terms),
            gridspec_kw={"height_ratios": [4] + [1] * n_terms},
        )
        ax_rates, term_axes = axes[0], list(axes[1:])
    else:
        fig, ax_rates = plt.subplots(figsize=(9, 5))
        term_axes = []

    colors: dict[str, str] = {}
    for code, grp in series.groupby("area_code"):
        label = grp["area_label"].iloc[0]
        # steps-post: the rate holds until the next change - the honest shape for this data.
        line = ax_rates.step(grp["date"], grp["value"], where="post", label=f"{label} ({code})")[0]
        colors[code] = line.get_color()

    _annotate_breaks(ax_rates, series, metas, colors)
    ax_rates.set_title("Central bank policy rates")
    ax_rates.set_ylabel("Per cent per year")
    ax_rates.grid(True, alpha=0.3)
    if not series.empty:
        ax_rates.legend(loc="best", fontsize=8)
        ax_rates.set_xlim(series["date"].min(), series["date"].max())

    if n_terms:
        _plot_term_lanes(term_axes, term_freq)
        term_axes[-1].set_xlabel("Date")
    else:
        ax_rates.set_xlabel("Date")

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _plot_term_lanes(term_axes: list, term_freq) -> None:
    """One colour-coded lane per term: monthly mention frequency, label in the left margin."""
    for i, term in enumerate(term_freq.columns):
        ax = term_axes[i]
        color = _TERM_PALETTE[i % len(_TERM_PALETTE)]
        ax.fill_between(
            term_freq.index, term_freq[term].to_numpy(), step="mid", color=color, alpha=0.7
        )
        ax.set_yticks([])
        ax.margins(y=0)
        # Term label sits in the left margin, well left of the data, colour-matched.
        ax.set_ylabel(
            term, rotation=0, ha="right", va="center", color=color, fontsize=9, labelpad=14
        )
        ax.label_outer()


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


def _speeches_section(term_freq) -> str:
    """Term-frequency summary: total mentions and peak month per term (the 'finding')."""
    if term_freq is None or term_freq.empty:
        return ""
    lines = [
        "## Central-bank speeches - term frequency",
        "",
        "Monthly whole-word mentions across BIS central-bank speeches (via gingado), aligned to",
        "the rate chart above. Compare the rhetoric tracks with the policy-rate moves.",
        "",
        "| Term | Total mentions | Peak month (count) |",
        "|---|---:|---|",
    ]
    for term in term_freq.columns:
        series = term_freq[term]
        peak = series.idxmax()
        lines.append(
            f"| {term} | {int(series.sum()):,} | {peak.strftime('%Y-%m')} ({int(series.max())}) |"
        )
    return "\n".join(lines)


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
    term_freq=None,
) -> Path:
    path = out / "report.md"
    window = _window_label(start, end)
    unit = snapshot["unit_measure"].iloc[0] if not snapshot.empty else ""
    sections = [
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
    ]
    speeches = _speeches_section(term_freq)
    if speeches:
        sections += [speeches, ""]
    sections += [_provenance_footer(provenance), ""]
    path.write_text("\n".join(sections))
    return path
