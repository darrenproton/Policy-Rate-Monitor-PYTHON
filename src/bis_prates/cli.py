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
def transform() -> None:
    """Parse and tidy the cached CSV into a clean dataset."""
    # TODO: implement in bis_prates.parse / bis_prates.transform
    click.echo("[bis-prates] transform — not implemented yet")


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
    help="Earliest date to include, YYYY-MM-DD.",
)
def report(countries: str, start: str | None) -> None:
    """Generate the snapshot report (summary + chart) for the given countries."""
    # TODO: implement in bis_prates.report (uses bis_prates.codelists for EA->XM)
    click.echo(
        f"[bis-prates] report — not implemented yet "
        f"(countries={countries!r}, start={start!r})"
    )


if __name__ == "__main__":
    cli()
