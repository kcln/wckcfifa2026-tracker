"""Honest forward backtest: ML model vs the live Elo heuristic baseline.

Both predictors are scored on the SAME held-out, most-recent chronological
slice of the historical data. The Elo baseline reuses the live
``src/predictor.py`` math (the same heuristic the tracker ships) so the
comparison answers the real question: does the calibrated ML model beat the
thing it is replacing?

The fiddly bit is the log-loss column alignment: ``log_loss`` needs the
per-class probability matrix in a fixed class order, so both the ML
``predict_proba`` output and the heuristic's ``{home, draw, away}`` dict are
projected onto ``model.classes_`` before scoring.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, log_loss

# Make the repo root importable so ``from src import predictor`` resolves
# (predictor is numpy-free stdlib math, safe to import in the ml venv).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.src import features, ingest
from ml.src.predict import _model
from ml.src.train import FEATURES
from src import predictor  # noqa: E402


def backtest(test_fraction: float = 0.2) -> dict:
    """Score the ML model and the Elo heuristic on the most-recent test slice.

    Returns ``{"ml": {accuracy, logloss}, "elo": {accuracy, logloss}, "n_test"}``.
    """
    raw = ingest.load_results()
    feat = features.build(raw)
    ordered = feat.sort_values("date", kind="stable").reset_index(drop=True)

    n_rows = len(ordered)
    n_test = max(1, int(round(n_rows * test_fraction)))
    test_df = ordered.iloc[n_rows - n_test:]

    y_true = test_df["outcome"].tolist()

    model = _model()
    classes = list(model.classes_)  # e.g. ["away", "draw", "home"]

    # --- ML model ---
    X = test_df[FEATURES].to_numpy(dtype=float)
    ml_proba = model.predict_proba(X)
    ml_pred = [classes[i] for i in ml_proba.argmax(axis=1)]
    ml_acc = float(accuracy_score(y_true, ml_pred))
    ml_ll = float(log_loss(y_true, ml_proba, labels=classes))

    # --- Elo heuristic baseline (live src/predictor.py) ---
    elo_proba = np.empty((n_test, len(classes)), dtype=float)
    elo_pred: list[str] = []
    for i, row in enumerate(test_df.itertuples(index=False)):
        p = predictor.predict(float(row.elo_home), float(row.elo_away), bool(row.neutral))
        elo_proba[i] = [p[cls] for cls in classes]  # align to model class order
        elo_pred.append(max(p, key=p.get))
    elo_acc = float(accuracy_score(y_true, elo_pred))
    elo_ll = float(log_loss(y_true, elo_proba, labels=classes))

    return {
        "ml": {"accuracy": ml_acc, "logloss": ml_ll},
        "elo": {"accuracy": elo_acc, "logloss": elo_ll},
        "n_test": int(n_test),
    }


if __name__ == "__main__":
    res = backtest()
    print(f"Backtest on most-recent {res['n_test']:,} matches\n")
    print(f"{'model':<8}{'accuracy':>12}{'logloss':>12}")
    print("-" * 32)
    for name in ("ml", "elo"):
        r = res[name]
        print(f"{name:<8}{r['accuracy']:>12.4f}{r['logloss']:>12.4f}")
    print()
    acc_d = res["ml"]["accuracy"] - res["elo"]["accuracy"]
    ll_d = res["elo"]["logloss"] - res["ml"]["logloss"]
    print(f"ML vs Elo: accuracy {acc_d:+.4f}, logloss improvement {ll_d:+.4f} (positive = ML better)")
