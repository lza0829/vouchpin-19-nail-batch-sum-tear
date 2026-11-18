"""钉后互证场景核对：人为制造三类分叉（改事件额 / 删事实行 / 只改批头），
分别核对「以事件湖重算为准」(events) 与「以批头+明细为准」(batch) 两策略。

运行：python tests/recon_scenarios.py   （使用独立临时 DATA_DIR，不碰真实库）
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="vouchpin-recon-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from app.seed import seed_if_empty  # noqa: E402
from app.db import connect  # noqa: E402
from app.services import (  # noqa: E402
    catalog_service,
    event_service,
    recon_service,
    redeem_service,
    settings_service,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def expect_409(name: str, fn) -> str:
    try:
        fn()
    except HTTPException as e:
        check(name, e.status_code == 409, f"(got {e.status_code}: {e.detail})")
        return str(e.detail)
    check(name, False, "(no exception)")
    return ""


def fresh_sealed_day(day: str, n: int = 3, amt: float = 10.0) -> int:
    """开新业务日，写 n 笔核销并钉扎，返回批次 id。"""
    settings_service.set_day({"business_day": day})
    for i in range(n):
        event_service.add_event({
            "event_type": "redeem",
            "coupon_code": f"T-{day}-{i}",
            "campaign_code": "NEW10",
            "amount": amt,
            "business_day": day,
        })
    return int(redeem_service.seal({"business_day": day})["batch_id"])


def db(fn):
    conn = connect(immediate=True)
    try:
        out = fn(conn)
        conn.commit()
        return out
    finally:
        conn.close()


def first_fact_of_batch(bid: int) -> dict:
    return db(lambda c: dict(c.execute(
        "SELECT * FROM redeem_facts WHERE batch_id=? ORDER BY id LIMIT 1", (bid,)).fetchone()))


def batch_row(bid: int) -> dict:
    return db(lambda c: dict(c.execute("SELECT * FROM redeem_batches WHERE id=?", (bid,)).fetchone()))


def buckets_of(detail: dict) -> set[str]:
    return {d["bucket"] for d in detail["summary"]["diffs"]}


def dash_state(day: str) -> dict:
    settings_service.set_day({"business_day": day})
    return catalog_service.dashboard()


def scenario_events_tampered(day: str) -> None:
    """分叉一：改事件额（事件湖金额被改，批头/事实不变）——策略 A。"""
    print(f"== 场景① 改事件额 · 策略 events (day={day}) ==")
    bid = fresh_sealed_day(day)
    fact = first_fact_of_batch(bid)
    db(lambda c: c.execute("UPDATE coupon_events SET amount=15 WHERE id=?", (fact["event_id"],)))

    r = recon_service.run(bid)
    check("互证判分叉", r["batch_status"] == "disputed" and not r["consistent"])
    check("差异含金额桶", "amount" in buckets_of(recon_service.detail(bid)))

    d = dash_state(day)
    check("总览不当正常已钉", d["current_batch"]["status"] == "disputed" and d["day_disputed"])
    check("总览差异态", d["current_batch"]["recon_state"] == "diverged")

    expect_409("争议期间禁止再钉第二份 sealed", lambda: redeem_service.seal({"business_day": day}))
    expect_409("争议期间禁止再写核销事件", lambda: event_service.add_event({
        "event_type": "redeem", "coupon_code": "X-1", "campaign_code": "NEW10",
        "amount": 10, "business_day": day}))
    expect_409("争议批禁止解钉（只读）", lambda: recon_service.unseal(bid))

    r = recon_service.override_header(bid)
    b = batch_row(bid)
    check("覆盖后批头=事件重算", b["total_amount"] == 35.0 and b["fact_count"] == 3, f"(got {b})")
    check("旧批头已留痕", db(lambda c: c.execute(
        "SELECT COUNT(*) n FROM batch_header_audits WHERE batch_id=? AND old_total_amount=30 AND new_total_amount=35",
        (bid,)).fetchone()["n"]) == 1)
    check("事实侧仍分叉→仍争议", r["batch_status"] == "disputed")

    db(lambda c: c.execute("UPDATE redeem_facts SET amount=15 WHERE id=?", (fact["id"],)))
    r = recon_service.run(bid)
    check("修复事实后复跑→回 sealed", r["batch_status"] == "sealed" and r["consistent"])
    check("总览恢复正常", dash_state(day)["current_batch"]["recon_state"] == "ok")


def scenario_fact_deleted(day: str) -> None:
    """分叉二：删事实行（批内事实缺失，批头/事件不变）——策略 A。"""
    print(f"== 场景② 删事实行 · 策略 events (day={day}) ==")
    bid = fresh_sealed_day(day)
    fact = first_fact_of_batch(bid)
    db(lambda c: c.execute("DELETE FROM redeem_facts WHERE id=?", (fact["id"],)))

    r = recon_service.run(bid)
    det = recon_service.detail(bid)
    check("互证判分叉→争议", r["batch_status"] == "disputed")
    bs = buckets_of(det)
    check("差异含笔数/金额/缺事实三桶", {"count", "amount", "missing_fact"} <= bs, f"(got {bs})")
    check("缺事实定位到券码", any(d["coupon_code"] == fact["coupon_code"] for d in det["summary"]["diffs"]))

    r = recon_service.override_header(bid)
    check("批头本就等于事件重算→无审计行", db(lambda c: c.execute(
        "SELECT COUNT(*) n FROM batch_header_audits WHERE batch_id=?", (bid,)).fetchone()["n"]) == 0)
    check("覆盖不能抹平事实缺失→仍争议", r["batch_status"] == "disputed")

    db(lambda c: c.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, batch_id, status)"
        " VALUES(?,?,?,?,?,?,'sealed')",
        (fact["coupon_code"], fact["campaign_code"], fact["amount"], fact["business_day"], fact["event_id"], bid)))
    r = recon_service.run(bid)
    check("补回事实后复跑→回 sealed", r["batch_status"] == "sealed" and r["consistent"])


def scenario_header_tampered(day: str) -> None:
    """分叉三：只改批头（事件/事实一致，批头被改）——策略 A。"""
    print(f"== 场景③ 只改批头 · 策略 events (day={day}) ==")
    bid = fresh_sealed_day(day)
    db(lambda c: c.execute("UPDATE redeem_batches SET total_amount=999 WHERE id=?", (bid,)))

    r = recon_service.run(bid)
    check("互证判分叉→争议", r["batch_status"] == "disputed")
    check("差异仅金额桶（笔数未动）", buckets_of(recon_service.detail(bid)) == {"amount"})

    r = recon_service.override_header(bid)
    b = batch_row(bid)
    check("覆盖后批头恢复 30 且回 sealed", b["total_amount"] == 30.0 and r["batch_status"] == "sealed")
    check("留痕 999→30", db(lambda c: c.execute(
        "SELECT COUNT(*) n FROM batch_header_audits WHERE batch_id=? AND old_total_amount=999 AND new_total_amount=30",
        (bid,)).fetchone()["n"]) == 1)


def scenario_batch_strategy(day1: str, day2: str, day3: str) -> None:
    """策略 B（以批头+明细为准）：报告只读、不改批头、差异未清禁止重钉（解钉类改写除外）。"""
    settings_service.set_strategy({"strategy": "batch"})

    print(f"== 策略 batch · 改事件额 (day={day1}) ==")
    bid = fresh_sealed_day(day1)
    fact = first_fact_of_batch(bid)
    db(lambda c: c.execute("UPDATE coupon_events SET amount=15 WHERE id=?", (fact["event_id"],)))

    r = recon_service.run(bid)
    b = batch_row(bid)
    check("报告判分叉", not r["consistent"] and r["strategy"] == "batch")
    check("批状态保持 sealed（只读报告）", b["status"] == "sealed")
    check("批头不被改写", b["total_amount"] == 30.0)
    check("差异落库", db(lambda c: c.execute(
        "SELECT COUNT(*) n FROM recon_diffs WHERE run_id=?", (r["run_id"],)).fetchone()["n"]) > 0)
    d = dash_state(day1)
    check("总览显示有差异而非全正常", d["current_batch"]["recon_state"] == "diverged")
    expect_409("策略 B 禁止事件覆盖批头", lambda: recon_service.override_header(bid))

    recon_service.unseal(bid)
    check("解钉类改写被允许", batch_row(bid)["status"] == "voided")
    msg = expect_409("差异未清禁止重钉", lambda: redeem_service.seal({"business_day": day1}))
    check("拦截文案指向差异未清", "差异未清" in msg, f"(got {msg})")

    db(lambda c: c.execute("UPDATE coupon_events SET amount=10 WHERE id=?", (fact["event_id"],)))
    r2 = redeem_service.seal({"business_day": day1})
    check("差异修复后重钉放行", r2["status"] == "sealed" and r2["batch_id"] != bid)

    print(f"== 策略 batch · 删事实行 (day={day2}) ==")
    bid2 = fresh_sealed_day(day2)
    f2 = first_fact_of_batch(bid2)
    db(lambda c: c.execute("DELETE FROM redeem_facts WHERE id=?", (f2["id"],)))
    r = recon_service.run(bid2)
    bs = buckets_of(recon_service.detail(bid2))
    check("删事实→三桶齐全且批头不动", {"count", "amount", "missing_fact"} <= bs
          and batch_row(bid2)["fact_count"] == 3 and batch_row(bid2)["status"] == "sealed")

    print(f"== 策略 batch · 只改批头 (day={day3}) ==")
    bid3 = fresh_sealed_day(day3)
    db(lambda c: c.execute("UPDATE redeem_batches SET total_amount=999 WHERE id=?", (bid3,)))
    r = recon_service.run(bid3)
    check("批头被改→报告分叉但系统不回写", not r["consistent"] and batch_row(bid3)["total_amount"] == 999.0)
    check("差异未清时解钉仍允许", recon_service.unseal(bid3)["status"] == "voided")
    expect_409("差异未清禁止重钉", lambda: redeem_service.seal({"business_day": day3}))
    db(lambda c: c.execute("UPDATE redeem_batches SET total_amount=30 WHERE id=?", (bid3,)))
    check("批头修复后重钉放行", redeem_service.seal({"business_day": day3})["status"] == "sealed")

    settings_service.set_strategy({"strategy": "events"})


def main() -> int:
    seed_if_empty()
    settings_service.set_strategy({"strategy": "events"})
    scenario_events_tampered("2026-11-11")
    scenario_fact_deleted("2026-11-12")
    scenario_header_tampered("2026-11-13")
    scenario_batch_strategy("2026-11-14", "2026-11-15", "2026-11-16")

    bad = settings_service.get_strategy()
    check("策略全局互斥且可切换回 events", bad["strategy"] == "events" and set(bad["options"]) == {"events", "batch"})
    try:
        settings_service.set_strategy({"strategy": "both"})
        check("非法策略被拒绝", False)
    except HTTPException:
        check("非法策略被拒绝", True)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
