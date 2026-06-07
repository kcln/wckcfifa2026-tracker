# SESSION_NOTES — wckcfifa2026-tracker

_Last updated: 2026-06-06_

## What this is
A cloud-scheduled tracker for the 2026 FIFA World Cup (Jun 11 – Jul 19). Every 15 min on
GitHub Actions it fetches results, predicts matches (ML, Elo fallback), simulates the
bracket + title odds (Monte Carlo), pushes briefs to Telegram, and rebuilds a Bauhaus
GitHub Pages archive. Port of ipl-tracker; scheduler moved from launchd to GitHub Actions
so it needs no local machine.

## Status: BUILD COMPLETE (v1 + v2), merged to `main`. Not yet deployed.
- 80 tests passing: `./venv/bin/pytest -q` (67 live) and `ml/.venv/bin/python -m pytest ml/tests -q` (13 ml).
- 24 task commits on `main`. Branches `build-v1`, `ml-engine` are ff-merged (safe to delete).

## What was built
- **v1 (Tasks 0–12):** state, fixtures (real final 104-match draw, web-verified), data_fetcher
  (tiered ESPN→cache, reconciles by team+date), predictor (Elo + form, real eloratings.net),
  bracket_sim (group tables, best-thirds, Monte Carlo), message_builder, telegram_sender,
  html_archive (Bauhaus, screenshot-verified), tracker (idempotent, exit codes), smoke test,
  GitHub Actions workflow, README.
- **v2 (Tasks 13–17):** `ml/` engine — ingest 49k international matches, PIT-safe Elo+form
  features, LightGBM 3-class + isotonic calibration (0.597 acc / 0.883 logloss, beats Elo's
  0.906), backtest, and a precomputed `predictions.json` the live bridge reads stdlib-only.

## Decisions worth remembering
- Local venvs MUST be Python 3.13 (`/opt/homebrew/bin/python3.13`). System python3 is 3.9
  and lacks numpy 2.1.3 wheels / diverges from CI. (`ml/.venv` is separate, has pandas/sklearn/lightgbm.)
- ML predictions are precomputed (static pre-tournament team state) → live runtime + CI stay
  lean (no ML deps). Bridge degrades to Elo on any failure.
- Bugs fixed mid-build: venv-on-3.9, and parse_espn not emitting team names/date (live results
  would never have reconciled).
- v1 simplification: third-place→R32 knockout assignment is approximate (group winners/runners-up exact).

## NEXT — go live (needs KCL's GitHub auth + Telegram bot; cannot be done by Claude)
1. `gh repo create kcln/wckcfifa2026-tracker --public --source=. --remote=origin --push`
2. Repo Settings → Pages → source = `main` branch, folder = `/docs`.
3. Repo Settings → Secrets and variables → Actions → add `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_IDS` (comma-separated), optional `FOOTBALL_DATA_KEY`.
4. Actions tab → wc2026-tracker → Run workflow (or wait for the 15-min cron).
5. Verify the Pages URL renders and a Telegram message arrives.

## Retrain the model later
`ml/.venv/bin/python -m ml.src.train` then `ml/.venv/bin/python -m ml.src.predict`
(regenerates model.pkl + team_state.json + predictions.json), then commit those artifacts.

## Run locally
- Tests: `./venv/bin/pytest -q`
- Smoke (no send/push): `./venv/bin/python scripts/smoke_test.py`
- One real run: `./venv/bin/python -m src.tracker` (writes state.json + docs/index.html)
