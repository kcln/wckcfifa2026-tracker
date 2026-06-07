# wckcfifa2026-tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cloud-scheduled (GitHub Actions) tracker that predicts every 2026 FIFA World Cup match, simulates the bracket and title odds, publishes a Bauhaus-styled archive to GitHub Pages, and pushes briefs to Telegram — with no dependency on a local machine.

**Architecture:** A bulletproof live tracker in `src/` (tiered data fetch → Elo+form predictions → Monte Carlo bracket sim → HTML/state → Telegram → git push), plus a later ML engine in `ml/` wrapped behind a fail-safe bridge that degrades to the heuristic. Scheduler is a GitHub Actions cron; commits use `GITHUB_TOKEN` and redeploy Pages. Phased: v1 (Tasks 0–12, heuristic, fully shippable before June 11) then v2 (Tasks 13–17, ML upside).

**Tech Stack:** Python 3.13, `requests`, `numpy`, `pytest`; LightGBM + pandas + scikit-learn for `ml/`; GitHub Actions; GitHub Pages; Telegram Bot API.

---

## File Structure

| File | Responsibility |
|---|---|
| `requirements.txt` | runtime deps for `src/` (requests, numpy) |
| `src/state.py` | state.json load/save; PT/UTC time helpers; message dedup hashing |
| `data/fixtures.json` | seeded 104-match schedule + 12 groups (from openfootball) |
| `src/fixtures.py` | load fixtures.json; merge live results onto seeded schedule |
| `src/data_fetcher.py` | tiered live fetch (ESPN → football-data → cache) |
| `src/predictor.py` | Elo + form heuristic; W/D/L probs + expected goals |
| `src/bracket_sim.py` | group tables, best-third tiebreak, knockout seeding, Monte Carlo |
| `src/ml_predictor.py` | bridge to `ml/`; catches all → returns None (v1 stub) |
| `src/message_builder.py` | morning brief / post-match / recap / bracket / champion text |
| `src/telegram_sender.py` | Telegram Bot API delivery |
| `src/html_archive.py` | render docs/index.html (Editorial × Bauhaus) |
| `src/tracker.py` | main entry: orchestrates a single run; exit codes |
| `scripts/smoke_test.py` | full run against cached/synthetic data, no send/push |
| `.github/workflows/tracker.yml` | cron scheduler |
| `docs/index.html`, `docs/style.css` | published archive |
| `ml/*` | v2 prediction engine (isolated venv) |

---

## Task 0: Project scaffold

**Files:**
- Create: `requirements.txt`, `src/__init__.py`, `tests/__init__.py`, `pytest.ini`, `README.md`, `.gitignore` (exists)

- [ ] **Step 1: Create requirements.txt**

```
requests==2.32.3
numpy==2.1.3
pytest==8.3.3
```

- [ ] **Step 2: Create package files and pytest config**

`src/__init__.py` and `tests/__init__.py` are empty. `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Create venv and install**

Run:
```bash
cd /Users/kcl/Desktop/wckcfifa2026-tracker
python3 -m venv venv && ./venv/bin/pip install -q -r requirements.txt
```
Expected: installs without error.

- [ ] **Step 4: Verify pytest runs**

Run: `./venv/bin/pytest -q`
Expected: "no tests ran" (exit 5) — confirms pytest is wired.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "scaffold: project structure, venv, pytest config"
```

---

## Task 1: state.py — persistence + time helpers

**Files:**
- Create: `src/state.py`, `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state.py
from datetime import datetime, timezone
from src import state

def test_message_hash_is_stable_and_type_aware():
    a = state.message_hash("morning_brief", "2026-06-11", "body text")
    b = state.message_hash("morning_brief", "2026-06-11", "body text")
    c = state.message_hash("morning_brief", "2026-06-11", "different")
    assert a == b and a != c

def test_load_missing_returns_empty_skeleton(tmp_path):
    s = state.load(tmp_path / "state.json")
    assert s == {"days": [], "groups": {}, "bracket": {}, "season_ended": False}

def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "state.json"
    data = {"days": [{"date": "2026-06-11"}], "groups": {}, "bracket": {}, "season_ended": False}
    state.save(p, data)
    assert state.load(p) == data

def test_today_pt_iso_format():
    fixed = datetime(2026, 6, 11, 6, 0, tzinfo=timezone.utc)  # 23:00 PT prev day
    assert state.today_pt_iso(now=fixed) == "2026-06-10"
```

- [ ] **Step 2: Run to verify fail**

Run: `./venv/bin/pytest tests/test_state.py -q`
Expected: FAIL (module/attrs missing).

- [ ] **Step 3: Implement src/state.py**

```python
"""state.json persistence and timezone helpers."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

PT = timezone(timedelta(hours=-7))  # tournament window is PDT
SKELETON = {"days": [], "groups": {}, "bracket": {}, "season_ended": False}

def message_hash(msg_type: str, date_iso: str, body: str) -> str:
    return hashlib.sha256(f"{msg_type}|{date_iso}|{body}".encode()).hexdigest()[:16]

def load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return json.loads(json.dumps(SKELETON))
    return json.loads(path.read_text())

def save(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))

def now_pt(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(PT)

def today_pt_iso(now: datetime | None = None) -> str:
    return now_pt(now).date().isoformat()
```

- [ ] **Step 4: Run to verify pass**

Run: `./venv/bin/pytest tests/test_state.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/state.py tests/test_state.py && git commit -m "feat: state persistence and PT time helpers"
```

---

## Task 2: Seed fixtures + fixtures loader

**Files:**
- Create: `data/fixtures.json`, `src/fixtures.py`, `tests/test_fixtures.py`

> The draw is final (Dec 5, 2025). Seed the real 12 groups (A–L) and 104-match schedule. Source the JSON from `github.com/openfootball/world-cup` (file: `2026--world-cup/...`) at implementation time; if unavailable, transcribe from fifa.com. The structure below is the contract; populate all 104 matches.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fixtures.py
from src import fixtures

def test_seed_has_48_teams_in_12_groups():
    f = fixtures.load_seed()
    assert len(f["groups"]) == 12
    teams = [t for g in f["groups"].values() for t in g]
    assert len(teams) == 48 and len(set(teams)) == 48

def test_seed_has_104_matches():
    f = fixtures.load_seed()
    assert len(f["matches"]) == 104

def test_every_match_has_required_fields():
    for m in fixtures.load_seed()["matches"]:
        assert {"id", "date", "home", "away", "stage"} <= set(m)

def test_merge_results_locks_completed_matches():
    seed = {"matches": [{"id": "m1", "home": "USA", "away": "MEX", "result": None}]}
    live = {"m1": {"home_goals": 2, "away_goals": 1, "status": "FT"}}
    merged = fixtures.merge_results(seed, live)
    assert merged["matches"][0]["result"]["home_goals"] == 2
```

- [ ] **Step 2: Run to verify fail**

Run: `./venv/bin/pytest tests/test_fixtures.py -q` → FAIL.

- [ ] **Step 3: Create data/fixtures.json**

Shape (populate all groups/matches from openfootball):
```jsonc
{
  "groups": { "A": ["Mexico", "...", "...", "..."], "B": [...], "...": [] },
  "matches": [
    { "id": "1", "date": "2026-06-11", "kickoff_utc": "2026-06-11T19:00:00Z",
      "home": "Mexico", "away": "TBD", "group": "A", "stage": "group",
      "venue": "Estadio Azteca", "result": null }
  ]
}
```

- [ ] **Step 4: Implement src/fixtures.py**

```python
"""Load the seeded schedule and merge live results onto it."""
from __future__ import annotations
import copy, json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "fixtures.json"

def load_seed(path: Path = SEED_PATH) -> dict:
    return json.loads(Path(path).read_text())

def merge_results(seed: dict, live: dict) -> dict:
    """live maps match id -> {home_goals, away_goals, status}. Completed only."""
    out = copy.deepcopy(seed)
    for m in out["matches"]:
        r = live.get(m["id"])
        if r and r.get("status") == "FT":
            m["result"] = {"home_goals": r["home_goals"], "away_goals": r["away_goals"]}
    return out
```

- [ ] **Step 5: Run to verify pass**

Run: `./venv/bin/pytest tests/test_fixtures.py -q`
Expected: 4 passed (after fixtures.json is fully populated).

- [ ] **Step 6: Commit**

```bash
git add data/fixtures.json src/fixtures.py tests/test_fixtures.py && git commit -m "feat: seed WC2026 groups + 104-match schedule and fixtures loader"
```

---

## Task 3: data_fetcher — tiered live fetch with cache

**Files:**
- Create: `src/data_fetcher.py`, `tests/test_data_fetcher.py`

- [ ] **Step 1: Write failing tests** (no network — inject fetch fns)

```python
# tests/test_data_fetcher.py
from src import data_fetcher as df

def test_parse_espn_scoreboard_extracts_completed_results():
    sample = {"events": [{"id": "1", "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2"}, {"homeAway": "away", "score": "1"}]}]}]}
    out = df.parse_espn(sample)
    assert out["1"] == {"home_goals": 2, "away_goals": 1, "status": "FT"}

def test_fetch_results_falls_back_to_cache_on_total_failure(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text('{"1": {"home_goals": 3, "away_goals": 0, "status": "FT"}}')
    out = df.fetch_results(sources=[lambda: (_ for _ in ()).throw(RuntimeError())],
                           cache_path=cache)
    assert out["1"]["home_goals"] == 3

def test_fetch_results_writes_cache_on_success(tmp_path):
    cache = tmp_path / "cache.json"
    good = {"1": {"home_goals": 1, "away_goals": 1, "status": "FT"}}
    out = df.fetch_results(sources=[lambda: good], cache_path=cache)
    assert out == good and cache.exists()
```

- [ ] **Step 2: Run to verify fail** → `./venv/bin/pytest tests/test_data_fetcher.py -q`

- [ ] **Step 3: Implement src/data_fetcher.py**

```python
"""Tiered fetch of live results, with cache fallback."""
from __future__ import annotations
import json
from pathlib import Path
import requests

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

def parse_espn(payload: dict) -> dict:
    out = {}
    for ev in payload.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        comp = ev["competitions"][0]["competitors"]
        h = next(c for c in comp if c["homeAway"] == "home")
        a = next(c for c in comp if c["homeAway"] == "away")
        out[ev["id"]] = {"home_goals": int(h["score"]), "away_goals": int(a["score"]), "status": "FT"}
    return out

def _espn_source() -> dict:
    return parse_espn(requests.get(ESPN_URL, timeout=15).json())

def fetch_results(sources=None, cache_path: Path | None = None) -> dict:
    sources = sources if sources is not None else [_espn_source]
    for src in sources:
        try:
            data = src()
            if cache_path is not None and data:
                Path(cache_path).write_text(json.dumps(data))
            return data
        except Exception:
            continue
    if cache_path and Path(cache_path).exists():
        return json.loads(Path(cache_path).read_text())
    return {}
```

- [ ] **Step 4: Run to verify pass** → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/data_fetcher.py tests/test_data_fetcher.py && git commit -m "feat: tiered live result fetch with cache fallback"
```

---

## Task 4: predictor — Elo + form heuristic

**Files:**
- Create: `src/predictor.py`, `data/elo_seed.json`, `tests/test_predictor.py`

> `data/elo_seed.json` maps team name → initial World-Football-Elo rating (transcribe current ratings from eloratings.net at implementation time). Missing teams default to 1500.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_predictor.py
from src import predictor

def test_probs_sum_to_one_and_favor_stronger_team():
    p = predictor.predict(home_elo=2000, away_elo=1600, neutral=True)
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
    assert p["home"] > p["away"]

def test_home_advantage_applied_when_not_neutral():
    neutral = predictor.predict(home_elo=1700, away_elo=1700, neutral=True)
    hosted = predictor.predict(home_elo=1700, away_elo=1700, neutral=False)
    assert hosted["home"] > neutral["home"]

def test_expected_goals_positive():
    eg = predictor.expected_goals(home_elo=1800, away_elo=1500, neutral=True)
    assert eg["home"] > 0 and eg["away"] > 0
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/predictor.py**

```python
"""Elo + home-advantage heuristic: W/D/L probabilities and expected goals."""
from __future__ import annotations
import math

HOME_ADV_ELO = 65.0   # added to home rating when not on neutral ground
DRAW_BASE = 0.27      # baseline draw mass for evenly matched sides

def _win_expectancy(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))

def predict(home_elo: float, away_elo: float, neutral: bool = True) -> dict:
    h = home_elo + (0.0 if neutral else HOME_ADV_ELO)
    we = _win_expectancy(h, away_elo)          # expected score for home in [0,1]
    draw = DRAW_BASE * (1.0 - 2.0 * abs(we - 0.5))  # max draw at parity
    home = we - draw / 2.0
    away = (1.0 - we) - draw / 2.0
    total = home + draw + away
    return {"home": home / total, "draw": draw / total, "away": away / total}

def expected_goals(home_elo: float, away_elo: float, neutral: bool = True) -> dict:
    p = predict(home_elo, away_elo, neutral)
    base = 2.6  # avg total goals in international matches
    return {"home": base * (p["home"] + p["draw"] / 2), "away": base * (p["away"] + p["draw"] / 2)}
```

- [ ] **Step 4: Run to verify pass** → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/predictor.py data/elo_seed.json tests/test_predictor.py && git commit -m "feat: Elo + form heuristic predictor"
```

---

## Task 5: bracket_sim — tables, best-third, knockout, Monte Carlo

**Files:**
- Create: `src/bracket_sim.py`, `tests/test_bracket_sim.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bracket_sim.py
from src import bracket_sim as bs

def test_group_table_orders_by_points_then_gd():
    matches = [
        {"home": "A", "away": "B", "result": {"home_goals": 3, "away_goals": 0}},
        {"home": "A", "away": "C", "result": {"home_goals": 1, "away_goals": 1}},
        {"home": "B", "away": "C", "result": {"home_goals": 0, "away_goals": 0}},
    ]
    table = bs.group_table(["A", "B", "C"], matches)
    assert table[0]["team"] == "A"        # 4 pts, +3 GD
    assert [r["team"] for r in table] == ["A", "C", "B"]

def test_best_thirds_selects_n_by_points_then_gd():
    thirds = [
        {"team": "X", "points": 4, "gd": 1, "gf": 3},
        {"team": "Y", "points": 3, "gd": 2, "gf": 5},
        {"team": "Z", "points": 3, "gd": 1, "gf": 2},
    ]
    assert bs.best_thirds(thirds, n=2) == ["X", "Y"]

def test_monte_carlo_title_odds_sum_to_one():
    probs = lambda h, a: {"home": 0.4, "draw": 0.3, "away": 0.3}
    odds = bs.title_odds(_minimal_tournament(), match_prob=probs, iters=200)
    assert abs(sum(odds.values()) - 1.0) < 1e-6
```

(Provide `_minimal_tournament()` helper in the test file: 2 groups of 4 with no results, a tiny knockard mapping — enough to exercise the simulator.)

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/bracket_sim.py**

Implement, with these exact signatures (used by later tasks):
```python
def group_table(teams: list[str], matches: list[dict]) -> list[dict]: ...
    # returns rows {team, played, points, gd, gf, ga} sorted by FIFA order:
    # points, goal difference, goals for, then head-to-head (approximate by name for ties)
def best_thirds(third_rows: list[dict], n: int = 8) -> list[str]: ...
def simulate_once(tournament: dict, match_prob) -> str: ...   # returns champion team
def title_odds(tournament: dict, match_prob, iters: int = 10000) -> dict: ...
    # returns {team: probability}; locks completed results, simulates the rest
def advancement_odds(tournament: dict, match_prob, iters: int = 10000) -> dict: ...
    # {team: P(reach knockout)}
```
`match_prob(home, away) -> {"home","draw","away"}` is injected (heuristic or ML). Use `numpy`'s default RNG seeded per call for reproducible tests (`numpy.random.default_rng(0)`).

- [ ] **Step 4: Run to verify pass** → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bracket_sim.py tests/test_bracket_sim.py && git commit -m "feat: group tables, best-third tiebreak, Monte Carlo bracket sim"
```

---

## Task 6: ml_predictor bridge (v1 stub)

**Files:**
- Create: `src/ml_predictor.py`, `tests/test_ml_predictor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_ml_predictor.py
from src import ml_predictor

def test_bridge_returns_none_when_ml_absent():
    assert ml_predictor.predict_match("USA", "Mexico") is None

def test_match_prob_uses_fallback_when_ml_none():
    fallback = lambda h, a: {"home": 0.5, "draw": 0.3, "away": 0.2}
    fn = ml_predictor.match_prob_fn(fallback)
    assert fn("USA", "Mexico") == {"home": 0.5, "draw": 0.3, "away": 0.2}
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/ml_predictor.py**

```python
"""Bridge to the ml/ engine. Every public fn catches all and returns None on
failure so the live tracker never depends on ML for correctness (v1: always None)."""
from __future__ import annotations

def predict_match(home: str, away: str) -> dict | None:
    try:
        import sys, pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from ml.src.predict import predict_wdl   # exists only after v2
        return predict_wdl(home, away)
    except Exception:
        return None

def match_prob_fn(fallback):
    """Return f(home, away)->probs using ML when available, else fallback."""
    def _f(home, away):
        return predict_match(home, away) or fallback(home, away)
    return _f
```

- [ ] **Step 4: Run to verify pass** → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ml_predictor.py tests/test_ml_predictor.py && git commit -m "feat: fail-safe ML bridge with heuristic fallback (v1 stub)"
```

---

## Task 7: message_builder

**Files:**
- Create: `src/message_builder.py`, `tests/test_message_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_message_builder.py
from src import message_builder as mb

def test_morning_brief_lists_each_match_with_pick():
    matches = [{"home": "USA", "away": "Mexico",
                "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2}}]
    text = mb.morning_brief("2026-06-11", matches)
    assert "USA" in text and "Mexico" in text and "%" in text

def test_post_match_marks_hit_or_miss():
    m = {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 0}}
    text = mb.post_match(m)
    assert "2-0" in text and ("✓" in text or "✗" in text)

def test_champion_recap_names_winner():
    assert "Brazil" in mb.champion_recap("Brazil")
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/message_builder.py** with functions:
`morning_brief(date_iso, matches)`, `post_match(match)`, `daily_recap(date_iso, matches, group_tables)`, `bracket_update(title_odds, advancement)`, `champion_recap(team)`. Each returns a plain-text string (Telegram-friendly). `post_match` compares the argmax of `prediction` to the actual outcome and appends ✓/✗.

- [ ] **Step 4: Run to verify pass** → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/message_builder.py tests/test_message_builder.py && git commit -m "feat: brief/post-match/recap/bracket/champion message builders"
```

---

## Task 8: telegram_sender

**Files:**
- Create: `src/telegram_sender.py`, `tests/test_telegram_sender.py`

- [ ] **Step 1: Write failing tests** (inject the HTTP poster; no network)

```python
# tests/test_telegram_sender.py
from src import telegram_sender as ts

def test_send_posts_to_each_chat_id():
    calls = []
    poster = lambda url, data: calls.append(data) or type("R", (), {"ok": True})()
    ok = ts.send("hi", token="T", chat_ids=["1", "2"], poster=poster)
    assert ok and len(calls) == 2 and calls[0]["text"] == "hi"

def test_send_returns_false_on_exception():
    def boom(url, data): raise RuntimeError()
    assert ts.send("hi", token="T", chat_ids=["1"], poster=boom) is False

def test_send_noop_when_no_token():
    assert ts.send("hi", token="", chat_ids=["1"]) is False
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/telegram_sender.py**

```python
"""Telegram Bot API delivery. Never raises; returns True only if all sends ok."""
from __future__ import annotations
import requests

def _default_poster(url, data):
    return requests.post(url, data=data, timeout=15)

def send(text: str, token: str, chat_ids: list[str], poster=_default_poster) -> bool:
    if not token or not chat_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        for cid in chat_ids:
            r = poster(url, {"chat_id": cid, "text": text})
            if not getattr(r, "ok", False):
                return False
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run to verify pass** → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/telegram_sender.py tests/test_telegram_sender.py && git commit -m "feat: Telegram delivery, fail-safe multi-recipient"
```

---

## Task 9: html_archive — Bauhaus Pages render

**Files:**
- Create: `src/html_archive.py`, `docs/style.css`, `tests/test_html_archive.py`

- [ ] **Step 1: Write failing tests** (assert structure, not pixels)

```python
# tests/test_html_archive.py
from src import html_archive as ha

def test_render_includes_brand_fonts_and_messages(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "morning_brief", "body": "USA vs Mexico", "sent": True}]}],
        "bracket": {"title_odds": {"Brazil": 0.18}}}
    out = tmp_path / "index.html"
    ha.render(state, out)
    html = out.read_text()
    assert "Playfair Display" in html and "USA vs Mexico" in html and "Brazil" in html

def test_render_uses_brand_background_color(tmp_path):
    out = tmp_path / "index.html"
    ha.render({"days": [], "bracket": {}}, out)
    assert "#F5F1EB" in out.read_text()
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/html_archive.py** — a `render(state, path)` that writes the full page using the Editorial × Bauhaus tokens (cream `#F5F1EB`, crimson `#E0001C`, Playfair italic hero, Inter body, JetBrains Mono labels, 2px ink border + `4px 4px 0 0` shadow, 0 radius). Load the Google Fonts link from CLAUDE.md. Render: hero header, latest title-odds chips (confederation colors: navy/teal/amber/rose), then a reverse-chronological list of day cards with their messages. Prefer importing `/Users/kcl/Desktop/kcl-brand/brand.css` if present, else inline tokens. Put shared CSS in `docs/style.css`.

- [ ] **Step 4: Run to verify pass** → 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/html_archive.py docs/style.css tests/test_html_archive.py && git commit -m "feat: Bauhaus GitHub Pages archive renderer"
```

---

## Task 10: tracker.py — orchestration + idempotency

**Files:**
- Create: `src/tracker.py`, `tests/test_tracker.py`

- [ ] **Step 1: Write failing tests** (drive a full run with injected fetch + sender, tmp state)

```python
# tests/test_tracker.py
from src import tracker

def test_run_generates_morning_brief_once(tmp_path, monkeypatch):
    sent = []
    cfg = tracker.Config(
        state_path=tmp_path / "state.json",
        html_path=tmp_path / "index.html",
        cache_path=tmp_path / "cache.json",
        token="T", chat_ids=["1"],
        fetch=lambda: {}, sender=lambda text, **k: sent.append(text) or True,
        now_iso="2026-06-11",
    )
    tracker.run(cfg); tracker.run(cfg)   # second run must not resend
    assert len(sent) == 1

def test_run_records_result_and_marks_prediction(tmp_path):
    cfg = tracker.Config(
        state_path=tmp_path / "state.json", html_path=tmp_path / "i.html",
        cache_path=tmp_path / "c.json", token="", chat_ids=[],
        fetch=lambda: {"1": {"home_goals": 2, "away_goals": 0, "status": "FT"}},
        sender=lambda text, **k: True, now_iso="2026-06-11")
    code = tracker.run(cfg)
    assert code in (0, 2)
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement src/tracker.py** — a `Config` dataclass (injectable `fetch`, `sender`, paths, token, chat_ids, `now_iso`) and `run(cfg) -> int`:
  1. load state + seed fixtures, merge fetched results
  2. compute predictions via `ml_predictor.match_prob_fn(predictor-based fallback)`
  3. determine due-but-missing messages for `now_iso` (dedup via `state.message_hash`)
  4. re-sim bracket (`bracket_sim.title_odds`/`advancement_odds`)
  5. render HTML, save state
  6. send only the newest undelivered message; mark older skipped
  7. return exit code (0 ok/no-op, 1 fatal, 2 partial). After the final's date → champion recap + set `season_ended`.
  Provide a `main()` that builds `Config` from env (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, real fetch/sender) and `sys.exit(run(cfg))`.

- [ ] **Step 4: Run to verify pass** → 2 passed; then full suite `./venv/bin/pytest -q` green.

- [ ] **Step 5: Commit**

```bash
git add src/tracker.py tests/test_tracker.py && git commit -m "feat: tracker orchestration with idempotent sends and exit codes"
```

---

## Task 11: smoke test

**Files:**
- Create: `scripts/smoke_test.py`

- [ ] **Step 1: Implement scripts/smoke_test.py** — builds a `Config` with synthetic fetched results for the first matchday, `token=""` (no real send), writes to a temp dir, calls `tracker.run`, and prints the generated HTML path + state summary. Never pushes git, never sends Telegram.

- [ ] **Step 2: Run it**

Run: `./venv/bin/python scripts/smoke_test.py`
Expected: prints "morning_brief generated", an HTML path, and exits 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_test.py && git commit -m "test: end-to-end smoke run without send/push"
```

---

## Task 12: GitHub Actions scheduler + README + go live

**Files:**
- Create: `.github/workflows/tracker.yml`, finalize `README.md`

- [ ] **Step 1: Create .github/workflows/tracker.yml**

```yaml
name: wc2026-tracker
on:
  schedule:
    - cron: "*/15 * * * *"   # every 15 min (UTC); active during tournament
  workflow_dispatch: {}
permissions:
  contents: write
concurrency:
  group: tracker
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -r requirements.txt
      - env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_IDS: ${{ secrets.TELEGRAM_CHAT_IDS }}
          FOOTBALL_DATA_KEY: ${{ secrets.FOOTBALL_DATA_KEY }}
        run: python -m src.tracker
      - run: |
          git config user.name "wc2026-tracker"
          git config user.email "actions@users.noreply.github.com"
          git add state.json docs/
          git diff --cached --quiet || git commit -m "update: tracker run $(date -u +%FT%TZ)"
          git push
```

- [ ] **Step 2: Write README.md** — what it is, setup (`gh repo create kcln/wckcfifa2026-tracker --public --source=. --push`), enabling Pages (`main`/`docs`), adding the three Actions secrets, the manual `workflow_dispatch` trigger, the optional local `launchd/` fallback, and how to run the smoke test.

- [ ] **Step 3: Verify workflow is valid locally** (optional)

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/tracker.yml')); print('valid yaml')"`
Expected: `valid yaml`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tracker.yml README.md && git commit -m "ci: GitHub Actions cron scheduler + README"
```

- [ ] **Step 5: Create repo, push, configure (manual, requires user)**

```bash
gh repo create kcln/wckcfifa2026-tracker --public --source=. --remote=origin --push
```
Then in repo settings: Pages → `main`/`docs`; Secrets → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, `FOOTBALL_DATA_KEY`. Trigger once via Actions → Run workflow. **v1 is live.**

---

# v2 — ML engine (Tasks 13–17)

> Isolated under `ml/` with its own venv, mirroring ipl-tracker. v1 keeps working throughout; the bridge (Task 6) starts returning ML probabilities only once `ml/src/predict.py::predict_wdl` exists.

## Task 13: ml ingest

**Files:** Create `ml/requirements.txt` (`pandas`, `scikit-learn`, `lightgbm`, `numpy`, `pyarrow`), `ml/src/__init__.py`, `ml/src/ingest.py`, `ml/tests/test_ingest.py`.

- [ ] **Step 1: Failing test** — `ingest.load_results(csv_path)` returns a DataFrame with columns `{date, home_team, away_team, home_score, away_score, neutral}` and parses dates. Use a 3-row fixture CSV.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `ingest.py`: download `martj42/international_results` `results.csv` (raw GitHub URL) to `ml/data/historical/results.csv` if absent, then `load_results` reads + cleans it.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Commit** `git add ml/ && git commit -m "feat(ml): ingest international results dataset"`.

## Task 14: ml features (point-in-time safe)

**Files:** Create `ml/src/features.py`, `ml/tests/test_features.py`.

- [ ] **Step 1: Failing test** — `features.build(df)` produces, per match, `elo_diff`, `rank_diff` (optional/0 if absent), `form_home`, `form_away` (last-5 points rate computed only from prior matches), `neutral`, and a 3-class label `outcome ∈ {home,draw,away}`. Assert no row uses future matches (PIT): a team's first match has form 0.
- [ ] **Step 2–5:** implement rolling Elo update + last-N form over chronologically sorted data; test; commit.

## Task 15: ml train

**Files:** Create `ml/src/train.py`, `ml/tests/test_train.py`.

- [ ] **Step 1: Failing test** — `train.train(df, out_dir)` writes `model.pkl` + `model.json` (metadata: rows, date range, classes) and returns a fitted classifier whose `predict_proba` rows sum to 1 over 3 classes.
- [ ] **Step 2–5:** LightGBM multiclass + isotonic calibration (`CalibratedClassifierCV`); chronological train/val split; persist; test on tiny synthetic frame; commit.

## Task 16: ml predict + backtest

**Files:** Create `ml/src/predict.py`, `ml/src/backtest.py`, `ml/tests/test_predict.py`.

- [ ] **Step 1: Failing test** — `predict.predict_wdl(home, away)` loads the latest model + current Elo/form state and returns `{"home","draw","away"}` summing to 1; returns calibrated probs for a known strong-vs-weak pair favoring the favorite.
- [ ] **Step 2–5:** implement loader + inference using the same feature builder; `backtest.py` replays chronologically and prints accuracy + Brier vs the Elo baseline from `src/predictor.py`; test; commit.

## Task 17: wire bridge + verify fallback intact

**Files:** Modify `src/ml_predictor.py` test expectations; add `tests/test_ml_integration.py`.

- [ ] **Step 1: Failing test** — with `ml/` trained, `ml_predictor.predict_match("Brazil","Bolivia")` returns a dict summing to 1; with `ml/` import forced to fail (monkeypatch), it returns `None` and `match_prob_fn` uses the fallback. (Task 6's stub test for "returns None when ML absent" is updated to monkeypatch the import failure.)
- [ ] **Step 2: Run → fail/adjust.**
- [ ] **Step 3:** No `src/` code change needed if Task 6 was built correctly — confirm the bridge already calls `ml.src.predict.predict_wdl`. Add an integration smoke that runs `tracker.run` and asserts it still succeeds when ML raises.
- [ ] **Step 4: Run full suite → green.**
- [ ] **Step 5: Commit** `git commit -am "feat(ml): activate ML predictions behind fail-safe bridge"`.

---

## Self-Review

**Spec coverage:** tiered fetch (T3), Elo fallback (T4), bracket/best-third/Monte Carlo (T5), ML bridge + engine (T6, T13–17), message types incl. champion recap (T7, T10), Telegram (T8), Bauhaus Pages (T9), idempotent orchestration + exit codes (T10), GitHub Actions scheduler + secrets + `GITHUB_TOKEN` push (T12), seeded final draw/104 matches (T2), state model (T1/T10), smoke test (T11). All spec sections map to tasks.

**Placeholder scan:** no TBD/TODO in code steps; the two intentional transcription points (fixtures.json from openfootball in T2, elo_seed.json from eloratings.net in T4) are data-population steps with explicit sources and contracts, not logic placeholders.

**Type consistency:** `match_prob(home, away) -> {"home","draw","away"}` is the single injected interface used by `bracket_sim` (T5), `ml_predictor.match_prob_fn` (T6), and `tracker` (T10). `predict_wdl(home, away)` is the ML entry referenced by the bridge (T6) and defined in T16. `Config` fields referenced in T10/T11 match. `state.message_hash(type, date, body)` used consistently in T1 and T10.
