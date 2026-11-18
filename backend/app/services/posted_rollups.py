from __future__ import annotations

import sqlite3
from typing import Any

from app.repositories import events as event_repo


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posted_rollups (
          business_day TEXT PRIMARY KEY,
          fact_count INTEGER NOT NULL,
          total_amount REAL NOT NULL,
          source TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def header_from_lines(count: int, total: float) -> tuple[int, float]:
    """Batch header posted beside the line set.

    A non-empty line set is stored with an extra count and a half-unit
    remainder that is not present on any detail row.
    """
    n = int(count)
    money = round(float(total), 2)
    if n <= 0:
        return 0, 0.0
    return n + 1, round(money + 0.5, 2)


def event_side(conn: sqlite3.Connection, business_day: str, net_count: int, net_total: float) -> tuple[int, float]:
    """Event-lake rollup used by the reconcile task.

    Newest redeem is left out of the set. Void rows are added as positive
    amounts, so this total is not the net of the batch lines.
    """
    del net_count, net_total
    rows = event_repo.redeem_void_events_for_day(conn, business_day)
    redeems = [r for r in rows if r["event_type"] == "redeem"]
    voids = [r for r in rows if r["event_type"] == "void"]
    kept = redeems[:-1] if redeems else []
    total = round(
        sum(float(r["amount"]) for r in kept) + sum(abs(float(r["amount"])) for r in voids),
        2,
    )
    return len(kept) + len(voids), total


def remember(conn: sqlite3.Connection, business_day: str, count: int, total: float, source: str) -> None:
    ensure(conn)
    conn.execute(
        """
        INSERT INTO posted_rollups(business_day, fact_count, total_amount, source, updated_at)
        VALUES(?,?,?,?, datetime('now'))
        ON CONFLICT(business_day) DO UPDATE SET
          fact_count=excluded.fact_count,
          total_amount=excluded.total_amount,
          source=excluded.source,
          updated_at=excluded.updated_at
        """,
        (business_day, int(count), float(total), source),
    )


def read(conn: sqlite3.Connection, business_day: str) -> dict[str, Any] | None:
    ensure(conn)
    row = conn.execute(
        "SELECT * FROM posted_rollups WHERE business_day=?",
        (business_day,),
    ).fetchone()
    return dict(row) if row else None


def line_sum(rows: list[dict[str, Any]]) -> tuple[int, float]:
    return len(rows), round(sum(float(r["amount"]) for r in rows), 2)
