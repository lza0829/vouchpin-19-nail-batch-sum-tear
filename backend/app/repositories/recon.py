from __future__ import annotations
import sqlite3
from typing import Any


def insert_run(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO recon_runs(batch_id, business_day, strategy, result, header_count, header_total, fact_count, fact_total, event_count, event_total)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            int(fields["batch_id"]),
            fields["business_day"],
            fields["strategy"],
            fields["result"],
            int(fields["header_count"]),
            float(fields["header_total"]),
            int(fields["fact_count"]),
            float(fields["fact_total"]),
            int(fields["event_count"]),
            float(fields["event_total"]),
        ),
    )
    return int(cur.lastrowid)


def insert_diff(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO recon_diffs(run_id, batch_id, bucket, coupon_code, expected, actual, detail) VALUES(?,?,?,?,?,?,?)",
        (
            int(fields["run_id"]),
            int(fields["batch_id"]),
            fields["bucket"],
            fields.get("coupon_code"),
            fields.get("expected"),
            fields.get("actual"),
            fields.get("detail") or "",
        ),
    )
    return int(cur.lastrowid)


def latest_run_for_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM recon_runs WHERE batch_id=? ORDER BY id DESC LIMIT 1",
        (batch_id,),
    ).fetchone()
    return dict(row) if row else None


def runs_for_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM recon_runs WHERE batch_id=? ORDER BY id DESC",
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def diffs_for_run(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM recon_diffs WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_header_audit(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO batch_header_audits(batch_id, old_fact_count, old_total_amount, new_fact_count, new_total_amount, reason)"
        " VALUES(?,?,?,?,?,?)",
        (
            int(fields["batch_id"]),
            int(fields["old_fact_count"]),
            float(fields["old_total_amount"]),
            int(fields["new_fact_count"]),
            float(fields["new_total_amount"]),
            fields.get("reason") or "",
        ),
    )
    return int(cur.lastrowid)


def audits_for_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM batch_header_audits WHERE batch_id=? ORDER BY id DESC",
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]
