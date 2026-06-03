"""bis-prates — command-line interface

Three subcommands wired as stubs: fetch -> transform -> report.
"""

import click
import requests


@click.group()
@click.version_option(package_name="bis-prates")
def cli() -> None:
    """BIS Policy Rate Monitor — fetch, tidy, and report central bank policy rates."""


@cli.command()
@click.option("--force", is_flag=True, help="Re-download even if a cached copy exists.")
@click.option(
    "--data-dir",
    default="data",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Where to cache the download and extract the CSV.",
)
@click.option("--no-verify", is_flag=True, help="Skip the SDMX dataflow confirmation.")
def fetch(force: bool, data_dir: str, no_verify: bool) -> None:
    """Download + cache the latest policy-rates CSV from the BIS Data Portal."""
    from . import fetch as fetch_mod

    try:
        prov = fetch_mod.fetch(data_dir, force=force, verify=not no_verify)
    except requests.RequestException as exc:
        raise click.ClickException(f"download failed: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"[bis-prates] fetched {prov.dataflow_id} v{prov.version} — {prov.dataflow_name}"
    )
    click.echo(f"  source       : {prov.source_url}")
    click.echo(f"  last-modified: {prov.last_modified}")
    click.echo(f"  size         : {prov.content_length} bytes")
    click.echo(f"  sha256       : {prov.sha256}")
    click.echo(f"  csv          : {prov.csv_path}")


@cli.command()
@click.option(
    "--csv",
    "csv_path",
    default="data/WS_CBPOL_csv_flat.csv",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Extracted CBPOL CSV to parse (run `fetch` first).",
)
@click.option(
    "--keep-missing",
    is_flag=True,
    help="Keep rows with no observation (OBS_STATUS=M).",
)
def transform(csv_path: str, keep_missing: bool) -> None:
    """Parse and tidy the cached CSV into a clean long dataset."""
    from pathlib import Path

    from . import parse as parse_mod

    if not Path(csv_path).exists():
        raise click.ClickException(f"CSV not found: {csv_path} — run `bis-prates fetch` first")

    df = parse_mod.parse(csv_path, drop_missing=not keep_missing)

    # Summary only for now; the snapshot/report stages consume the tidy frame next.
    click.echo(f"[bis-prates] parsed {csv_path}")
    click.echo(f"  rows   : {len(df):,}")
    click.echo(f"  areas  : {df['area_code'].nunique()}")
    click.echo(f"  freqs  : {sorted(df['freq_code'].unique())}")
    click.echo(f"  dates  : {df['date'].min().date()} -> {df['date'].max().date()}")
    click.echo(f"  columns: {list(df.columns)}")


@cli.command()
@click.option(
    "--countries",
    default="US,XM,GB,JP,CH",
    show_default=True,
    help="Comma-separated REF_AREA codes (euro area is XM, not EA).",
)
@click.option(
    "--start",
    default=None,
    help="Earliest date to include in the chart window, YYYY-MM-DD.",
)
@click.option(
    "--csv",
    "csv_path",
    default="data/WS_CBPOL_csv_flat.csv",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Extracted CBPOL CSV to read (run `fetch` first).",
)
def report(countries: str, start: str | None, csv_path: str) -> None:
    """Generate the snapshot report (summary + chart) for the given countries."""
    from pathlib import Path

    import pandas as pd

    from . import parse as parse_mod
    from . import transform as transform_mod
    from .codelists import resolve

    if not Path(csv_path).exists():
        raise click.ClickException(f"CSV not found: {csv_path} — run `bis-prates fetch` first")

    df = parse_mod.parse(csv_path)

    # Resolve requested codes (EA -> XM) and validate against codes present in the data.
    res = resolve(countries.split(","), set(df["area_code"]))
    for code in res.unknown:
        hint = ", ".join(res.suggestions.get(code) or []) or "no close match"
        click.echo(f"  ! unknown code {code!r} (did you mean: {hint})", err=True)
    if not res.resolved:
        raise click.ClickException("no valid countries to report")

    snap = transform_mod.snapshot(df, res.resolved)
    series = transform_mod.select_series(df, res.resolved, start=start)

    click.echo(f"[bis-prates] snapshot for {', '.join(res.resolved)}")
    for _, r in snap.iterrows():
        change = "n/a" if pd.isna(r["change"]) else f"{r['change']:+.3f}"
        click.echo(
            f"  {r['area_code']} {r['area_label']:<16} {r['value']:>7.3f}%  "
            f"(as of {r['date'].date()}; last move {change} on "
            f"{r['last_change_date'].date()}, {r['direction']})"
        )
    window = f" from {start}" if start else ""
    click.echo(f"  chart series{window}: {len(series):,} observations")


if __name__ == "__main__":
    cli()
