from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM redeem_batches ORDER BY id DESC").fetchall()]


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM redeem_batches WHERE id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def active_batch_for_day(conn: sqlite3.Connection, business_day: str) -> dict[str, Any] | None:
    """现行批：该业务日处于 sealed / disputed 的批次（同一日至多一份）。"""
    row = conn.execute(
        "SELECT * FROM redeem_batches WHERE business_day=? AND status IN ('sealed','disputed') ORDER BY id DESC LIMIT 1",
        (business_day,),
    ).fetchone()
    return dict(row) if row else None


def latest_batch_for_day(conn: sqlite3.Connection, business_day: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM redeem_batches WHERE business_day=? ORDER BY id DESC LIMIT 1",
        (business_day,),
    ).fetchone()
    return dict(row) if row else None


def set_status(conn: sqlite3.Connection, batch_id: int, status: str) -> None:
    conn.execute("UPDATE redeem_batches SET status=? WHERE id=?", (status, batch_id))


def update_header(conn: sqlite3.Connection, batch_id: int, fact_count: int, total_amount: float) -> None:
    conn.execute(
        "UPDATE redeem_batches SET fact_count=?, total_amount=? WHERE id=?",
        (int(fact_count), float(total_amount), batch_id),
    )


def append_note(conn: sqlite3.Connection, batch_id: int, note: str) -> None:
    conn.execute(
        "UPDATE redeem_batches SET note = trim(note || ?) WHERE id=?",
        (note, batch_id),
    )


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_batches(business_day, status, fact_count, total_amount, sealed_at, note) VALUES(?,?,?,?,?,?)",
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)
