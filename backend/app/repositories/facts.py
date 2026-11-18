from __future__ import annotations
import sqlite3
from typing import Any


def list_facts(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM redeem_facts WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM redeem_facts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, status) VALUES(?,?,?,?,?,?)",
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            fields.get("status") or "open",
        ),
    )
    return int(cur.lastrowid)


def open_facts_for_day(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE business_day=? AND status='open' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def facts_for_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    """批快照集合：归属该批的事实行（解钉后仍保留 batch_id 以便互证追溯）。"""
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE batch_id=? ORDER BY id",
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_batched(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> None:
    for fid in fact_ids:
        conn.execute(
            "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE id=?",
            (batch_id, fid),
        )


def unseal_batch_facts(conn: sqlite3.Connection, batch_id: int) -> None:
    """解钉：批内事实回到 open（保留 batch_id 作为快照归属）。"""
    conn.execute(
        "UPDATE redeem_facts SET status='open' WHERE batch_id=?",
        (batch_id,),
    )


def update_amount(conn: sqlite3.Connection, fact_id: int, amount: float) -> None:
    conn.execute(
        "UPDATE redeem_facts SET amount=? WHERE id=?",
        (float(amount), int(fact_id)),
    )


def sum_for_batch(conn: sqlite3.Connection, batch_id: int) -> tuple[int, float]:
    row = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(amount), 0) t FROM redeem_facts WHERE batch_id=?",
        (int(batch_id),),
    ).fetchone()
    return int(row["n"]), round(float(row["t"]), 2)
