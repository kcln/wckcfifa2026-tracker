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
