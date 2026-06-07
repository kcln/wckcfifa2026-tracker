"""Ingest layer for the international football results dataset.

Source: martj42/international_results (CSV of every international match,
~1872-present). This is the training data for the 3-class match predictor
(home win / draw / away win) that sits behind ``src/ml_predictor.py``.

Kept isolated in ``ml/`` with its own venv so the live tracker runtime never
pulls in pandas/sklearn/lightgbm.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import pandas as pd

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"

# <repo>/ml/data/historical/results.csv  (this file lives at <repo>/ml/src/ingest.py)
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "historical" / "results.csv"

# Tidy column order; remaining columns (city, country) are kept after these.
_LEAD_COLS = ["date", "home_team", "away_team", "home_score", "away_score", "neutral"]


def download(dest: Path | str = DATA_PATH, url: str = RESULTS_URL) -> Path:
    """Download the raw results CSV to ``dest`` if not already present.

    Uses urllib (stdlib) to avoid adding a dependency to the ml env.
    Returns the path to the file.
    """
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return dest


def load_results(path: Path | str = DATA_PATH) -> pd.DataFrame:
    """Read the results CSV into a tidy, typed DataFrame.

    - parses ``date`` as datetime
    - coerces scores to numeric and drops rows missing either score
    - casts scores to int
    - normalises ``neutral`` to a real bool
    - reorders columns to lead with the canonical predictor fields, keeping
      ``tournament`` (and any remaining columns) afterwards
    """
    df = pd.read_csv(path)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
    df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)

    df["neutral"] = _to_bool(df["neutral"])

    remaining = [c for c in df.columns if c not in _LEAD_COLS]
    df = df[_LEAD_COLS + remaining].reset_index(drop=True)
    return df


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a column of True/False/"True"/"False"/0/1 to a real bool Series."""
    if series.dtype == bool:
        return series
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .map({"true": True, "false": False, "1": True, "0": False})
        .fillna(False)
        .astype(bool)
    )


if __name__ == "__main__":
    p = download()
    frame = load_results(p)
    print(f"file: {p}")
    print(f"rows: {len(frame):,}")
    print(f"date range: {frame['date'].min().date()} -> {frame['date'].max().date()}")
