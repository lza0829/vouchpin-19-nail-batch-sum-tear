from __future__ import annotations
import sqlite3
from typing import Any


def list_events(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM coupon_events WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM coupon_events ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def redeem_void_events_for_day(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    """事件湖重算口径：该业务日全部 redeem/void 事件。"""
    rows = conn.execute(
        "SELECT * FROM coupon_events WHERE business_day=? AND event_type IN ('redeem','void') ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_event(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount, business_day, occurred_at, note) VALUES(?,?,?,?,?,?,?)",
        (
            fields["event_type"],
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields.get("amount") or 0),
            fields["business_day"],
            fields["occurred_at"],
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)
