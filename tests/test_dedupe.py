"""Dedupe tests: collapse forward-filled runs to change-points, per series."""
from __future__ import annotations

from bis_prates.transform import change_points


def test_collapses_forward_filled_runs(make_tidy):
    df = make_tidy(
        [
            {"area_code": "US", "date": "2020-01-01", "value": 2.0},
            {"area_code": "US", "date": "2020-01-02", "value": 2.0},  # repeat -> dropped
            {"area_code": "US", "date": "2020-01-03", "value": 1.75},  # change
            {"area_code": "US", "date": "2020-01-04", "value": 1.75},  # repeat -> dropped
            {"area_code": "US", "date": "2020-01-05", "value": 2.0},  # change
        ]
    )
    cp = change_points(df)
    assert list(cp["date"].dt.day) == [1, 3, 5]
    assert list(cp["value"]) == [2.0, 1.75, 2.0]


def test_change_points_are_per_series(make_tidy):
    df = make_tidy(
        [
            {"area_code": "US", "date": "2020-01-01", "value": 1.0},
            {"area_code": "US", "date": "2020-01-02", "value": 1.0},
            {"area_code": "GB", "date": "2020-01-01", "value": 5.0},
            {"area_code": "GB", "date": "2020-01-02", "value": 5.5},
        ]
    )
    cp = change_points(df)
    # US collapses to one row; GB keeps both (a genuine move).
    assert len(cp[cp.area_code == "US"]) == 1
    assert len(cp[cp.area_code == "GB"]) == 2
