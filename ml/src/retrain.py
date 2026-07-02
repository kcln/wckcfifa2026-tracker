"""Nightly self-learning retrain with a backtest gate.

Pipeline (run by .github/workflows/retrain.yml, or manually):

  1. Historical results + THIS tournament's played matches (from state.json,
     knockout names resolved) are combined and deduped.
  2. The feature pass runs over the combined timeline, so Elo / form / rest
     now include tournament results — the model literally learns from every
     match played so far.
  3. A fresh LightGBM + isotonic model is trained into a STAGING directory.
  4. GATE: the staged model's log-loss on the tournament matches played so far
     is compared against the FROZEN published predictions (predictions.json —
     exactly what the tracker has been serving). Only if the retrain scores
     better do we promote.
  5. On promotion: model artifacts, a fresh team_state.json (final running
     state INCLUDING the newest results), and a regenerated predictions.json
     (rest-days aware for teams with a known next fixture) are written.

Metrics for every run — pass or fail — land in retrain_metrics.json.

Honesty note: the gate matches fall inside the training timeline (its most
recent slice, used for calibration), so the gate is a sanity floor against
regressions, not an out-of-sample proof of skill. The model.json val metrics
remain the honest forward numbers.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.src import features, ingest, tournament, train  # noqa: E402
from ml.src import predict  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parents[1] / "data" / "models"
STAGING_DIR = MODELS_DIR / "staging"
METRICS_PATH = MODELS_DIR / "retrain_metrics.json"

_KEY = ["date", "home_team", "away_team"]


def combined_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(combined, tournament_rows): history + this tournament, deduped on
    (date, home, away) — historical rows win so a dataset that eventually
    includes WC 2026 doesn't double-count."""
    ingest.download()
    hist = ingest.load_results()
    tourn = tournament.tournament_frame()
    if tourn.empty:
        return hist, tourn
    combined = pd.concat([hist, tourn], ignore_index=True)
    combined = combined.drop_duplicates(subset=_KEY, keep="first")
    return combined, tourn


def _frozen_logloss(rows: pd.DataFrame, classes: list) -> tuple[float, pd.DataFrame]:
    """Log-loss of the currently PUBLISHED predictions on the given tournament
    feature rows. Rows without a published pair are dropped (and the returned
    frame is the kept subset, so both models score the same matches)."""
    published = json.loads((MODELS_DIR / "predictions.json").read_text())
    probs, mask = [], []
    for row in rows.itertuples(index=False):
        p = published.get(f"{row.home_team}|{row.away_team}")
        mask.append(bool(p))
        if p:
            probs.append([p[c] for c in classes])
    kept_rows = rows.loc[mask].reset_index(drop=True)
    ll = float(log_loss(kept_rows["outcome"].tolist(),
                        np.array(probs), labels=classes))
    return ll, kept_rows


def run() -> dict:
    combined, tourn = combined_frame()
    if tourn.empty:
        print("no tournament results yet — nothing to learn from")
        return {"gate_passed": False, "reason": "no tournament matches"}

    feat = features.build(combined)

    # Train into staging so a failed gate never touches published artifacts.
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    model = train.train(feat, out_dir=STAGING_DIR)
    classes = list(model.classes_)

    # Tournament feature rows = the gate set.
    gate = feat.merge(tourn[_KEY].drop_duplicates(), on=_KEY, how="inner")

    frozen_ll, kept = _frozen_logloss(gate, classes)
    X = kept[train.FEATURES].to_numpy(dtype=float)
    new_ll = float(log_loss(kept["outcome"].tolist(),
                            model.predict_proba(X), labels=classes))

    passed = new_ll < frozen_ll
    metrics = {
        "run_date": str(_date.today()),
        "n_tournament_matches": int(len(tourn)),
        "n_gate": int(len(kept)),
        "frozen_logloss": round(frozen_ll, 5),
        "retrained_logloss": round(new_ll, 5),
        "gate_passed": bool(passed),
        "features": train.FEATURES,
    }

    if passed:
        # Promote: model artifacts, then state + predictions FROM the promoted
        # model (build_team_state clears predict's caches).
        shutil.copy2(STAGING_DIR / "model.pkl", MODELS_DIR / "model.pkl")
        shutil.copy2(STAGING_DIR / "model.json", MODELS_DIR / "model.json")
        predict._model.cache_clear()
        predict._model_features.cache_clear()

        state = predict.build_team_state(df=combined)

        # Rest days for teams with a known next fixture (live bracket dates).
        rest: dict = {}
        for team, iso in tournament.next_fixture_dates().items():
            last = (state.get(team) or {}).get("last_date")
            if iso and last:
                gap = (_date.fromisoformat(iso) - _date.fromisoformat(last)).days
                rest[team] = float(min(max(gap, 0), features.REST_CAP))
        predict.export_predictions(predict._world_cup_teams(),
                                   rest_by_team=rest)
        metrics["promoted"] = True
        metrics["rest_teams"] = len(rest)
    else:
        metrics["promoted"] = False

    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    run()
