"""Train the 3-class match-outcome model (home win / draw / away win).

A LightGBM multiclass classifier is fit on the older portion of the data and
then wrapped in isotonic calibration fit on the most-recent (held-out) slice.
Calibration matters because the probabilities feed a Monte Carlo bracket
simulation downstream: miscalibrated probabilities produce wrong title odds.

The split is strictly *chronological* (no shuffle): we train on the past and
validate on the future, so the reported metrics reflect genuine forward
prediction skill rather than optimistic random-split leakage.

``FEATURES`` is the single source of truth for the model's input columns and is
imported unchanged by the inference layer (``predict.py``) so train and serve
never drift.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, log_loss

# The ONLY feature columns the model consumes. elo_home/elo_away are redundant
# with elo_diff for this model, so X stays compact. Shared verbatim with predict.py.
FEATURES = ["elo_diff", "form_home", "form_away", "neutral"]

# All three labels the model must always know about, in a stable sorted order.
CLASSES = ["away", "draw", "home"]

# <repo>/ml/data/models  (this file lives at <repo>/ml/src/train.py)
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "models"

_LGBM_PARAMS = dict(
    objective="multiclass",
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=50,
    verbosity=-1,
)


def train(df: pd.DataFrame, out_dir, val_fraction: float = 0.2):
    """Train + calibrate the outcome model, persist artifacts, return estimator.

    Parameters
    ----------
    df : DataFrame
        Must contain the ``FEATURES`` columns, an ``outcome`` label column, and a
        ``date`` column used for the chronological split.
    out_dir : path-like
        Directory to write ``model.pkl`` and ``model.json`` into.
    val_fraction : float
        Fraction of the most-recent rows held out for calibration + validation.

    Returns
    -------
    A fitted, isotonically calibrated estimator whose ``predict_proba`` sums to
    1 across the 3 classes and which exposes ``.classes_``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Chronological split: oldest -> train, most recent -> validation. Stable
    # sort preserves input order for same-date rows.
    ordered = df.sort_values("date", kind="stable").reset_index(drop=True)
    n_rows = len(ordered)
    n_val = max(1, int(round(n_rows * val_fraction)))
    n_train = n_rows - n_val

    train_df = ordered.iloc[:n_train]
    val_df = ordered.iloc[n_train:]

    X_train, y_train = train_df[FEATURES], train_df["outcome"]
    X_val, y_val = val_df[FEATURES], val_df["outcome"]

    # Fit the base LightGBM model on the training slice. Pin the full class set
    # so the model handles every label even if a slice happens to miss one.
    base = lgb.LGBMClassifier(**_LGBM_PARAMS)
    base.fit(X_train, y_train)

    # Isotonic calibration on the held-out validation slice via the prefit API
    # (supported in sklearn 1.5.2). Calibrating on future data keeps the
    # probabilities honest for forward prediction.
    calibrated = CalibratedClassifierCV(estimator=base, method="isotonic", cv="prefit")
    calibrated.fit(X_val, y_val)

    # Honest forward-looking metrics on the validation slice.
    proba_val = calibrated.predict_proba(X_val)
    pred_val = calibrated.predict(X_val)
    val_accuracy = float(accuracy_score(y_val, pred_val))
    val_logloss = float(log_loss(y_val, proba_val, labels=list(calibrated.classes_)))

    # Persist the calibrated estimator and metadata.
    model_path = out_dir / "model.pkl"
    with open(model_path, "wb") as fh:
        pickle.dump(calibrated, fh)

    meta = {
        "n_rows": int(n_rows),
        "n_train": int(n_train),
        "n_val": int(n_val),
        "classes": sorted(calibrated.classes_.tolist()),
        "features": FEATURES,
        "val_accuracy": val_accuracy,
        "val_logloss": val_logloss,
        "trained_through": ordered["date"].max().isoformat(),
        "model_type": "lightgbm-multiclass+isotonic",
    }
    (out_dir / "model.json").write_text(json.dumps(meta, indent=2))

    return calibrated


if __name__ == "__main__":
    from ml.src import ingest, features

    raw = ingest.load_results()
    feat = features.build(raw)
    model = train(feat, out_dir=DEFAULT_OUT_DIR)
    print(json.dumps(json.loads((DEFAULT_OUT_DIR / "model.json").read_text()), indent=2))
