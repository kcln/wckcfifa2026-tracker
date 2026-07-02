# ML engine roadmap

## Shipped — self-learning loop (Jul 2026)

- **Nightly retrain** (`ml/src/retrain.py`, `.github/workflows/retrain.yml`,
  09:30 UTC): history + this tournament's played matches (knockout names
  resolved, true-home-aware `neutral`) → feature pass → LightGBM + isotonic →
  **backtest gate** — promoted only when the retrain beats the currently
  published `predictions.json` (log-loss) on the tournament matches so far.
  Metrics for every run land in `ml/data/models/retrain_metrics.json`.
- **Rest-days features** (`rest_home`/`rest_away`, capped at 30): computable
  across the full 49k-match history, so the fatigue/recovery effect is
  genuinely learned. At export, teams with a known next fixture get their real
  rest from the live bracket; others default to 4 days.
- **Fresh team state**: `team_state.json` now carries each team's state
  *including* its newest result (the old pass lagged one match) plus
  `last_date`.
- **No history rewriting**: the tracker freezes the published pick/probability
  for finished matches (`build_board(prior=...)`, `_accuracy(frozen=...)`), so
  a model retrained *on* a match can never retroactively claim it.

### Honesty notes
- The gate matches sit inside the retrain's own timeline (calibration slice),
  so the gate is a **regression floor**, not out-of-sample proof of skill. The
  chronological val metrics in `model.json` remain the honest forward numbers.
- Inference is all-neutral (`predictions.json` is pair-static); host
  advantage only enters via the Elo fallback. Acceptable while remaining hosts
  are few — revisit if a host reaches the semis.

## Tier 2 remainder — travel / altitude / venue

- The pieces that need **historically trainable** coverage to matter:
  - `travel_km`: distance between a team's consecutive match cities. Needs a
    geocode table for historical cities (thousands). Practical path: geocode
    only *tournament* cities per competition (World Cups, Euros, Copa, AFCON
    have compact venue sets) and let the feature be missing elsewhere —
    LightGBM handles missing natively.
  - `altitude_m`: small static table (Mexico City 2,240 m, Zapopan 1,566 m,
    Guadalupe ~540 m; all 2026 US/Canada venues < 400 m). Same
    tournament-cities-only coverage strategy.
- Skipped for now because a feature that is non-missing for only ~100 of 49k
  training rows cannot be learned (min_child_samples=50); shipping it would be
  decoration, not signal.

## Tier 3 — player-level data (next tournament)

- **FIFA ranking** as a team-strength feature: monthly rankings exist back to
  1992 (public datasets); merge as-of match date. Cheap, historically dense —
  the best first Tier-3 step.
- **Squad market value** (Transfermarkt) and **lineup/injury** data (FBref):
  real lift, but needs scraping + entity resolution, and lineups can't be
  retrofitted across the full history — the training signal only accumulates
  going forward. Build the ingest early in the next competition cycle.
- Design note: keep every source behind the same PIT rule — a feature must be
  computable strictly before kickoff (published lineups: yes, ~1h before;
  post-hoc ratings: never).
