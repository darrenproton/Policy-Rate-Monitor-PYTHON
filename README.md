# BIS Policy Rate Monitor (Python)

A small command-line tool that downloads the BIS *Central bank policy rates* dataset, tidies it,
and produces a latest-snapshot report (with one chart) for a chosen set of countries.

> 🚧 Work in progress. This README describes the intended interface — the target to build against.

## Install

```bash
cd PYTHON
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This exposes the `bis-prates` command.

## Usage

The tool has three steps: **fetch → transform → report**.

```bash
# 1) Download + cache the latest policy-rates CSV from the BIS Data Portal
bis-prates fetch

# 2) Parse and tidy the cached data
bis-prates transform

# 3) Generate the report for a set of countries
bis-prates report --countries "US,XM,GB,JP,CH" --start "2015-01-01"
```

### Options

| Option | Applies to | Description |
|--------|-----------|-------------|
| `--countries` | `report` | Comma-separated REF_AREA codes. **Euro area is `XM`** (not `EA`). |
| `--start` | `report` | Earliest date to include, `YYYY-MM-DD`. |
| `--force` | `fetch` | Re-download even if a cached copy exists. |
| `--help` | all | Show help. |

## Outputs

Written to `out/`:

| File | Contents |
|------|----------|
| `out/summary.csv` | Latest snapshot per country (rate, last change, date) + attributes. |
| `out/summary.json` | Same snapshot as JSON. |
| `out/policy_rates.png` | Policy-rate time series chart for the selected countries. |
| `out/report.md` | Short report: snapshot table, the chart, and data provenance. |

Snapshot rows are enriched with the series attributes (decimals, unit of measure, unit
multiplier, series title).

## Data source

BIS Data Portal — *Central bank policy rates*, bulk flat CSV:
<https://data.bis.org/static/bulk/WS_CBPOL_csv_flat.zip> (topic page:
<https://data.bis.org/topics/CBPOL>). Downloaded files are cached in `data/` (gitignored).

## Development

```bash
pytest        # run the unit tests (parsing, change calculation, dedupe)
```

## AI usage note

_TODO
