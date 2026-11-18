# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 过期/退回窗（后挖）→ 批次互证。

## 钉后互证（三方对账）

钉扎后事件湖合计、事实表合计、批头 `total_amount` 可能分叉。系统以**全局互斥**的权威策略只贯彻一种（设置页切换，即时生效）：

- **以事件湖重算为准（events，默认）**：按批业务日从 redeem/void 事件重算期望合计与笔数；与批头不一致则批标记 `disputed`，总览不得当正常已钉。可按事件重算覆盖批头（旧批头入 `batch_header_audits` 留痕）或保持争议只读；争议期间禁止对该日再钉出第二份现行 sealed，争议批亦禁止解钉。
- **以批头+明细为准（batch）**：互证报告只读对比事件/事实，分叉只出差异报告（笔数/金额/缺事件/缺事实分桶，落 `recon_runs`/`recon_diffs`），不改 sealed 批头；差异未清前禁止对该日解钉类改写以外的重钉。

互证任务（互证页「运行互证」）、批状态、事件重算、事实汇总、批明细、总览现行批、差异列表全部同源（`recon_service.compute` 实时三方比对）：分叉的批在任何页面都不会显示为完全正常的已钉。

API：
- `POST /api/batches/{id}/recon` 运行互证；`GET /api/batches/{id}/recon` 互证详情（汇总/差异/批明细/运行历史/批头审计）
- `POST /api/batches/{id}/override` 按事件重算覆盖批头（仅 events 策略 + 争议批）
- `POST /api/batches/{id}/unseal` 解钉（sealed→voided，事实回 open）
- `GET/PUT /api/settings/strategy` 查看/切换策略（`events` | `batch`）

场景核对（三类人为分叉 × 两策略，39 项断言）：
`cd backend && python tests/recon_scenarios.py`

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
