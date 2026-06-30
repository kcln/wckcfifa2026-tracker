"""Tiered fetch of live results, with cache fallback."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

_PT = ZoneInfo("America/Los_Angeles")
_UTC = ZoneInfo("UTC")


def _pt_date(iso_utc: str) -> str:
    """PT calendar date for an ESPN UTC timestamp. Seed fixture dates are PT,
    so evening kickoffs (>= 17:00 PT = 00:00 UTC next day) must be converted
    or reconcile_results drops them on the date mismatch."""
    try:
        dt = datetime.fromisoformat((iso_utc or "").replace("Z", "+00:00"))
    except ValueError:
        return (iso_utc or "")[:10]
    return dt.astimezone(_PT).date().isoformat()


def _team_name(competitor: dict) -> str:
    """Pull a display name from an ESPN competitor, tolerant of payload shape."""
    team = competitor.get("team", {})
    return team.get("displayName") or team.get("name") or competitor.get("name", "")


def _events_from_details(details, id_to_name: dict) -> list:
    """Goals and red cards from a competition's `details` timeline.

    ESPN embeds a per-match `details` list on the scoreboard payload, so no
    extra request is needed. Each returned event is
    {kind, player, team, minute} where kind is one of
    'goal' | 'own_goal' | 'penalty' | 'red'. Red cards key off the `redCard`
    boolean (covers a second yellow, which ESPN also flags red). Shootout
    events are skipped so penalty-shootout pings don't clutter a recap.
    """
    out = []
    for d in details or []:
        if d.get("shootout"):
            continue
        is_red = bool(d.get("redCard"))
        is_goal = bool(d.get("scoringPlay")) and not d.get("yellowCard") \
            and not is_red
        if not (is_goal or is_red):
            continue
        athletes = d.get("athletesInvolved") or []
        player = athletes[0].get("displayName", "") if athletes else ""
        team_id = (d.get("team") or {}).get("id")
        country = id_to_name.get(team_id, "")
        minute = (d.get("clock") or {}).get("displayValue", "")
        if is_red:
            kind = "red"
        elif d.get("ownGoal"):
            kind = "own_goal"
        elif d.get("penaltyKick"):
            kind = "penalty"
        else:
            kind = "goal"
        out.append({"kind": kind, "player": player,
                    "team": country, "minute": minute})
    return out


def parse_espn(payload: dict) -> dict:
    """Extract completed results and half-time scores from an ESPN scoreboard.

    Each entry carries the team names and match date in addition to the score, so
    the tracker can reconcile feed events to our seed fixtures by (home, away, date)
    — ESPN's event ids do not match our seed ids.

    Status mapping: completed -> "FT"; paused at the break (STATUS_HALFTIME) ->
    "HT"; any other in-progress match -> "LIVE" (with the running clock). Only
    pre-match (not yet kicked off) events are skipped, so the website can show
    live scores continuously. Each entry carries `clock` (e.g. "50'").
    """
    out = {}
    for ev in payload.get("events", []):
        stype = ev.get("status", {}).get("type", {})
        if bool(stype.get("completed")):
            status = "FT"
        elif stype.get("name") == "STATUS_HALFTIME":
            status = "HT"
        elif stype.get("state") == "in":    # any other in-progress phase
            status = "LIVE"
        else:
            continue                        # pre-match (not started yet)
        competition = ev["competitions"][0]
        comp = competition["competitors"]
        h = next(c for c in comp if c["homeAway"] == "home")
        a = next(c for c in comp if c["homeAway"] == "away")
        id_to_name = {c.get("team", {}).get("id"): _team_name(c) for c in comp}
        # A knockout tie level after extra time is settled on penalties: ESPN
        # marks the actual winner (`winner: true`) and carries each side's
        # shootout tally, so capture both — the score alone can't tell us.
        win = next((c for c in comp if c.get("winner")), None)
        entry = {
            "home": _team_name(h),
            "away": _team_name(a),
            "date": _pt_date(ev.get("date") or ""),
            "home_goals": int(h["score"]),
            "away_goals": int(a["score"]),
            "status": status,
            "clock": ev.get("status", {}).get("displayClock", ""),
            "events": _events_from_details(
                competition.get("details"), id_to_name),
        }
        if status == "FT" and win is not None:
            entry["winner"] = _team_name(win)
        if h.get("shootoutScore") is not None and a.get("shootoutScore") is not None:
            entry["home_pens"] = int(h["shootoutScore"])
            entry["away_pens"] = int(a["shootoutScore"])
        out[ev["id"]] = entry
    return out


def _scoreboard_urls(now: datetime) -> list:
    """ESPN buckets a fixture by its US-local date, so a late-PT kickoff (>= 9pm
    PT = >= 04:00 UTC) lands in the NEXT UTC date bucket and is absent from the
    default single-day scoreboard. That silently dropped the last match of the
    night and stalled the daily recap (it waits for every match to read FT).
    Fetch a yesterday/today/tomorrow window so any PT day is fully covered."""
    urls = [ESPN_URL]
    for delta in (-1, 0, 1):
        d = (now + timedelta(days=delta)).strftime("%Y%m%d")
        urls.append(f"{ESPN_URL}?dates={d}")
    return urls


def _merge_events(payloads) -> dict:
    """Merge several scoreboard payloads into one, deduping events by id (a
    later payload wins, so explicit date buckets override the default feed)."""
    events = {}
    for p in payloads:
        for ev in p.get("events", []):
            events[ev["id"]] = ev
    return {"events": list(events.values())}


def _espn_source() -> dict:
    payloads = []
    for url in _scoreboard_urls(datetime.now(_UTC)):
        try:
            payloads.append(requests.get(url, timeout=15).json())
        except Exception:
            continue
    return parse_espn(_merge_events(payloads))


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
