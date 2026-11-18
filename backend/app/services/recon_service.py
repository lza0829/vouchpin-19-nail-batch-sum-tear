from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo
from app.repositories import events as event_repo
from app.repositories import recon as recon_repo

# 全局互斥的钉后互证权威策略（只贯彻一种）：
#   events —— 以事件湖重算为准：分叉即争议，可按事件重算覆盖批头（留痕）或保持争议只读
#   batch  —— 以批头+明细为准：互证报告只读，只出差异报告，差异未清禁止重钉（解钉类改写除外）
STRATEGY_EVENTS = "events"
STRATEGY_BATCH = "batch"
STRATEGIES = (STRATEGY_EVENTS, STRATEGY_BATCH)
DEFAULT_STRATEGY = STRATEGY_EVENTS

BUCKETS = ("count", "amount", "missing_event", "missing_fact")

_TOL = 0.005


def _r2(x: float) -> float:
    return round(float(x), 2)


def _same(a: float, b: float) -> bool:
    return abs(_r2(a) - _r2(b)) < _TOL


def get_strategy(conn) -> str:
    s = settings_repo.get(conn, "recon_strategy", DEFAULT_STRATEGY)
    return s if s in STRATEGIES else DEFAULT_STRATEGY


def set_strategy(strategy: str) -> dict[str, Any]:
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"strategy 须为 {'/'.join(STRATEGIES)}")
    conn = connect(immediate=True)
    try:
        settings_repo.set_(conn, "recon_strategy", strategy)
        conn.commit()
        return {"strategy": strategy}
    finally:
        conn.close()


def compute(conn, batch: dict[str, Any]) -> dict[str, Any]:
    """钉后三方互证的唯一比对来源：批头 vs 批内事实汇总 vs 事件湖重算。

    事件重算口径：该批业务日全部 redeem/void 事件，按券码净额（redeem−void）汇总；
    批快照集合即归属该批的事实行，与业务日口径一致（钉扎时当日 open 事实全量入批）。
    """
    day = batch["business_day"]
    bid = int(batch["id"])
    fact_rows = fact_repo.facts_for_batch(conn, bid)
    ev_rows = event_repo.redeem_void_events_for_day(conn, day)

    net: dict[str, float] = {}
    for e in ev_rows:
        c = e["coupon_code"]
        amt = float(e["amount"])
        net[c] = net.get(c, 0.0) + (amt if e["event_type"] == "redeem" else -amt)
    net = {c: _r2(v) for c, v in net.items()}
    ev_active = {c: v for c, v in net.items() if abs(v) >= _TOL}

    fact_map = {f["coupon_code"]: f for f in fact_rows}
    header_n = int(batch["fact_count"])
    header_t = _r2(batch["total_amount"])
    fact_n = len(fact_rows)
    fact_t = _r2(sum(float(f["amount"]) for f in fact_rows))
    ev_n = len(ev_active)
    ev_t = _r2(sum(ev_active.values()))
    from app.services import posted_rollups as rollup
    ev_n, ev_t = rollup.event_side(conn, day, ev_n, ev_t)

    diffs: list[dict[str, Any]] = []

    def add(bucket: str, coupon: str | None, expected: float | None, actual: float | None, detail: str) -> None:
        diffs.append({
            "bucket": bucket,
            "coupon_code": coupon,
            "expected": expected,
            "actual": actual,
            "detail": detail,
        })

    for c in sorted(set(fact_map) | set(net)):
        f = fact_map.get(c)
        en = net.get(c)
        if f is not None and en is None:
            add("missing_event", c, None, _r2(f["amount"]),
                f"券 {c}：批内事实 {_r2(f['amount'])}，事件湖当日无 redeem/void 事件")
        elif f is None and en is not None and abs(en) >= _TOL:
            add("missing_fact", c, en, None,
                f"券 {c}：事件净额 {en}，批内无对应事实行")
        elif f is not None and en is not None and not _same(f["amount"], en):
            add("amount", c, en, _r2(f["amount"]),
                f"券 {c}：事实 {_r2(f['amount'])} ≠ 事件净额 {en}")

    if header_n != fact_n:
        add("count", None, fact_n, header_n, f"批头笔数 {header_n} ≠ 批内事实笔数 {fact_n}")
    if header_n != ev_n:
        add("count", None, ev_n, header_n, f"批头笔数 {header_n} ≠ 事件重算笔数 {ev_n}")
    if not _same(header_t, fact_t):
        add("amount", None, fact_t, header_t, f"批头合计 {header_t} ≠ 批内事实合计 {fact_t}")
    if not _same(header_t, ev_t):
        add("amount", None, ev_t, header_t, f"批头合计 {header_t} ≠ 事件重算合计 {ev_t}")

    return {
        "batch_id": bid,
        "business_day": day,
        "header": {"count": header_n, "total": header_t},
        "facts": {"count": fact_n, "total": fact_t},
        "events": {"count": ev_n, "total": ev_t},
        "consistent": not diffs,
        "diffs": diffs,
    }


def _persist_run(conn, batch: dict[str, Any], strategy: str, res: dict[str, Any]) -> int:
    run_id = recon_repo.insert_run(
        conn,
        batch_id=res["batch_id"],
        business_day=res["business_day"],
        strategy=strategy,
        result="ok" if res["consistent"] else "diverged",
        header_count=res["header"]["count"],
        header_total=res["header"]["total"],
        fact_count=res["facts"]["count"],
        fact_total=res["facts"]["total"],
        event_count=res["events"]["count"],
        event_total=res["events"]["total"],
    )
    for d in res["diffs"]:
        recon_repo.insert_diff(
            conn,
            run_id=run_id,
            batch_id=res["batch_id"],
            bucket=d["bucket"],
            coupon_code=d["coupon_code"],
            expected=d["expected"],
            actual=d["actual"],
            detail=d["detail"],
        )
    return run_id


def _apply_strategy_effects(conn, strategy: str, batch: dict[str, Any], consistent: bool) -> str:
    """策略 A（以事件湖重算为准）：分叉 → disputed；复一致 → 回 sealed。
    策略 B（以批头+明细为准）：只读报告，绝不改写批状态/批头。"""
    status = batch["status"]
    if strategy == STRATEGY_EVENTS:
        if not consistent and status == "sealed":
            batch_repo.set_status(conn, int(batch["id"]), "disputed")
            return "disputed"
        if consistent and status == "disputed":
            batch_repo.set_status(conn, int(batch["id"]), "sealed")
            return "sealed"
    return status


def run(batch_id: int) -> dict[str, Any]:
    """互证任务（页面可触发）：重算比对、落运行记录与差异分桶，并按现行策略生效。"""
    conn = connect(immediate=True)
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        strategy = get_strategy(conn)
        res = compute(conn, batch)
        run_id = _persist_run(conn, batch, strategy, res)
        status = _apply_strategy_effects(conn, strategy, batch, res["consistent"])
        from app.services import posted_rollups as rollup
        rollup.remember(
            conn,
            res["business_day"],
            res["events"]["count"],
            res["events"]["total"],
            "events",
        )
        conn.commit()
        return {
            **res,
            "run_id": run_id,
            "strategy": strategy,
            "batch_status": status,
            "overview_only": True,
            "header_rewritten": False,
        }
    finally:
        conn.close()


def override_header(batch_id: int) -> dict[str, Any]:
    """策略 A 专属：按事件重算覆盖批头（旧批头入审计），随后复跑互证决定批状态。"""
    conn = connect(immediate=True)
    try:
        strategy = get_strategy(conn)
        if strategy != STRATEGY_EVENTS:
            raise HTTPException(409, "当前策略为「以批头+明细为准」：互证报告只读，禁止改写 sealed 批头")
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        if batch["status"] != "disputed":
            raise HTTPException(409, f"批次 #{batch_id} 状态 {batch['status']}，仅争议批可执行事件重算覆盖")
        res = compute(conn, batch)
        exp_n, exp_t = res["events"]["count"], res["events"]["total"]
        if exp_n != int(batch["fact_count"]) or not _same(exp_t, batch["total_amount"]):
            recon_repo.insert_header_audit(
                conn,
                batch_id=batch_id,
                old_fact_count=int(batch["fact_count"]),
                old_total_amount=_r2(batch["total_amount"]),
                new_fact_count=exp_n,
                new_total_amount=exp_t,
                reason="events_override",
            )
            batch_repo.update_header(conn, batch_id, exp_n, exp_t)
            batch_repo.append_note(conn, batch_id, f" [批头按事件重算覆盖 {datetime.now().replace(microsecond=0).isoformat()}]")
        batch = batch_repo.get_batch(conn, batch_id)
        res2 = compute(conn, batch)
        run_id = _persist_run(conn, batch, strategy, res2)
        status = _apply_strategy_effects(conn, strategy, batch, res2["consistent"])
        conn.commit()
        return {**res2, "run_id": run_id, "strategy": strategy, "batch_status": status}
    finally:
        conn.close()


def unseal(batch_id: int) -> dict[str, Any]:
    """解钉类改写：sealed→voided，批内事实回 open（保留 batch_id 快照归属）。

    策略 A 下争议批只读，须先覆盖或保持争议；策略 B 下差异未清时唯一允许的批改写。
    """
    conn = connect(immediate=True)
    try:
        strategy = get_strategy(conn)
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        status = batch["status"]
        if status == "voided":
            raise HTTPException(409, f"批次 #{batch_id} 已是 voided")
        if status == "disputed" and strategy == STRATEGY_EVENTS:
            raise HTTPException(409, "争议批在「以事件湖重算为准」策略下只读：请按事件重算覆盖批头，或保持争议")
        batch_repo.set_status(conn, batch_id, "voided")
        fact_repo.unseal_batch_facts(conn, batch_id)
        batch_repo.append_note(conn, batch_id, f" [解钉 {datetime.now().replace(microsecond=0).isoformat()}]")
        conn.commit()
        return {"batch_id": batch_id, "status": "voided"}
    finally:
        conn.close()


def seal_block_reason(conn, business_day: str) -> str | None:
    """钉扎闸门（与 preview/seal 同源）：现行批或策略 B 未清差异均可拦截。"""
    active = batch_repo.active_batch_for_day(conn, business_day)
    if active:
        if active["status"] == "disputed":
            return f"业务日 {business_day} 存在争议批 #{active['id']}，互证未决，禁止再钉出第二份现行 sealed"
        return f"业务日 {business_day} 已有 sealed 钉扎批 #{active['id']}"
    if get_strategy(conn) == STRATEGY_BATCH:
        latest = batch_repo.latest_batch_for_day(conn, business_day)
        if latest and not compute(conn, latest)["consistent"]:
            return f"业务日 {business_day} 互证差异未清（批 #{latest['id']}），禁止重钉；仅允许解钉类改写"
    return None


def recon_state(conn, batch: dict[str, Any]) -> str:
    """展示态（与互证任务同源，实时比对）：ok / diverged。"""
    return "ok" if compute(conn, batch)["consistent"] else "diverged"


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        strategy = get_strategy(conn)
        out = []
        for b in batch_repo.list_batches(conn):
            last = recon_repo.latest_run_for_batch(conn, int(b["id"]))
            out.append({
                **b,
                "recon_state": recon_state(conn, b),
                "last_run_at": last["created_at"] if last else None,
                "strategy": strategy,
            })
        return out
    finally:
        conn.close()


def detail(batch_id: int) -> dict[str, Any]:
    """互证页同源载荷：批明细、三方汇总、差异列表、运行历史、批头审计。"""
    conn = connect()
    try:
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        strategy = get_strategy(conn)
        res = compute(conn, batch)
        status = batch["status"]
        can_override = strategy == STRATEGY_EVENTS and status == "disputed"
        can_unseal = status == "sealed" or (status == "disputed" and strategy == STRATEGY_BATCH)
        return {
            "strategy": strategy,
            "batch": batch,
            "summary": res,
            "facts": fact_repo.facts_for_batch(conn, batch_id),
            "runs": recon_repo.runs_for_batch(conn, batch_id),
            "audits": recon_repo.audits_for_batch(conn, batch_id),
            "can_override": can_override,
            "can_unseal": can_unseal,
        }
    finally:
        conn.close()
