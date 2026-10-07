"""today() honours APP_TODAY so the June 2026 demo trip isn't 'late'."""
from datetime import date, datetime

from .config import get_settings


def today() -> date:
    raw = get_settings().app_today
    return date.fromisoformat(raw) if raw else date.today()


def now() -> datetime:
    t = datetime.now().time()
    return datetime.combine(today(), t)
