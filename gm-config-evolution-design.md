# GM 配置能力演进设计稿（v1 · 仅设计，未动任何 GM 代码）

> 2026-10-09 立项意图：让"智能体触发记忆时按管理平台配置执行提取与使用"落地，GM 需从"行为硬编码"演进为"配置驱动"。
> 原则：①新增表零依赖，不动现有 15 张表；②所有改造遵循"配置缺失即回退当前硬编码行为"，零迁移上线；③单租户先行，表保留 tenant_id 列仅顺应 GM 全表惯例。

## 1. 新增配置表（3 张必选 + 1 张可选）

### T1 tenant_extract_config 提取配置（配置域 C1）

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| tenant_id | varchar(64) PK | — | 固定 cmic-yun |
| fact_enabled | boolean | true | 事实记忆提取开关 |
| inference_enabled | boolean | true | 推断生成开关（consolidate 的 _infer） |
| skill_enabled | boolean | false | 技能记忆提取开关 |
| prompt_suffix | text | null | **追加式**租户提取指令（拼在默认提示词后，非整体替换） |
| scope_exemptions | jsonb | null | 范围豁免清单（现硬编码：身份/生日/居住地） |
| input_token_budget | int | 12000 | 覆盖 env MEMORY_MODEL_INPUT_TOKENS |
| output_token_budget | int | 2048 | 同上 |
| max_model_calls | int | 20 | 单任务模型调用上限 |
| extraction_model | varchar(128) | null | 覆盖默认 qwen3.8-max |
| duplicate_threshold | numeric | 0.85 | 去重候选阈值（现全局 env） |
| version / updated_at | int / timestamptz | 1 / now | |

消费点：worker.py（类型开关检查）、providers.py（提示词追加+豁免清单）、extraction_input.py（预算来源改为 T1 > env）。

### T2 tenant_retrieval_config 检索配置（C4）

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| tenant_id | varchar(64) PK | — | |
| default_top_k | int | 10 | 召回上限 |
| applicability_enabled | boolean | true | 语义适用性判定开关 |
| applicability_model | varchar(128) | null | 判定模型 |
| candidate_multiplier | int | 3 | 候选放大倍数 |
| similarity_threshold | numeric | null | 相似度过滤（现无此能力，新增） |
| allowed_business_domains | varchar(32)[] | null | 召回范围限制 |
| version / updated_at | | | |

消费点：retrieval.py search_memories——入参保留，缺省值改读 T2（调用方显式传参仍可覆盖）。

### T3 profile_schema 画像字段定义（C6）

| 列 | 类型 | 说明 |
|---|---|---|
| tenant_id + property_key | PK | |
| display_name | varchar(64) | 字段显示名 |
| value_type | varchar(16) | string/number/boolean/list/object |
| description | varchar(512) | 字段说明（进画像重建提示词） |
| enabled | boolean | 停用字段不再参与 profile_rebuild |
| position | int | 排序 |
| created_at / updated_at | | |

消费点：profile.py 硬编码字段清单处。种子迁移：从 profile.py 现有硬编码清单自动生成初始行，保证 profile_rebuild 行为不变。

### T4（可选）tenant_lifecycle_config 生命周期策略（C3）

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| tenant_id | PK | | |
| ttl_by_type | jsonb | null | {"fact": null, "inference": 30, "skill": null}，单位天；null=不过期 |
| ttl_scan_enabled | boolean | true | ttl_expire 扫描开关 |

消费点：提取时模型未给出 expired_at 则按策略兜底；governance_worker 扫描读取。

## 2. 新增 HTTP 端点（1 个）

`POST /v1/memories/search`（api.py）：
- 入参：query、user_id、business_domain、project_id?、top_k?（覆盖 T2 缺省）
- 行为：bge-m3 向量化 → pgvector 余弦（memory_embedding）→ 按 T2 配置召回
- 鉴权：复用现有 StaticCredentialStore 凭证
- 意义：管理平台"检索调试"页与管理平台外调用方共用；此前已确认"检索接口后续建设"即指此。

## 3. 执行侧改造点清单

| 文件 | 改造 | 风险 |
|---|---|---|
| providers.py | 提示词追加 prompt_suffix；豁免清单读 T1 | 低（追加式不改默认提示词） |
| worker.py | fact_extract 前按 T1 检查类型开关/预算/模型 | 低 |
| extraction_input.py | 预算优先级 T1 > env | 低 |
| retrieval.py | 缺省参数读 T2 | 低（入参显式传参仍优先） |
| api.py | 新增 search 端点 | 中（新端点+embedder 依赖） |
| profile.py | schema 读 T3（种子迁移保底） | 中（profile_rebuild 回归） |
| governance_worker.py | TTL 扫描读 T4 | 低 |

## 4. 兼容与迁移策略

1. 4 张表均为新增，无外键依赖现有表，可单独上线；
2. 每表"未插行/字段为 null → 完全回退当前硬编码行为"，对现网 ai-assistant 写入链路零影响；
3. T3 附带种子迁移（从 profile.py 硬编码生成），其余表可不插行；
4. 表均带 version，管理平台保存时 +1，为后续审计留钩子。

## 5. 工作量粗估（含自测回归）

- 建表+迁移：0.5 人日
- T1 提取链改造：1-1.5 人日（提示词追加式，重点回归 SCOPE_UNRESOLVED 行为）
- T2+search 端点：1-1.5 人日
- T3 画像 schema 化：1 人日
- T4：0.5 人日（可选）
- 合计：约 4-5 人日；分期可按 T1 → T3 → T2+端点 → T4 顺序独立交付。

## 6. 待决策

1. 4 张表方案是否认可？有无要增删的配置项？
2. prompt_suffix 采用"追加式"而非"整体替换"，是否接受（更安全）？
3. T4 本期是否要（也可并入 T1 一列）？
4. 排期：等管理平台 Phase A 之后再做，还是并行？
