from __future__ import annotations

import datetime as dt
import uuid


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())

