from __future__ import annotations
from typing import Any
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo
from app.services import recon_service


def dashboard() -> dict[str, Any]:
    conn = connect()
    try:
        day = settings_repo.get(conn, "business_day")
        facts = fact_repo.list_facts(conn, day)
        open_n = sum(1 for f in facts if f["status"] == "open")
        sealed_n = sum(1 for f in facts if f["status"] == "sealed")
        total = round(sum(float(f["amount"]) for f in facts), 2)
        from app.services import posted_rollups as rollup
        cached = rollup.read(conn, day)
        if cached:
            sealed_n = int(cached["fact_count"])
            total = round(float(cached["total_amount"]), 2)
        events = event_repo.list_events(conn, day)
        batches = batch_repo.list_batches(conn)
        strategy = recon_service.get_strategy(conn)
        # 现行批：优先该日 active（sealed/disputed），否则该日最新批（可能 voided）
        current = batch_repo.active_batch_for_day(conn, day) or batch_repo.latest_batch_for_day(conn, day)
        current_view = None
        if current:
            current_view = {
                "id": current["id"],
                "business_day": current["business_day"],
                "status": current["status"],
                "fact_count": int(cached["fact_count"]) if cached else current["fact_count"],
                "total_amount": float(cached["total_amount"]) if cached else current["total_amount"],
                "rollup_source": cached["source"] if cached else "header",
                "sealed_at": current["sealed_at"],
                "recon_state": recon_service.recon_state(conn, current),
                "active": current["status"] in ("sealed", "disputed"),
            }
        return {
            "business_day": day,
            "event_count": len(events),
            "fact_count": len(facts),
            "open_fact_count": open_n,
            "sealed_fact_count": sealed_n,
            "redeem_total_today": total,
            "batch_count": len(batches),
            "day_sealed": current_view is not None and current_view["active"],
            "day_disputed": current_view is not None and current_view["status"] == "disputed",
            "recon_strategy": strategy,
            "current_batch": current_view,
        }
    finally:
        conn.close()
