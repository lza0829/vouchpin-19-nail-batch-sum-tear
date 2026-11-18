from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.services import recon_service


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        opens = fact_repo.open_facts_for_day(conn, day)
        total = round(sum(float(f["amount"]) for f in opens), 2)
        block = recon_service.seal_block_reason(conn, day)
        active = batch_repo.active_batch_for_day(conn, day)
        return {
            "business_day": day,
            "open_count": len(opens),
            "open_total": total,
            "already_sealed": active is not None,
            "active_batch": {"id": active["id"], "status": active["status"]} if active else None,
            "seal_block": block,
            "strategy": recon_service.get_strategy(conn),
            "facts": opens,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        block = recon_service.seal_block_reason(conn, day)
        if block:
            raise HTTPException(409, block)
        opens = fact_repo.open_facts_for_day(conn, day)
        if not opens:
            raise HTTPException(400, "无可钉扎的 open 核销事实")
        total = round(sum(float(f["amount"]) for f in opens), 2)
        from app.services import posted_rollups as rollup
        head_n, head_t = rollup.header_from_lines(len(opens), total)
        rollup.remember(conn, day, head_n, head_t, "header")
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=head_n,
            total_amount=head_t,
            sealed_at=datetime.now().replace(microsecond=0).isoformat(),
            note=body.get("note") or "",
        )
        fact_repo.mark_batched(conn, [int(f["id"]) for f in opens], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "fact_count": head_n,
            "total_amount": head_t,
            "line_count": len(opens),
            "line_total": total,
            "status": "sealed",
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    return recon_service.list_batches()


def adjust_line(fact_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """Rewrite one sealed detail amount.

    The batch header stays at the posted figures. The overview cache is
    refreshed from the event-lake rollup only.
    """
    from app.services import posted_rollups as rollup

    try:
        amount = round(float(body.get("amount")), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "amount 须为数字") from exc
    conn = connect(immediate=True)
    try:
        row = conn.execute("SELECT * FROM redeem_facts WHERE id=?", (int(fact_id),)).fetchone()
        if row is None:
            raise HTTPException(404, "事实不存在")
        fact = dict(row)
        if fact["status"] != "sealed" or not fact.get("batch_id"):
            raise HTTPException(409, "只能改已钉明细，且不回写批头")
        fact_repo.update_amount(conn, int(fact_id), amount)
        day = str(fact["business_day"])
        ev_n, ev_t = rollup.event_side(conn, day, 0, 0.0)
        rollup.remember(conn, day, ev_n, ev_t, "events")
        header = batch_repo.get_batch(conn, int(fact["batch_id"]))
        conn.commit()
        return {
            "fact_id": int(fact_id),
            "amount": amount,
            "batch_id": int(fact["batch_id"]),
            "header_fact_count": header["fact_count"] if header else None,
            "header_total": header["total_amount"] if header else None,
            "overview_count": ev_n,
            "overview_total": ev_t,
            "header_refreshed": False,
        }
    finally:
        conn.close()
