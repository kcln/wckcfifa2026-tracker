"""Point-in-time (PIT) safe feature engineering for the match predictor.

The cardinal rule here is *no leakage*: every feature attached to a match must
be computable strictly from information available BEFORE that match kicks off.
We guarantee this with a single chronological pass that, for each match:

  1. reads the current running state (Elo, recent form) into the row,
  2. records the row (pre-match snapshot),
  3. THEN updates the running state with the actual result.

Because state is only ever updated *after* a row is recorded, no future
information can bleed into a past feature. The downstream trainer splits
chronologically (train on older, test on newer), so this ordering is what keeps
the backtest honest.

Elo follows the World-Football-Elo family also used by the live
``src/predictor.py`` heuristic (HOME_ADV=65), so the ML model is a calibrated
upgrade over that baseline rather than a different scoring universe.
"""
from __future__ import annotations

import pandas as pd

START_ELO = 1500.0
HOME_ADV = 65.0          # Elo points added to the home side (0 on neutral ground)
K = 30.0                 # Elo update step size
FORM_WINDOW = 5          # matches of recent form to average over
REST_CAP = 30.0          # days; longer layoffs (and debuts) clamp here — past a
                         # month the rested-vs-rusty signal saturates

# Columns carried through from the input frame to identify each match.
_ID_COLS = ["date", "home_team", "away_team", "home_score", "away_score", "neutral"]


def outcome_label(home_score: int, away_score: int) -> str:
    """Return the 3-class label for a match from its final score."""
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def expected_score(elo_a: float, elo_b: float) -> float:
    """Elo expected result for A vs B in [0, 1] (apply HOME_ADV before calling)."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def _points(home_score: int, away_score: int, *, for_home: bool) -> int:
    """Points (3/1/0) earned by the home or away side in a single match."""
    label = outcome_label(home_score, away_score)
    if label == "draw":
        return 1
    if (label == "home") == for_home:
        return 3
    return 0


def _form(recent: dict, team: str) -> float:
    """Points-per-game over a team's last FORM_WINDOW matches; 0 if none."""
    history = recent.get(team)
    if not history:
        return 0.0
    return sum(history) / len(history)


def _rest(last_played: dict, team: str, date) -> float:
    """Days since the team's previous match, clamped to REST_CAP (debuts and
    long layoffs read as fully rested). In a compressed tournament this is the
    fatigue/recovery signal: 3 days' rest vs 6 is a real difference."""
    prev = last_played.get(team)
    if prev is None:
        return REST_CAP
    days = (date - prev).days
    return float(min(max(days, 0), REST_CAP))


def build(df: pd.DataFrame, return_state: bool = False):
    """Build a PIT-safe feature matrix with a 3-class ``outcome`` label.

    Single stable-sorted chronological pass maintaining running Elo and recent
    form. Each row stores the PRE-match feature values; state is updated only
    after the row is recorded, so there is no leakage.

    With ``return_state=True`` also returns the FINAL running state after the
    last match — ``(frame, {"elo", "form", "last_played"})`` — which is what
    inference should use (each team's state *including* its newest result; the
    per-row pre-match snapshots lag one match by construction).
    """
    ordered = df.sort_values("date", kind="stable").reset_index(drop=True)

    elo: dict[str, float] = {}
    recent: dict[str, list[int]] = {}
    last_played: dict = {}                    # team -> date of last match
    rows: list[dict] = []

    for match in ordered.itertuples(index=False):
        home, away = match.home_team, match.away_team
        neutral = bool(match.neutral)

        elo_home = elo.get(home, START_ELO)
        elo_away = elo.get(away, START_ELO)

        form_home = _form(recent, home)
        form_away = _form(recent, away)

        rest_home = _rest(last_played, home, match.date)
        rest_away = _rest(last_played, away, match.date)

        rows.append({
            "date": match.date,
            "home_team": home,
            "away_team": away,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "neutral": int(neutral),
            "elo_home": elo_home,
            "elo_away": elo_away,
            "elo_diff": elo_home - elo_away,
            "form_home": form_home,
            "form_away": form_away,
            "rest_home": rest_home,
            "rest_away": rest_away,
            "outcome": outcome_label(match.home_score, match.away_score),
        })

        # --- update running state AFTER recording the pre-match row ---
        adj = 0.0 if neutral else HOME_ADV
        exp_home = expected_score(elo_home + adj, elo_away)
        if match.home_score > match.away_score:
            actual_home = 1.0
        elif match.home_score < match.away_score:
            actual_home = 0.0
        else:
            actual_home = 0.5

        delta = K * (actual_home - exp_home)
        elo[home] = elo_home + delta
        elo[away] = elo_away - delta

        recent.setdefault(home, []).append(_points(match.home_score, match.away_score, for_home=True))
        recent.setdefault(away, []).append(_points(match.home_score, match.away_score, for_home=False))
        recent[home][:] = recent[home][-FORM_WINDOW:]
        recent[away][:] = recent[away][-FORM_WINDOW:]
        last_played[home] = match.date
        last_played[away] = match.date

    frame = pd.DataFrame(rows)
    if return_state:
        state = {
            "elo": dict(elo),
            "form": {t: (sum(h) / len(h)) for t, h in recent.items() if h},
            "last_played": dict(last_played),
        }
        return frame, state
    return frame
