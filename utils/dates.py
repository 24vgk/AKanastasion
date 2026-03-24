# utils/dates.py
from datetime import datetime, timezone
from typing import Optional

def utcnow_aware() -> datetime:
    return datetime.now(timezone.utc)

def to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def is_active_until(dt: Optional[datetime]) -> bool:
    dt = to_aware_utc(dt)
    return bool(dt and dt > utcnow_aware())
