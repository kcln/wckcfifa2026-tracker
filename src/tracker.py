"""
tracker.py — orchestration core for the 2026 FIFA World Cup tracker.

Runs every ~15 minutes on GitHub Actions. The whole run is idempotent: re-running
on the same day must never duplicate a message or re-send one. Dedup is by the
message hash over (type, date, body). When the job has been down for a while a
backlog of due messages can pile up; rather than spamming, we deliver only the
NEWEST undelivered message and mark the older ones as sent ("skipped, stale").

Exit codes (consumed by CI):
    0  success / no-op
    2  partial — HTML written but a Telegram send was attempted and failed
    1  fatal — the whole body is wrapped in try/except and degrades to 1
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# Support both `python -m src.tracker` and `python src/tracker.py`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import (bracket_sim, data_fetcher, fixtures, html_archive,
                     inbox, live_loop, message_builder, ml_predictor,
                     predictor, state, subscribers, telegram_sender)
else:
    from . import (bracket_sim, data_fetcher, fixtures, html_archive,
                   inbox, live_loop, message_builder, ml_predictor,
                   predictor, state, subscribers, telegram_sender)


HOSTS = {"Mexico", "USA", "Canada"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    state_path: Path
    html_path: Path
    cache_path: Path
    token: str
    chat_ids: list
    fetch: Callable[[], dict]          # () -> {seed_id: {home_goals,away_goals,status}}
    sender: Callable[..., bool]        # (text, **kwargs) -> bool
    now_iso: str                       # today's date in PT, YYYY-MM-DD
    sim_iters: int = 10000


# ---------------------------------------------------------------------------
# Name normalization + feed reconciliation
# ---------------------------------------------------------------------------

# Map common feed spellings to the canonical (squashed) names used in
# data/fixtures.json. Keys and values are post-squash forms.
_ALIASES = {
    "korearepublic": "southkorea",
    "republicofkorea": "southkorea",
    "unitedstates": "usa",
    "unitedstatesofamerica": "usa",
    "iriran": "iran",
    "czechia": "czechrepublic",
    "cotedivoire": "ivorycoast",
    # ESPN uses the endonyms; the seed uses common English names. Day-3 the
    # 'Türkiye' (-> turkiye) vs seed 'Turkey' mismatch silently dropped
    # Australia 2-0 Türkiye, which blocked the whole June-13 daily recap.
    "turkiye": "turkey",
    # ESPN sometimes spells the ampersand out ("Bosnia and Herzegovina");
    # squashing alone can't unify "&" with "and", so alias it explicitly.
    "bosniaandherzegovina": "bosniaherzegovina",
}

_SQUASH_RE = re.compile(r"[^a-z0-9]+")


def _norm(name: str) -> str:
    """Canonicalize a team name for feed<->seed matching: lowercase, strip
    ALL non-alphanumerics (so 'Bosnia-Herzegovina' and 'Bosnia & Herzegovina'
    unify), then apply the alias table. Callers compare _norm to _norm — the
    canonical form is internal only.

    Burned by punctuation on day 2: ESPN's 'Bosnia-Herzegovina' vs the seed's
    'Bosnia & Herzegovina' silently dropped the Canada match's result."""
    n = unicodedata.normalize("NFKD", (name or ""))
    n = n.encode("ascii", "ignore").decode()  # ô -> o, ç -> c
    n = _SQUASH_RE.sub("", n.strip().lower())
    return _ALIASES.get(n, n)


def reconcile_results(raw_feed: dict, seed: dict) -> dict:
    """Map an ESPN-style feed (keyed by feed id, each entry carrying home/away team
    names + date + goals + status) onto seed fixture ids.

    Matching is by (normalized home, normalized away, date). Unmatched feed entries
    are silently skipped. The real fetch in main() pipes the data_fetcher output
    through here; tests inject already-reconciled {seed_id: result} dicts so they
    never exercise this path.
    """
    index = {}
    for m in seed.get("matches", []):
        key = (_norm(m["home"]), _norm(m["away"]), m.get("date"))
        index[key] = m["id"]

    out = {}
    for entry in raw_feed.values():
        if not isinstance(entry, dict):
            continue
        key = (_norm(entry.get("home", "")), _norm(entry.get("away", "")),
               entry.get("date"))
        seed_id = index.get(key)
        if seed_id is None:
            continue
        out[seed_id] = {
            "home_goals": entry["home_goals"],
            "away_goals": entry["away_goals"],
            "status": entry.get("status", "FT"),
            "events": entry.get("events", []),
        }
    return out


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------

def is_host_home(home: str, match: dict) -> bool:
    """Whether `home` should get a home-advantage bump for this match.

    v1 simplification: we treat a match as non-neutral (home advantage) only when
    the home team is one of the three hosts {Mexico, USA, Canada}. We do not check
    that the venue is actually in that host's territory, nor restrict to group
    stage — the host set is small and this keeps the heuristic transparent.
    """
    return home in HOSTS


def _build_match_prob(merged: dict):
    """match_prob(home, away) using ML when available, else the Elo predictor with
    host home-advantage applied per is_host_home."""
    def fallback(home, away):
        neutral = home not in HOSTS
        return predictor.predict_teams(home, away, neutral=neutral)

    return ml_predictor.match_prob_fn(fallback)


# ---------------------------------------------------------------------------
# Day / message bookkeeping
# ---------------------------------------------------------------------------

def _get_day(stateobj: dict, date_iso: str) -> dict:
    """Return (creating if needed) the day entry for date_iso."""
    for d in stateobj["days"]:
        if d.get("date") == date_iso:
            d.setdefault("messages", [])
            return d
    day = {"date": date_iso, "messages": []}
    stateobj["days"].append(day)
    return day


def _all_hashes(stateobj: dict) -> set:
    """Every message hash already present anywhere in state."""
    return {
        m["hash"]
        for d in stateobj["days"]
        for m in d.get("messages", [])
        if "hash" in m
    }


def _add_message(day: dict, existing: set, msg_type: str, date_iso: str,
                 body: str, kickoff_utc: str = "") -> None:
    """Append a message to `day` iff its (type,date,body) hash is new.
    Mutates `existing` so repeated calls within one run stay deduped.
    Stamps kickoff_utc (the relevant match's start, shown as the archive's
    PT/CT/ET/IST time stack) and generated_at (PT); neither is part of the
    dedup hash."""
    h = state.message_hash(msg_type, date_iso, body)
    if h in existing:
        return
    msg = {"type": msg_type, "body": body, "sent": False, "hash": h,
           "generated_at": state.now_pt().isoformat()}
    if kickoff_utc:
        msg["kickoff_utc"] = kickoff_utc
    day["messages"].append(msg)
    existing.add(h)


def _first_kickoff(matches: list[dict]) -> str:
    """Earliest kickoff among `matches` — the day-level messages' timestamp."""
    kicks = sorted(m.get("kickoff_utc") or "" for m in matches)
    kicks = [k for k in kicks if k]
    return kicks[0] if kicks else ""


# ---------------------------------------------------------------------------
# Due-message computation
# ---------------------------------------------------------------------------

def _matches_on(merged: dict, date_iso: str) -> list:
    return [m for m in merged["matches"] if m.get("date") == date_iso]


def _with_prediction(match: dict, match_prob) -> dict:
    """Shallow copy of a match with a `prediction` key the message builder needs."""
    out = dict(match)
    out["prediction"] = match_prob(match["home"], match["away"])
    return out


_DAY_DONE_AFTER = timedelta(hours=3, minutes=30)  # latest plausible final whistle


def _day_clock_complete(matches: list[dict], now_dt: datetime) -> bool:
    """True once every today match's kickoff + ~3.5h has passed — i.e. the
    day is over by the clock. Used as a fallback so a match that never
    reconciles (a feed name mismatch) can't silently block the daily recap
    forever. Returns False if any match lacks a parseable kickoff."""
    latest = None
    for m in matches:
        ko = m.get("kickoff_utc")
        if not ko:
            return False
        try:
            dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
        except ValueError:
            return False
        latest = dt if latest is None else max(latest, dt)
    return latest is not None and now_dt >= latest + _DAY_DONE_AFTER


def _group_tables_for(merged: dict) -> dict:
    """Compute current group tables {letter: rows} from merged fixtures."""
    by_group = {g: [] for g in merged["groups"]}
    for m in merged["matches"]:
        if m["stage"] == "group" and m.get("group") in by_group:
            by_group[m["group"]].append(m)
    return {
        g: bracket_sim.group_table(merged["groups"][g], by_group[g])
        for g in merged["groups"]
    }


def _final_match(merged: dict) -> dict | None:
    for m in merged["matches"]:
        if m["stage"] == "final":
            return m
    return None


def _latest_result(merged: dict) -> dict | None:
    """Most recent finished match — feeds the archive's 'Most recent' hero card."""
    done = [m for m in merged["matches"] if m.get("result")]
    if not done:
        return None
    m = max(done, key=lambda x: (x.get("date") or "", str(x.get("id") or "")))
    r = m["result"]
    return {
        "home": m["home"], "away": m["away"],
        "home_goals": r.get("home_goals"), "away_goals": r.get("away_goals"),
        "date": m.get("date"), "venue": m.get("venue"),
    }


def _prev_day_iso(now_iso: str) -> str:
    """The PT calendar day before `now_iso` (YYYY-MM-DD)."""
    return (datetime.strptime(now_iso, "%Y-%m-%d").date()
            - timedelta(days=1)).isoformat()


def _result_outcome(r: dict) -> str:
    if r["home_goals"] > r["away_goals"]:
        return "home"
    if r["away_goals"] > r["home_goals"]:
        return "away"
    return "draw"


def _accuracy(merged: dict, match_prob, *, until_kickoff: str | None = None,
              date_iso: str | None = None) -> tuple:
    """(hits, total) prediction accuracy over RESOLVED matches — argmax pick vs
    actual outcome. Filter to a single PT day with `date_iso`, or to matches
    that kicked off at/before `until_kickoff` for a stable running cumulative."""
    hits = total = 0
    for m in merged["matches"]:
        r = m.get("result")
        if not r:
            continue
        if date_iso is not None and m.get("date") != date_iso:
            continue
        if until_kickoff is not None and (m.get("kickoff_utc") or "") > until_kickoff:
            continue
        pred = match_prob(m["home"], m["away"])
        predicted = max(("home", "draw", "away"), key=lambda k: pred[k])
        total += 1
        if predicted == _result_outcome(r):
            hits += 1
    return hits, total


def _due_for_day(stateobj: dict, merged: dict, match_prob, date_iso: str,
                 *, is_today: bool, live: dict | None, existing: set) -> None:
    """Append all due messages for the matches whose PT KICKOFF date is
    `date_iso`: morning brief, per-match results, (live-day-only) half-times,
    the daily recap, and any knockout bracket update. All deduped by hash.

    Because a day is keyed by kickoff date, a match that starts late and ends
    after PT midnight is still handled here when this day is reprocessed the
    next calendar day — so its result and the day's recap always land."""
    todays = _matches_on(merged, date_iso)
    if not todays:
        return
    day = _get_day(stateobj, date_iso)
    todays_pred = [_with_prediction(m, match_prob) for m in todays]

    # 1) Morning brief — once per day with matches.
    brief = message_builder.morning_brief(date_iso, todays_pred)
    _add_message(day, existing, "morning_brief", date_iso, brief,
                 kickoff_utc=_first_kickoff(todays))

    # 2) Post-match — per finished match (fires even when reprocessing a prior
    #    day, so a past-midnight finish still gets its result). The running
    #    accuracy is cumulative THROUGH this match's kickoff, so the body stays
    #    stable as later matches resolve (no spurious re-sends).
    for mp in todays_pred:
        if mp.get("result"):
            overall = _accuracy(merged, match_prob,
                                until_kickoff=mp.get("kickoff_utc") or "")
            body = message_builder.post_match(mp, overall=overall)
            _add_message(day, existing, "post_match", date_iso, body,
                         kickoff_utc=mp.get("kickoff_utc") or "")

    # 2.5) Half-time — only for the live (today) day; prior-day matches are done.
    if is_today:
        for mp in todays_pred:
            entry = (live or {}).get(mp.get("id"))
            if (entry and entry.get("status") == "HT"
                    and not mp.get("result")):
                body = message_builder.half_time(
                    mp, entry["home_goals"], entry["away_goals"],
                    events=entry.get("events"))
                _add_message(day, existing, "half_time", date_iso, body,
                             kickoff_utc=mp.get("kickoff_utc") or "")

    # 3) Daily recap — once per day, when every match is resolved OR the day is
    #    clock-complete. Fires regardless of the current PT date, so the recap
    #    lands after the last match even if that's after midnight.
    already_recapped = any(mm.get("type") == "daily_recap"
                           for mm in day["messages"])
    any_resolved = any(m.get("result") for m in todays)
    all_resolved = all(m.get("result") for m in todays)
    if any_resolved and not already_recapped and (
            all_resolved
            or _day_clock_complete(todays, datetime.now(timezone.utc))):
        tables = _group_tables_for(merged)
        day_acc = _accuracy(merged, match_prob, date_iso=date_iso)
        last_ko = max((m.get("kickoff_utc") or "" for m in todays), default="")
        overall_acc = _accuracy(merged, match_prob, until_kickoff=last_ko)
        recap = message_builder.daily_recap(date_iso, todays_pred, tables,
                                            day_acc=day_acc,
                                            overall_acc=overall_acc)
        _add_message(day, existing, "daily_recap", date_iso, recap,
                     kickoff_utc=_first_kickoff(todays))

    # 4) Bracket update — on any knockout date.
    if any(m["stage"] != "group" for m in todays):
        bracket = stateobj.get("bracket") or {}
        body = message_builder.bracket_update(
            bracket.get("title_odds") or {},
            bracket.get("advancement") or {},
        )
        _add_message(day, existing, "bracket_update", date_iso, body,
                     kickoff_utc=_first_kickoff(todays))


def _due_messages(stateobj: dict, merged: dict, match_prob, now_iso: str,
                  live: dict | None = None) -> None:
    """Compute and append all due messages (deduped).

    Processes today AND the immediately previous PT day, so a match that ends
    after PT midnight still gets its result and its day's recap — the day is
    keyed by PT KICKOFF date. No deeper history is scanned (going forward only).
    """
    existing = _all_hashes(stateobj)
    _due_for_day(stateobj, merged, match_prob, _prev_day_iso(now_iso),
                 is_today=False, live=None, existing=existing)
    _due_for_day(stateobj, merged, match_prob, now_iso,
                 is_today=True, live=live, existing=existing)

    # 5) Champion recap — once, after the final is done (or now past it).
    if not stateobj.get("season_ended"):
        fin = _final_match(merged)
        if fin is not None:
            final_done = bool(fin.get("result"))
            past_final = fin.get("date") is not None and now_iso > fin["date"]
            if final_done or past_final:
                champ = _champion_name(fin)
                if champ:
                    cday = _get_day(stateobj, now_iso)
                    body = message_builder.champion_recap(champ)
                    _add_message(cday, existing, "champion_recap", now_iso, body,
                                 kickoff_utc=fin.get("kickoff_utc") or "")
                    stateobj["season_ended"] = True


def _champion_name(final_match: dict) -> str | None:
    """Resolve the champion's team name from the final's recorded result.
    Returns None if the final has no concrete teams/result yet."""
    res = final_match.get("result")
    home, away = final_match.get("home"), final_match.get("away")
    # Only resolvable when the final carries concrete (non-descriptor) team names
    # and a result. Descriptors like "W101" cannot be named without simulation.
    if not res or not home or not away:
        return None
    if home[:1] in {"W", "L"} or home[:1].isdigit():
        return None
    return home if res["home_goals"] >= res["away_goals"] else away


# ---------------------------------------------------------------------------
# Send all pending (oldest first) — no skips
# ---------------------------------------------------------------------------

def _undelivered(stateobj: dict) -> list:
    """All undelivered messages across all days, oldest-first.

    Ordering: by day date ascending, then by position within the day (append
    order, which already follows brief -> results -> recap -> bracket -> champion).
    """
    items = []
    for d in sorted(stateobj["days"], key=lambda x: x.get("date", "")):
        for m in d.get("messages", []):
            if not m.get("sent"):
                items.append(m)
    return items


def _send_pending(stateobj: dict, cfg: Config) -> int | None:
    """Deliver every undelivered message, oldest first — nothing is skipped.

    Each message is marked sent as it is delivered. On the first failure we
    stop and return 2; the failed message and anything after it stay unsent
    and are retried on the next run. Returns None if nothing was attempted
    (no pending messages, or token/chat_ids are empty), 0 if every pending
    message was delivered.
    """
    pending = _undelivered(stateobj)
    if not pending:
        return None

    if not cfg.token or not cfg.chat_ids:
        # Sending disabled: leave messages unsent (not an error, not delivered).
        return None

    for m in pending:
        ok = cfg.sender(m["body"], token=cfg.token, chat_ids=cfg.chat_ids)
        if not ok:
            return 2
        m["sent"] = True
    return 0


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(cfg: Config) -> int:
    try:
        stateobj = state.load(cfg.state_path)
        seed = fixtures.load_seed()

        try:
            live = cfg.fetch() or {}
        except Exception:
            live = {}

        merged = fixtures.merge_results(seed, live)
        match_prob = _build_match_prob(merged)

        # Compute and append all due messages for today (idempotent).
        _due_messages(stateobj, merged, match_prob, cfg.now_iso, live=live)

        # Recompute bracket + group state.
        try:
            stateobj["bracket"] = {
                "title_odds": bracket_sim.title_odds(merged, match_prob,
                                                     cfg.sim_iters),
                "advancement": bracket_sim.advancement_odds(merged, match_prob,
                                                            cfg.sim_iters),
            }
        except Exception:
            stateobj.setdefault("bracket", {})
        stateobj["groups"] = _group_tables_for(merged)
        stateobj["last_result"] = (_latest_result(merged)
                                   or stateobj.get("last_result"))

        # Keep days ordered.
        stateobj["days"].sort(key=lambda d: d.get("date", ""))

        # Render + persist before sending so the archive is up to date even if a
        # send fails.
        try:
            html_archive.render(stateobj, cfg.html_path)
        except Exception:
            pass
        state.save(cfg.state_path, stateobj)

        # Send everything still undelivered, oldest first.
        send_code = _send_pending(stateobj, cfg)
        state.save(cfg.state_path, stateobj)

        # Stop the tracker for good once the tournament is over: the champion
        # recap set season_ended, or we're well past the final. Drop a sentinel
        # the workflow uses to disable its schedule (no endless empty runs).
        if _tournament_over(merged, stateobj, cfg.now_iso):
            try:
                (Path(cfg.state_path).parent / ".season-ended").write_text("1\n")
            except Exception:
                pass

        if send_code == 2:
            return 2
        return 0
    except Exception:
        return 1


# How long after the final to keep running as a failsafe if the champion recap
# never fired (e.g. the final's result never reconciled).
_POST_FINAL_GRACE = timedelta(days=3)


def _tournament_over(merged: dict, stateobj: dict, now_iso: str) -> bool:
    """True once the World Cup is done — either the champion recap has fired
    (season_ended) or we're more than the grace period past the final's date."""
    if stateobj.get("season_ended"):
        return True
    fin = _final_match(merged)
    if fin and fin.get("date"):
        try:
            final_date = datetime.strptime(fin["date"], "%Y-%m-%d").date()
            today = datetime.strptime(now_iso, "%Y-%m-%d").date()
            return today > final_date + _POST_FINAL_GRACE
        except ValueError:
            return False
    return False


# ---------------------------------------------------------------------------
# Signup catch-up + inbox processing
# ---------------------------------------------------------------------------

def build_catchup(stateobj: dict, now_iso: str, option: int) -> list[str]:
    """Message bodies a new member gets for onboarding choice 1-4, drawn from
    today's already-built messages:
      1 brief + updates so far + day summary   2 brief only
      3 updates only                           4 day summary only
    """
    day = next((d for d in stateobj.get("days", []) if d.get("date") == now_iso),
               None)
    msgs = (day or {}).get("messages", [])
    brief = [m["body"] for m in msgs if m["type"] == "morning_brief"]
    updates = [m["body"] for m in msgs
               if m["type"] in ("half_time", "post_match")]
    recap = [m["body"] for m in msgs if m["type"] == "daily_recap"]
    if option == 2:
        return brief or ["No matchday brief yet for today."]
    if option == 3:
        return updates or ["No match updates yet today."]
    if option == 4:
        return recap or ["The day's summary posts after the last match — "
                         "you'll get it live."]
    return (brief + updates + recap) or [
        "Today's coverage hasn't started yet — you'll get everything live."]


def process_inbox(root: Path, token: str) -> list[str]:
    """Poll Telegram and run the signup approval/onboarding pipeline, then
    return the current approved broadcast list. Never raises."""
    subs_path = root / "subscribers.json"
    subs = subscribers.load(subs_path)
    if not token:
        return subs.get("approved", [])
    try:
        updates = inbox.poll(token, subs.get("last_update_id", 0) + 1)
        if updates:
            stateobj = state.load(root / "state.json")
            now_iso = state.today_pt_iso()
            send, answer_cb = inbox.make_io(token)
            approver = os.environ.get("APPROVER_CHAT_ID", "391401564")
            inbox.process_updates(
                updates, subs, approver=approver, send=send, answer_cb=answer_cb,
                catchup=lambda opt: build_catchup(stateobj, now_iso, opt),
                now_ts=state.now_pt().isoformat())
            subscribers.save(subs_path, subs)
    except Exception:
        pass
    return subs.get("approved", [])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _build_cfg(root: Path, chat_ids: list) -> Config:
    """Fresh Config per cycle: now_iso rolls over at PT midnight and the seed
    is reloaded so long live-mode loops pick up rebased fixture changes.
    `chat_ids` is the approved broadcast list from subscribers.json."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cache_path = root / "data" / "cache" / "results.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    seed = fixtures.load_seed()

    return Config(
        state_path=root / "state.json",
        html_path=root / "docs" / "index.html",
        cache_path=cache_path,
        token=token,
        chat_ids=chat_ids,
        fetch=lambda: reconcile_results(
            data_fetcher.fetch_results(cache_path=cache_path), seed),
        sender=lambda text, **k: telegram_sender.send(text, token, chat_ids),
        now_iso=state.today_pt_iso(),
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="2026 World Cup tracker")
    parser.add_argument("--live", action="store_true",
                        help="poll through the matchday window instead of a "
                             "single cycle (catches half-time breaks)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    (root / "docs").mkdir(parents=True, exist_ok=True)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if not args.live:
        approved = process_inbox(root, token)
        sys.exit(run(_build_cfg(root, approved)))

    autocommit = os.environ.get("GIT_AUTOCOMMIT") == "1"

    def run_once() -> int:
        approved = process_inbox(root, token)
        code = run(_build_cfg(root, approved))
        if autocommit:
            live_loop.git_sync()
        return code

    kickoffs = live_loop.kickoffs_from_matches(
        fixtures.load_seed().get("matches", []))
    code, cont = live_loop.live_loop(run_once, kickoffs)
    # Don't chain a continuation once the tournament is over — let it wind down.
    if cont and not (root / ".season-ended").exists():
        # The workflow dispatches a continuation run when this flag exists.
        (root / ".live-continue").write_text("1\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
