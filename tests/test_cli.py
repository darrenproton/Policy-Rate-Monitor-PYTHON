"""CLI tests via Click's CliRunner - exercise transform/report without the network."""
from __future__ import annotations

from click.testing import CliRunner

from bis_prates.cli import cli


def test_help_lists_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("fetch", "transform", "report"):
        assert cmd in result.output


def test_transform_prints_summary(sample_csv):
    result = CliRunner().invoke(cli, ["transform", "--csv", str(sample_csv)])
    assert result.exit_code == 0, result.output
    assert "parsed" in result.output
    assert "areas" in result.output


def test_report_writes_outputs(sample_csv, tmp_path):
    out = tmp_path / "out"
    result = CliRunner().invoke(
        cli, ["report", "--csv", str(sample_csv), "--countries", "US,GB", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "snapshot for" in result.output
    assert (out / "summary.csv").exists()
    assert (out / "report.md").exists()


def test_report_ea_alias_and_unknown(sample_csv, tmp_path):
    # EA -> XM (absent here) and a bad code both exercise the resolve/validate paths.
    result = CliRunner().invoke(
        cli,
        ["report", "--csv", str(sample_csv), "--countries", "US,EA,ZZ",
         "--out", str(tmp_path / "o")],
    )
    assert result.exit_code == 0, result.output
    assert "unknown code" in result.output  # ZZ rejected with a hint


def test_report_missing_csv_errors(tmp_path):
    result = CliRunner().invoke(cli, ["report", "--csv", str(tmp_path / "nope.csv")])
    assert result.exit_code != 0
    assert "CSV not found" in result.output
