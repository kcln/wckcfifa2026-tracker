# wckcfifa2026-tracker

Cloud-scheduled tracker for the 2026 FIFA World Cup — predictions, bracket simulation, Telegram alerts, and a GitHub Pages archive. No local machine required once deployed.

**Tournament window:** June 11 – July 19, 2026 (104 matches, 48 teams, 16 host cities across USA, Canada, Mexico).

---

## What it does

Every 15 minutes a GitHub Actions cron job runs the tracker:

1. **Fetches** fixtures and live results (tiered: ESPN soccer JSON → cache fallback).
2. **Predicts** each unplayed match using an Elo + form heuristic (ML engine is planned for phase 2; the tracker degrades gracefully to Elo when ML is absent).
3. **Simulates** group standings and the full knockout bracket with a Monte Carlo sweep, producing title-probability odds for every team.
4. **Generates briefs** — morning brief, post-match summaries, daily recaps, bracket updates, champion recap — as needed based on the current match state.
5. **Pushes the newest brief to Telegram** (supports multiple chat IDs; sends are idempotent so re-runs don't double-send).
6. **Rebuilds the GitHub Pages archive** (`docs/index.html`) in a Bauhaus-styled layout.
7. **Commits `state.json` and `docs/`** back to the repo so state persists across runs.

---

## Architecture

```
src/
  state.py          # load/save state.json; tracks sent briefs, last-seen results
  fixtures.py       # load and query data/fixtures.json (seeded draw, 104-match schedule)
  data_fetcher.py   # ESPN soccer JSON → parsed results; falls back to cached seed
  predictor.py      # Elo + home-advantage win-probability model
  ml_predictor.py   # bridge to ml/ engine (phase 2); currently returns None to trigger fallback
  bracket_sim.py    # group-stage standings + knockout bracket simulation; Monte Carlo title odds
  message_builder.py# formats morning brief, post-match, daily recap, bracket update, champion recap
  telegram_sender.py# multi-recipient Telegram delivery; respects rate limits
  html_archive.py   # Bauhaus-styled GitHub Pages renderer (docs/index.html)
  tracker.py        # orchestrator: wires all modules, decides what to run and send

data/
  fixtures.json     # final draw + full 104-match schedule (seeded; overwritten by live results)
  elo_seed.json     # team Elo ratings seed at tournament start

ml/                 # planned ML engine (phase 2) — not required for v1 operation
scripts/
  smoke_test.py     # end-to-end dry run (no Telegram send, no git push)
```

State is persisted in `state.json` at the repo root. The Pages archive lives in `docs/`.

---

## Setup

### 1. Create the GitHub repo

```bash
gh repo create kcln/wckcfifa2026-tracker --public --source=. --remote=origin --push
```

### 2. Enable GitHub Pages

Repo **Settings → Pages → Source**: set branch to `main`, folder to `/docs`. Save. The archive will be live at `https://kcln.github.io/wckcfifa2026-tracker/` after the first tracker run.

### 3. Add Actions secrets

**Settings → Secrets and variables → Actions → New repository secret** — add all three:

| Secret | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_IDS` | Comma-separated chat/channel IDs (e.g. `-100123456,789`) |
| `FOOTBALL_DATA_KEY` | (Optional) football-data.org API key for richer data |

### 4. Trigger the first run

Go to **Actions → wc2026-tracker → Run workflow** (workflow_dispatch), or wait for the next 15-minute cron tick. The first run seeds `state.json` and builds the initial Pages archive.

---

## Local development

Requires Python 3.13.

```bash
# Create venv and install deps
python3.13 -m venv venv
./venv/bin/pip install -r requirements.txt

# Run tests
./venv/bin/pytest -q

# Dry-run smoke test (no Telegram send, no git push)
./venv/bin/python scripts/smoke_test.py

# Run the tracker directly (needs secrets in env or .env)
python -m src.tracker
```

---

## How predictions work

Each match win-probability is computed from Elo ratings (seeded at `data/elo_seed.json`, then updated after each locked result) adjusted for a small home-advantage bonus for the three host nations. The group-stage standings and full knockout bracket are then simulated 10,000 times via Monte Carlo to produce title-probability odds for every remaining team. Odds sharpen as real match results lock in and propagate through the bracket.

The ML engine (`ml/`) is a phase-2 addition — when present it replaces the Elo heuristic with a trained model; when absent the tracker falls back to Elo automatically.

---

## Notes and limitations

- **GitHub cron lag**: Actions schedules can run 5–15 min late under load. This is fine for tracking 90-minute matches — runs are fully idempotent.
- **Knockout assignment (v1 simplification)**: group winners and runners-up are placed in the bracket exactly. The third-place → round-of-32 path is a v1 simplification and may not reflect the official seeding rules for all cases.
- **Team-name reconciliation**: the live feed normalizes team names via a small alias table in `data_fetcher.py`. Aliases may need additions once live tournament data starts flowing (some feeds use alternate country name spellings).
- **Local fallback**: a `launchd/` plist can run the tracker on a Mac instead of GitHub Actions if you prefer. Not required — Actions is the primary schedule.
- **Free-tier constraint**: keep the repo public so GitHub Pages stays free. Privatizing kills the Pages site on the free tier.
