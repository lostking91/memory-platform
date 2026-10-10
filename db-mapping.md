# 管理平台 ↔ GM 数据库映射矩阵（开发依据 v1）

> 2026-10-09 用户决策：**管理平台不走 GM HTTP API，直连 GM 数据库（Postgres :5433 / 容器内 5432），界面与 GM 库表字段一一对应。**
> 2026-10-09 18:23 用户决策：**单租户先行**，tenant_id 由 BFF 固定为 `cmic-yun`，界面不出现租户概念；GM 表保留 tenant_id 列仅为顺应其全表架构约定。
> 本文档为确认稿：§3 为待确认决策点，确认后才进入开发。
> 数据源实测：tenant 单值 `cmic-yun`；memory_item 6、source_record 31、memory_task 21、memory_evidence 18、memory_embedding 6、memory_audit_log 134、business_scene 4、governance_pending 6、profile_property 0、governance_policy 0、governance_operation 0、consolidate 任务 0。

## 1. 架构（待确认 Q1）

推荐：独立 BFF 服务（FastAPI，`memory-platform/server/`），持 PG 连接串直读直写；Vue3 前端只调 BFF。
- 读：SQL 直查（聚合/分页/过滤）。
- 写：**import GM 既有 Python 函数**（`memory_cmic.consolidation.revert_operation`、`governance_state.create_run/ensure_policy`、`lifecycle.invalidate_memory/expire_memory`、ingest 写入链），不重写事务、零改 GM 代码。BFF 复用 GM `.venv` 依赖或同版本安装。
- 检索：BFF import `memory_cmic.retrieval.search_memories`（含意图识别/改写/排序开关），见 Q3。
- 不推荐：前端直连 PG（暴露凭证/无事务封装）；复用 GM API（用户已否决）。

## 2. GM 全表清单（15 表）与界面归属

| 表 | 行数 | 界面归属 |
|---|---|---|
| memory_item | 6 | Tab2 主体（事实/推断/技能记忆）、Tab4 操作对象 |
| profile_property | 0 | Tab2 画像 Tab（空态） |
| source_record | 31 | 证据链展示（记忆→原始对话出处） |
| memory_evidence | 18 | 证据链（supports/derives/profile_basis） |
| memory_embedding | 6 | Tab3 检索向量源（pgvector cosine） |
| memory_task | 21 | Tab4 整合任务列表（task_type=consolidate）；其余类型为系统任务可作审计视角 |
| memory_task_source | 28 | 任务↔source 关联（任务详情溯源） |
| governance_policy | 0 | Tab4 治理策略 7 字段（0 行=未初始化，显示默认值，保存即 upsert） |
| governance_operation | 0 | Tab4 任务详情操作记录 + 回滚对象 |
| governance_pending | 6 | Tab4「待整合队列」面板（GM 原生概念，v2 原型没有，建议新增） |
| governance_subject_state | 1 | Tab4 辅助展示（last_add_at/last_run_at） |
| memory_audit_log | 134 | 左导航「记忆审计」页（建议做实，v2 为占位） |
| conversation_session | 8 | 不直接上界面（任务详情可显示 session_id） |
| business_scene | 4 | Tab3/整合上下文展示（范围词典：email/disk/communication/方案编写） |
| migration.external_entity_mapping | 0 | 不上界面（迁移用） |

## 3. 界面字段 ↔ 表字段映射

### Tab2 记忆详情
- 四宫格：事实记忆数=`count(memory_item: cognitive_type in (fact,inference) and status=active)`（含推断角标）；画像数=`count(profile_property: status=active)`；技能数=`count(memory_item: cognitive_type=skill and status=active)`；实体数=`count(distinct (subject_type,subject_id): status=active)`。
- 实体表：按 `(subject_type, subject_id)` 分组；列=subject_type / subject_id（真实值如 `gm_user_lw`，弃用 Mock 的 laowang-001）/ max(updated_at) / 各类型计数。
- 实体抽屉-事实/技能列表：memory_item 行字段 → 界面：summary+content→内容卡；cognitive_type→类型 chip（inference→紫色「推断」角标）；confidence→置信度；status→状态 chip（active/invalidated/disputed/expired）；version、effective_at、expired_at、invalidated_at、created_by、supersedes_id、conflict_group_id、business_domains、project_domains、metadata(temporal_kind/project_context/governance_action)→详情区。
- 实体抽屉-画像列表：profile_property → property_key=字段名、property_value=值、value_type、confidence、status、version、effective_at。
- 证据链（抽屉内新增折叠区）：memory_evidence(supports)→source_record.raw_content/occurred_at/author_type；derives→上游 memory_item.summary。

### Tab3 记忆检索
- 配置区：记忆类型/规则/最大召回数量/意图识别/改写/排序/输入 → 对应 `retrieval.search_memories(...)` 入参（top_k、intent、rewrite、rerank 开关）；向量计算落 memory_embedding（pgvector hnsw cosine）。
- 结果区：命中 memory_item 字段同 Tab2 卡片 + score。

### Tab4 记忆治理
- 策略表单 7 字段 = governance_policy 列一一对应：auto_enabled（开关）、change_threshold、idle_minutes、cooldown_minutes、max_wait_minutes、max_memories、max_model_calls；version/updated_at 只读展示。0 行时显示 GM 默认值（5/10/60/360/100/10）+「未初始化」提示；保存=upsert 且 version+1。
- 手动触发整合 = `create_run(automatic=False, trigger_reason='manual')` → 插入 memory_task(consolidate)。
- 任务列表 = memory_task where task_type=consolidate：列 id/user_id/status/trigger(payload.automatic→自动|手动)/created_at；进度列取 payload 运行时字段：selected=len(payload.selection)、processed=payload.cursor、remaining=payload.remaining、model_calls=payload.model_calls、token_usage=payload.token_usage（未运行时为空）。
- 任务详情抽屉：任务概要=memory_task 行（status/created_at/completed_at/attempt_count/last_error/error）；操作记录=governance_operation where task_id：kind(merge/inference/invalidate/rejection)+memory_id+details(content/winner_id/loser_id/source_ids)+created_at+reverted_at。
- 回滚按钮 = `revert_operation(expected_version=details 内版本, operator_id, reason)`；仅 merge/inference/invalidate 且 reverted_at 为空可回滚（GM 硬约束，界面据此禁用按钮）。
- 待整合队列面板（新增）：governance_pending 6 行 → user_id/memory_id(关联 summary)/generation/first_change_at。

### 左导航「记忆审计」页（新增做实）
memory_audit_log：action(INSERT/UPDATE/INVALIDATE/EXPIRE/DELETE/MIGRATE)/target_type/target_id/operator_type/operator_id/reason_code/reason/state_before/state_after/created_at；按 target 过滤+时间倒序+分页。

### Tab1 记忆规则（待确认 Q2）
GM 库**无任何规则表**（规则=百炼产品概念：抽取指令/过期时间/Pro·Lite/画像字段表）。三选一见 Q2。

## 4. 写操作清单（事务边界=GM 函数）

| 界面操作 | 落表 | 实现 |
|---|---|---|
| 治理策略保存 | governance_policy | ensure_policy + update（version+1） |
| 手动触发整合 | memory_task | governance_state.create_run |
| 操作回滚 | memory_item/memory_evidence/governance_operation/memory_task | consolidation.revert_operation |
| 记忆删除(失效) | memory_item/evidence/audit + vector_delete 任务 | lifecycle.invalidate_memory |
| 写入记忆数据 | source_record→memory_task(fact_extract)→memory_item | ingest 写入链（对应 GM memories:add 语义） |
| 规则 CRUD | 无表（Q2 定） | 前端配置/新表 |

## 5. 待确认决策点（Q1-Q4 见对话提问）

- Q1 数据访问架构：独立 BFF（推荐）/ 前端直连 PG / 复用 GM API。
- Q2 规则 Tab：纯前端配置+标注无 GM 表（推荐）/ GM 库新建 memory_rule 表 / 砍掉规则 Tab。
- Q3 检索 Tab：BFF import retrieval.py（推荐）/ BFF 自写 pgvector cosine / 检索改只读展示。
- Q4 开发顺序：直接 Vue3+BFF 正式项目（推荐）/ 先出接真数据的 v3 HTML / Vue 先全 Mock 后接 BFF。
- 默认决定（不另问，可否决）：Mock 数据全部替换为真实库数据；左导航「记忆审计」做实、「服务渠道/用量」保持占位；governance_policy 0 行显示默认值+未初始化提示；写/回滚一律 import GM 函数不重写 SQL 事务。
