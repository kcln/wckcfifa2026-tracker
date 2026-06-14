# SESSION_NOTES — wckcfifa2026-tracker

_Last updated: 2026-06-09_

## What this is
A cloud-scheduled tracker for the 2026 FIFA World Cup (Jun 11 – Jul 19). Every 15 min on
GitHub Actions it fetches results, predicts matches (ML, Elo fallback), simulates the
bracket + title odds (Monte Carlo), pushes briefs to Telegram, and rebuilds a Bauhaus
GitHub Pages archive. Port of ipl-tracker; scheduler moved from launchd to GitHub Actions
so it needs no local machine.

## Status: LIVE since 2026-06-09. Repo `kcln/wckcfifa2026-tracker`, Pages + Actions cron active.
- Pages: https://kcln.github.io/wckcfifa2026-tracker/ (HTTP 200, renders).
- Secrets set: `TELEGRAM_BOT_TOKEN` (reused IPL bot), `TELEGRAM_CHAT_IDS` = KC only (391401564).
  Ankit (8954471490) intentionally NOT added — KC's call later; update the secret to add him.
- First manual workflow run 2026-06-10T01:59Z: success, exit 0, results commit pushed.
- `FOOTBALL_DATA_KEY` not set (optional tier).
- Go-live snags: gh token needed `workflow` scope (`gh auth refresh -s workflow`), and
  secrets had to be set by KC directly (permission classifier blocked Claude).
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

## Design (2026-06-09, post go-live)
KC rejected the original Bauhaus archive page — the Pages site must replicate the
**ipl-tracker committed design exactly**: purple "Every match. Every prediction."
hero, most-recent + leader cards, collapsible match-day log, Telegram CTA
(@Kipl26bot — NO sign-up form; the form was replaced by the Telegram CTA in IPL's
committed page), lion mark, local-time script. `src/html_archive.py` now embeds
IPL's committed inline CSS/script verbatim; data bindings adapted to soccer.
Tracker stores `state["last_result"]` for the hero card. `docs/style.css` is now
unused (page inlines all CSS, like IPL) but left in place.
NOTE: do NOT apply the KCL Bauhaus brand to this site — explicit KC override.

## Messaging changes (2026-06-09 late)
- Cron tightened `*/15` → `*/5` (free on public repo; concurrency guard was already in place).
- NEW `half_time` message per live match at the break: `parse_espn` emits `HT` entries on
  `STATUS_HALFTIME` with the frozen break score; deduped by body hash across ticks;
  `merge_results` still records FT only so an HT score can never become a result.
- Sender rewritten: `_send_pending` flushes ALL undelivered oldest-first (was newest-only
  with stale-skip — KC: "no misses"). On failure it stops; the rest retries next run.
- Telegram opt-in invite sent to Ankit via @Kipl26bot (msg 156); he gets added to
  TELEGRAM_CHAT_IDS only after replying YES. Session watcher polls getUpdates.

## Incident (2026-06-12): missed Canada vs Bosnia messages
ESPN names the team `Bosnia-Herzegovina`; the seed says `Bosnia & Herzegovina`.
`_norm` compared raw lowercase strings -> reconcile silently dropped the match ->
no half-time, no result, recap stalled. FIX: `_norm` now strips diacritics (NFKD)
plus all non-alphanumerics before alias lookup (aliases re-keyed to squashed
forms; explicit `bosniaandherzegovina` alias since squash can't unify & with
'and'). The stale-code live run was cancelled so the queued run picks up the fix.
Half-time for that match is permanently missed; the result sends on the next run.

## Feature (2026-06-13): goal scorers + red cards in messages
Half-time, post-match, and daily-recap messages now list goal scorers (player,
country, minute) and red cards. Source = ESPN scoreboard's embedded
`competition.details` (no extra HTTP). `data_fetcher._events_from_details` keys
off the redCard/ownGoal/penaltyKick/scoringPlay flags (yellows + shootout
skipped); events ride through reconcile_results -> merge_results onto the match
result; `message_builder._event_lines` renders '⚽ 21' Scorer (Country)' /
'🟥 80' Player (Country)'. 119 tests. Format verified against the real
Brazil-Morocco feed.

## Incident+features (2026-06-14)
- BUG: ESPN 'Türkiye' (norm 'turkiye') vs seed 'Turkey' dropped Australia 2-0 Türkiye
  on June 13, which blocked the whole June-13 daily recap (gate required all 4 matches).
  KC noticed he got no end-of-day summary. FIX: turkiye->turkey alias; recap now also
  fires when the day is clock-complete (_day_clock_complete) and lists any unreconciled
  match under 'No result recorded:'. Backfilled June-13 (Australia result + recap) to KC.
- Welcome+catch-up sent to new signup Ashish Oberoi (chat 8957259477) via bot. He is NOT
  on the broadcast secret yet (pending the approval-flow redesign below).

## TODO (next build): signup approval + onboarding flow
KC's spec: when someone presses /start, bot DMs KC to APPROVE (buttons/command); on
approval the new member is added and gets a ONE-TIME onboarding choice asking (numbered):
  1. Today's match brief + summary of the day + updates till now
  2. Only match brief
  3. Only updates
  4. Only summary of the day
After that one-time catch-up, they go to regular programming (all future messages).
Constraint: GitHub Actions has no webhook -> approval is poll-latency (mins), not instant.
Subscriber list must move off the write-only secret (e.g. private gist) for auto-persist.
Bot currently has NO inbound handler (/start,/stop,approve) — that's the net-new module.

## Signup approval + onboarding flow SHIPPED (2026-06-14)
Built and deployed. New module `src/inbox.py` (poll getUpdates each cycle) + the
pipeline: /start -> pending + Approve/Decline DM to KC (APPROVER_CHAT_ID, default
391401564); KC taps Approve -> added + sent the 1-4 onboarding menu; member
replies 1-4 -> one-time catch-up (tracker.build_catchup from today's messages)
then onboarded; /stop -> unsubscribe. Subscriber list moved OFF the write-only
secret into committed `subscribers.json` (chat IDs only, names never persisted;
seeded from TELEGRAM_CHAT_IDS on first run). Broadcast now reads approved from
that file (tracker.process_inbox -> _build_cfg chat_ids). live_loop.git_sync +
workflow commit subscribers.json so approvals persist. Ashish + KC seeded as
approved+onboarded -> Ashish now activated WITHOUT the blocked secret command.
CONSTRAINT: poll-based (no webhook) so approval latency is minutes, not instant.
Privacy tradeoff: numeric chat IDs are visible in the public repo (acceptable per
KC); move to a private gist later if that changes. 135 tests pass.

## NEXT
- Add Ankit's chat ID (8954471490) to TELEGRAM_CHAT_IDS if/when he replies YES.
- Confirm a Telegram brief lands on KC's phone once the tournament starts (Jun 11).
- Optional: add Ankit's chat ID, set `FOOTBALL_DATA_KEY`, bump actions to Node 24
  (GitHub deprecation warning on checkout@v4 / setup-python@v5, forced June 16, 2026).

## Retrain the model later
`ml/.venv/bin/python -m ml.src.train` then `ml/.venv/bin/python -m ml.src.predict`
(regenerates model.pkl + team_state.json + predictions.json), then commit those artifacts.

## Run locally
- Tests: `./venv/bin/pytest -q`
- Smoke (no send/push): `./venv/bin/python scripts/smoke_test.py`
- One real run: `./venv/bin/python -m src.tracker` (writes state.json + docs/index.html)
