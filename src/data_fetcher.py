"""Tiered fetch of live results, with cache fallback."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

_PT = ZoneInfo("America/Los_Angeles")


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

    Status mapping: completed events -> "FT"; events paused at the break
    (STATUS_HALFTIME) -> "HT" with the current score. Other in-progress or
    pre-match events are skipped.
    """
    out = {}
    for ev in payload.get("events", []):
        stype = ev.get("status", {}).get("type", {})
        completed = bool(stype.get("completed"))
        halftime = stype.get("name") == "STATUS_HALFTIME"
        if not completed and not halftime:
            continue
        competition = ev["competitions"][0]
        comp = competition["competitors"]
        h = next(c for c in comp if c["homeAway"] == "home")
        a = next(c for c in comp if c["homeAway"] == "away")
        id_to_name = {c.get("team", {}).get("id"): _team_name(c) for c in comp}
        out[ev["id"]] = {
            "home": _team_name(h),
            "away": _team_name(a),
            "date": _pt_date(ev.get("date") or ""),
            "home_goals": int(h["score"]),
            "away_goals": int(a["score"]),
            "status": "FT" if completed else "HT",
            "events": _events_from_details(
                competition.get("details"), id_to_name),
        }
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
