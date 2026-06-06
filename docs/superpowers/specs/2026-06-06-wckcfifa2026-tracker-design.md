# wckcfifa2026-tracker — design

**Date:** 2026-06-06
**Status:** approved design, pre-implementation
**Owner:** KCL

## Summary

A cloud-scheduled tracker for the 2026 FIFA World Cup (June 11 – July 19, 2026,
USA / Canada / Mexico). On a recurring schedule it fetches fixtures and results,
predicts each day's matches with a trained ML model (Elo + form heuristic
fallback), simulates group standings and the knockout bracket / title odds,
archives every brief to a Bauhaus-styled GitHub Pages site, and notifies KCL on
Telegram. It is a direct port of the `ipl-tracker` pattern from cricket to
soccer, with the scheduler moved from macOS launchd to GitHub Actions so it does
not depend on a local machine being awake.

## Goals

- Live, hands-off coverage of the entire tournament with zero local dependency.
- Per-match win/draw/loss predictions during the group stage.
- Live group-standings projection and a knockout bracket / title-odds simulation.
- A public, branded archive of every brief and result.
- Telegram push for each new brief/result.
- Graceful degradation: the tracker is correct and publishable even if the ML
  model is unavailable or stale.

## Non-goals

- Player-level prop predictions or betting-market integration.
- Real-time per-minute live win-probability (post-match granularity only).
- iMessage delivery (Telegram + web only). A local launchd fallback is kept in
  the repo but is not the default.

## Tournament facts (encoded as fixed structure)

- 48 teams, 12 groups (A–L) of 4 teams, 104 matches total.
- The draw occurred Dec 5, 2025: all groups and the full 104-match schedule are
  already known and are seeded into the repo from openfootball; the live feed
  only fills in results.
- Advancement: top 2 of each group + the 8 best third-placed teams → 32-team
  knockout: Round of 32 → Round of 16 → Quarter-finals → Semi-finals →
  Third-place playoff → Final.
- Opener: June 11, 2026 (Estadio Azteca, Mexico City). Final: July 19, 2026
  (MetLife Stadium, NJ). Times handled in Pacific Time, like ipl-tracker.

## Architecture

Mirrors `ipl-tracker`: a bulletproof live tracker in `src/`, and a separate ML
engine in `ml/` with its own virtual environment. The ML path is wrapped behind
a bridge that catches every exception and falls back to the heuristic, so
nothing in the live path depends on ML for correctness.

```
wckcfifa2026-tracker/
├── .github/workflows/tracker.yml   GitHub Actions cron scheduler (primary)
├── src/                            live tracker — always runs, never depends on ml/
│   ├── data_fetcher.py             tiered fixtures/results source + cache
│   ├── predictor.py                Elo + form heuristic (always-works floor)
│   ├── ml_predictor.py             bridge to ml/; catches all → falls back to predictor
│   ├── bracket_sim.py              Monte Carlo group standings + knockout + title odds
│   ├── message_builder.py          morning brief / post-match / daily recap / bracket update
│   ├── telegram_sender.py          Telegram Bot API delivery
│   ├── html_archive.py             renders docs/index.html (Editorial × Bauhaus)
│   ├── state.py                    state.json load/save, timezone helpers
│   └── tracker.py                  main entry point
├── ml/                             prediction engine (isolated venv, like ipl ml/)
│   ├── ingest.py                   download + parse martj42/international_results
│   ├── features.py                 pre-match features (PIT-safe)
│   ├── train.py                    3-class W/D/L LightGBM + isotonic; Poisson goals
│   ├── predict.py                  inference API used by the bridge
│   └── backtest.py                 chronological replay vs Elo baseline
├── data/
│   ├── fixtures.json               seeded 104-match schedule + groups (from openfootball)
│   └── cache/                      fetched-feed cache (gitignored)
├── docs/
│   ├── index.html                  GitHub Pages archive
│   ├── style.css                   brand styles
│   └── superpowers/specs/          this design doc
├── launchd/                        optional local fallback (not default)
├── state.json                      days[], groups{}, bracket{}, season_ended
├── requirements.txt
└── README.md
```

### Data sources (tiered, first that succeeds wins)

1. **ESPN soccer JSON** — `site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard`
   (public, no key; same family as ipl-tracker's ESPN fallback). Primary for
   live scores/fixtures.
2. **football-data.org** — free tier with an API key (`FOOTBALL_DATA_KEY`),
   World Cup competition endpoint. Fallback.
3. **openfootball/world-cup** GitHub JSON — the seeded canonical schedule;
   floor source and the seed for `data/fixtures.json`.
4. **Local cache** — last good fetch, so a feed outage never breaks a run.

### Prediction engine (ML, with heuristic fallback)

- **Training data:** `martj42/international_results` — every international match
  ~1872–2026 (~48k rows), public CSV.
- **Features (point-in-time safe):** World-Football-Elo diff, FIFA-rank diff,
  recent form (last-N results), goals for/against, rest days, neutral/host flag,
  confederation, competitive-vs-friendly.
- **Models:** primary 3-class home/draw/away LightGBM with isotonic
  calibration; a parallel Poisson goals model produces scorelines that feed the
  Monte Carlo bracket sim.
- **Baseline / fallback:** World-Football-Elo + home advantage in
  `src/predictor.py`. The bridge `src/ml_predictor.py` returns ML probabilities
  when available and the Elo heuristic otherwise.
- **Validation:** `ml/backtest.py` replays chronologically and reports accuracy
  and Brier score vs the Elo baseline.

### Bracket simulation

`src/bracket_sim.py` runs Monte Carlo (default 10k iterations): plays remaining
group matches using model probabilities, computes final group tables and the 8
best third-placed teams per FIFA tiebreakers, seeds the knockout bracket, and
simulates through the final to produce advancement and title probabilities per
team. Completed matches are locked to their real results; only unplayed matches
are simulated.

## Per-run flow (each GitHub Actions trigger)

1. Checkout, set up Python, install `src/` requirements.
2. Fetch fixtures + results (tiered → cache).
3. Determine which message types are due-but-missing for today (PT).
4. Generate them: predictions via the ML bridge; re-sim bracket from current
   results.
5. Append to `docs/index.html`; record in `state.json`.
6. Send only the newest undelivered message via Telegram; mark older ones
   skipped (idempotent, matches ipl-tracker behavior).
7. Commit `state.json` + `docs/` with `GITHUB_TOKEN`; the push redeploys Pages.

### Message types

- **Morning brief** — once after 00:00 PT: today's matches with predictions.
- **Post-match** — once per completed match: result + whether prediction hit.
- **Daily recap** — once after the day's last match: results + updated group
  tables and who is advancing.
- **Bracket / title-odds update** — during the knockout stage: updated bracket
  and title probabilities.
- **Champion recap** — once after July 19, then the workflow self-disables.

## Scheduling (GitHub Actions, not launchd)

- `.github/workflows/tracker.yml`, `on: schedule:` cron every 15 minutes during
  the tournament window. Runs entirely on GitHub-hosted runners; no local
  machine required.
- Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, optional
  `FOOTBALL_DATA_KEY`) live in repo Actions secrets, never committed.
- Commit/push uses the built-in `GITHUB_TOKEN`; the push to `/docs` redeploys
  Pages.
- Known limitations, accepted: GitHub cron can lag 5–15 min under load (fine for
  90-minute matches; runs are idempotent and catch up). Scheduled workflows
  auto-disable after 60 days of repo inactivity, which never triggers because we
  push every run. After the final, the workflow disables itself.
- `launchd/` is retained as an optional local fallback, documented in the README
  but not the default path.

## State model (`state.json`)

```jsonc
{
  "days": [            // one entry per tournament day
    { "date": "2026-06-11",
      "messages": [ { "type": "...", "sent": true, "hash": "...", "body": "..." } ],
      "matches": [ { "id": "...", "home": "...", "away": "...",
                     "prediction": {...}, "result": {...} } ] }
  ],
  "groups": { "A": { "table": [...] }, "...": {} },
  "bracket": { "R32": [...], "R16": [...], "title_odds": {...} },
  "season_ended": false
}
```

## Brand / web archive

`docs/index.html` uses the locked Editorial × Bauhaus system: warm cream
background `#F5F1EB`, crimson `#E0001C` as the single hero accent, Playfair
Display Italic heroes, Inter body, JetBrains Mono labels, 2px ink borders with
4px hard offset shadows and 0 radius. The four spectrum colors (navy, teal,
amber, rose) map to the six confederations (grouped/abbreviated) as solid chip
and tag fills. Imports `brand.css` if present, else inlines the tokens.

## Error handling

- Every external call (feeds, Telegram, ML import) is wrapped; failures degrade,
  never crash the run.
- ML bridge returns `None` on any error → heuristic used.
- Feed failure → cache used.
- Telegram failure → message stays "undelivered" and retries next run; HTML/state
  still written.
- Exit codes mirror ipl-tracker: 0 success/no-op, 1 fatal, 2 partial.

## Testing

- Unit tests for: tiebreaker logic (group tables + best-third selection),
  bracket seeding, state idempotency (no duplicate sends), message dedup hashing.
- `ml/backtest.py` for model accuracy/Brier vs Elo baseline.
- A smoke test that runs the full tracker against cached/synthetic fixtures
  without sending Telegram or pushing.

## Phasing

1. **v1 — heuristic tracker, end-to-end (publish first).** Elo + form
   predictions, bracket sim, Telegram, GitHub Pages, GitHub Actions cron. Fully
   working and live before June 11.
2. **v2 — ML engine.** Train on `martj42/international_results`, backtest, wire
   behind the bridge. Pure upside; never blocks v1.

## Open questions

None at design time. Confirmed: draw is final (seed fixtures), phased scope
(heuristic first, ML second), scheduler is GitHub Actions.
