# 记忆运营监控平台（memory-platform）

任务3 正式项目：查看用户记忆纳入情况的**只读**运营监控平台。三页结构（概览统计 / 纳入明细 / 记忆清单），企业蓝视觉（与 design-demos/ops-monitor-v1.html 视觉稿 1:1）。

## 架构

```
Vue3 前端 (:5174) ──/api──> FastAPI BFF (:8002，只读) ──SQL SELECT──> GM Postgres (:5433)
```

- **零改 GM**：不依赖 GM API/Worker 进程，不写库，全部查询为 SELECT。
- **口径来源**：漏斗与纳入结果全部取自 GM 审计码（CONVERSATION_INGESTED / SCOPE_UNRESOLVED / FACT_EXTRACTED / FACT_SUPERSEDED / FACT_DISPUTED）与表计数，非硬编码。
- **Element Plus 暂未引入**：为与验收视觉稿 1:1，沿用自定义企业蓝 CSS；后续需要复杂表单控件时再引入。

## 目录

```
memory-platform/
├── server/               # FastAPI 只读 BFF
│   ├── main.py           # 全部端点与 SQL
│   ├── requirements.txt  # fastapi / uvicorn / psycopg[binary]
│   └── .venv/
├── frontend/             # Vue3 + Vite
│   ├── src/App.vue       # 顶栏/左导航/三页切换（hash 路由 #page=）
│   ├── src/views/Overview.vue   # 概览统计（统计卡/漏斗/分布/趋势）
│   ├── src/views/Intake.vue     # 纳入明细（列表+抽取过程抽屉）
│   ├── src/views/MemList.vue    # 记忆清单（列表+记忆详情抽屉）
│   └── src/api.js, style.css
├── design-demos/         # 视觉原型（ops-monitor-v1.html + B-enterprise-blue-v2.html）
├── db-mapping.md                 # 界面↔GM库表映射矩阵
├── design-alignment.md           # 管理平台方案对齐（任务5评审材料）
└── gm-config-evolution-design.md # GM配置演进设计稿（任务5，未动GM代码）
```

## 启动

```bash
# 1. BFF（:8002）
cd memory-platform/server
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002

# 2. 前端（:5174，代理 /api → :8002）
cd memory-platform/frontend
node node_modules/vite/bin/vite.js
```

打开 http://127.0.0.1:5174 （GM Postgres 容器 memory-cmic-postgres 需在运行）。

## BFF 端点

| 端点 | 说明 |
|---|---|
| GET /api/health | 连通性检查 |
| GET /api/overview | 统计卡 + 漏斗（审计码口径）+ 纳入结果分布 + 按日趋势 |
| GET /api/sources?outcome=&q= | 纳入明细列表（outcome=ok/mg/scope/none） |
| GET /api/sources/{id} | 抽取过程：原文/范围解析/抽取任务(含模型输入)/证据产出/审计 |
| GET /api/memories?type=&q= | 记忆清单 |
| GET /api/memories/{id} | 记忆详情：字段/来源追溯/向量/审计 |

## 说明

- 数据库连接串从环境变量 `OPS_DATABASE_URL` 读取，默认取 GM .env 中的本地开发库（只读使用）。
- 纳入明细的"产出"= 证据链产出过的记忆条目数；"现存"= 其中仍为 active 的条目。
- 管理平台（配置平面）已按 2026-10-10 用户决策后置为项目任务5，相关设计稿见本目录。
