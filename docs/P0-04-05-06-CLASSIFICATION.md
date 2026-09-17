# Feature Classification Gate (pre-code, per task order)

Feature: **P0-04 Device Registration API / P0-05 Member CRUD / P0-06 Manual Device Assignment Service**

Classification: **OPEN**

Reason: 基础设备注册、成员管理、人工确定性 assignment，属于 CostGuard Split
Foundation。不包含 proprietary attribution / reconciliation / optimization；
assignment 永远是人工确定性事务（explicit member_id + timeline overlap 校验），
归属查询是纯区间查找（member_at）。

Public repo allowed: **YES**

Commercial risk: **LOW**

Server-side required: **YES** — authorization / tenant boundary /
canonical assignment 必须在 server 侧成立（本轮以明确的 server-context
抽象表达，不伪造真实用户体系）。

## 明确禁止（本轮不实现，出现需求即 STOP 报告分类冲突）
- automatic attribution（任何形式的自动归属判断）
- device lineage intelligence
- behavioral scoring / proprietary confidence algorithm
- quota pressure / reconciliation / optimization / benchmark
- recommendation engine / private SaaS business logic
- Auth0 / Clerk / Stripe / 完整登录系统 / Dashboard / 支付 / Web frontend

## API framework decision
项目当前 dependencies = []（stdlib only）。FastAPI 0.133.1 已存在于本机
环境且 pydantic v2 可用。决策：**server API layer 采用 FastAPI（可选依赖），
但放置在独立 extras（`pip install costguard-agent[split-server]`），
核心 `costguard_split` 包保持零依赖、零网络不变** —— API 层是边界适配器，
domain/service 层不 import fastapi；测试在 FastAPI 缺失时 skip，
保证 wheel 核心 contract 测试与框架解耦。

## Endpoints（本轮实现）
- POST /api/v1/devices/register
- GET  /api/v1/devices/{device_id}
- POST /api/v1/members
- GET  /api/v1/members
- GET  /api/v1/members/{member_id}
- PATCH /api/v1/members/{member_id}
- POST /api/v1/devices/{device_id}/assignments

无 DELETE（member 用 disable；assignment 历史不可删）。
