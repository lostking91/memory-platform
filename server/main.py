"""记忆运营监控平台 BFF —— 只读直连 GM Postgres，零改 GM 代码。

数据源：GeneralMemory-2.1.0 Postgres（docker memory-cmic-postgres，宿主端口 5433）
约束：所有查询均为 SELECT，不写库、不改 GM、不依赖 GM 进程。
"""
import os
from collections import Counter
from datetime import timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException

DATABASE_URL = os.environ.get(
    "OPS_DATABASE_URL",
    # 注意：必须用 127.0.0.1 而非 localhost——Windows 上 localhost 先解析 IPv6(::1)
    # 连不上 Docker 映射端口，每次新建连接都要空等约 5 秒超时才回落 IPv4。
    "postgresql://memory_cmic:memory_cmic_local_dev@127.0.0.1:5433/memory_cmic",
)
TZ8 = timezone(timedelta(hours=8))

app = FastAPI(title="记忆运营监控平台 BFF（只读）")


def query(sql: str, args: tuple = ()) -> List[Dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()


def fmt(dt: Optional[Any], full: bool = False) -> str:
    if dt is None:
        return "--"
    try:
        d = dt.astimezone(TZ8)
        return d.strftime("%Y-%m-%d %H:%M" if full else "%m-%d %H:%M")
    except Exception:
        return str(dt)


def fmt_day(dt: Optional[Any]) -> str:
    if dt is None:
        return "--"
    try:
        return dt.astimezone(TZ8).strftime("%m-%d")
    except Exception:
        return str(dt)


def audit_counts() -> Dict[str, int]:
    rows = query("SELECT reason_code, count(*) c FROM memory_audit_log GROUP BY 1")
    return {r["reason_code"]: r["c"] for r in rows}


# ---------------- 概览统计 ----------------

@app.get("/api/overview")
def overview():
    audit = audit_counts()
    saved = query("SELECT count(*) c FROM source_record")[0]["c"]
    ingest = audit.get("CONVERSATION_INGESTED", 0)
    unresolved = audit.get("SCOPE_UNRESOLVED", 0)
    extracted = query(
        "SELECT count(DISTINCT target_id) c FROM memory_audit_log WHERE reason_code='FACT_EXTRACTED'"
    )[0]["c"]
    active = query("SELECT count(*) c FROM memory_item WHERE status='active'")[0]["c"]
    superseded = audit.get("FACT_SUPERSEDED", 0)
    disputed = audit.get("FACT_DISPUTED", 0)
    entities = query("SELECT count(DISTINCT subject_id) c FROM memory_item")[0]["c"]
    pending = query("SELECT count(*) c FROM memory_task WHERE status='pending'")[0]["c"]
    evidence = query("SELECT count(*) c FROM memory_evidence WHERE status='active'")[0]["c"]

    resolved = saved - unresolved
    rate = round(active / saved * 100, 1) if saved else 0.0

    # 来源级纳入结果分布（与明细页同口径）
    srcs = _all_sources()
    dist = Counter(s["outcome"] for s in srcs)

    trend = _trend()

    funnel = [
        {
            "key": "ingest", "label": "对话消息入库（CONVERSATION_INGESTED）", "table": "memory_audit_log",
            "value": ingest,
            "leak": ingest - saved, "leak_note": "入库去重/清理，无 source_record 存留",
        },
        {
            "key": "saved", "label": "写入保存（source_record）", "table": "source_record",
            "value": saved, "conv": round(saved / ingest * 100, 1) if ingest else 0,
            "leak": unresolved, "leak_note": "范围未解析 SCOPE_UNRESOLVED",
        },
        {
            "key": "resolved", "label": "范围解析通过", "table": "source_record（非 SCOPE_UNRESOLVED）",
            "value": resolved, "conv": round(resolved / saved * 100, 1) if saved else 0,
            "leak": resolved - resolved, "leak_note": "",
        },
        {
            "key": "extracted", "label": "抽取产出记忆（FACT_EXTRACTED）", "table": "memory_audit_log",
            "value": extracted, "conv": 100.0 if resolved else 0,
            "leak": superseded + disputed + (extracted - superseded - disputed - active),
            "leak_note": "失效替代 %d · 争议失效 %d · 合并/清理 %d" % (
                superseded, disputed, extracted - superseded - disputed - active),
        },
        {
            "key": "active", "label": "现存记忆（memory_item active）", "table": "memory_item",
            "value": active,
            "conv": round(active / extracted * 100, 1) if extracted else 0,
        },
    ]

    reasons = [
        {"label": "范围未解析", "value": unresolved, "cls": "b-er"},
        {"label": "无可抽取内容", "value": dist.get("none", 0), "cls": "b-gray"},
        {"label": "重复合并/失效清理", "value": dist.get("mg", 0), "cls": "b-blue"},
        {"label": "（对照）已纳入来源", "value": dist.get("ok", 0), "cls": "b-wn"},
    ]

    return {
        "stats": {
            "ingest": ingest, "saved": saved, "extracted": extracted, "active": active,
            "rate": rate, "entities": entities, "pending": pending, "evidence": evidence,
        },
        "funnel": funnel,
        "reasons": reasons,
        "reasons_note": "分布为「来源条目」口径（31 条 source_record）；漏斗前两级为消息/条目混合口径，均取自审计码。",
        "trend": trend,
        "tenant": "cmic-yun",
        "refreshed_at": fmt(query("SELECT now() ts")[0]["ts"], full=True),
    }


def _trend() -> List[Dict[str, Any]]:
    src = query(
        "SELECT to_char(created_at AT TIME ZONE 'Asia/Shanghai','MM-DD') d, count(*) c "
        "FROM source_record GROUP BY 1 ORDER BY 1"
    )
    mem = query(
        "SELECT to_char(created_at AT TIME ZONE 'Asia/Shanghai','MM-DD') d, count(*) c "
        "FROM memory_item WHERE status='active' GROUP BY 1 ORDER BY 1"
    )
    sm = {r["d"]: r["c"] for r in src}
    mm = {r["d"]: r["c"] for r in mem}
    # 固定连续 7 天窗口（Asia/Shanghai），缺日补 0，保证前端趋势图坐标稳定
    win = query(
        "SELECT to_char(g,'MM-DD') AS dlabel "
        "FROM generate_series("
        "(now() AT TIME ZONE 'Asia/Shanghai') - interval '6 days', "
        "(now() AT TIME ZONE 'Asia/Shanghai'), interval '1 day') g"
    )
    days = [r["dlabel"] for r in win] or sorted(set(sm) | set(mm))
    return [{"day": d, "saved": sm.get(d, 0), "active": mm.get(d, 0)} for d in days]


# ---------------- 纳入明细 ----------------

_SRC_SQL = """
SELECT s.id, s.raw_content, s.author_type, s.source_system, s.session_id,
       s.occurred_at, s.created_at,
       EXISTS(SELECT 1 FROM memory_audit_log a
              WHERE a.target_type='source' AND a.target_id=s.id
                AND a.reason_code='SCOPE_UNRESOLVED') AS unresolved,
       (SELECT count(DISTINCT e.downstream_memory_id) FROM memory_evidence e
          JOIN memory_item m ON m.id=e.downstream_memory_id AND m.status='active'
          WHERE e.upstream_source_id=s.id AND e.status='active') AS linked_active,
       (SELECT count(DISTINCT e.downstream_memory_id) FROM memory_evidence e
          WHERE e.upstream_source_id=s.id AND e.status='active') AS produced
FROM source_record s
ORDER BY s.created_at DESC
"""


def _all_sources() -> List[Dict[str, Any]]:
    rows = query(_SRC_SQL)
    out = []
    for r in rows:
        if r["unresolved"]:
            outcome = "scope"
        elif r["linked_active"] > 0:
            outcome = "ok"
        elif r["produced"] > 0:
            outcome = "mg"
        else:
            outcome = "none"
        out.append({
            "id": r["id"],
            "content": (r["raw_content"] or "").strip().replace("\n", " "),
            "author_type": r["author_type"],
            "source_system": r["source_system"],
            "session_id": r["session_id"],
            "time": fmt(r["created_at"]),
            "produced": r["produced"],
            "stored": r["linked_active"],
            "outcome": outcome,
        })
    return out


@app.get("/api/sources")
def sources(outcome: str = "all", q: str = "", limit: int = 100, offset: int = 0):
    rows = _all_sources()
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["content"].lower() or ql in r["id"].lower()]
    if outcome != "all":
        rows = [r for r in rows if r["outcome"] == outcome]
    total = len(rows)
    return {"total": total, "rows": rows[offset: offset + limit]}


@app.get("/api/sources/{src_id}")
def source_detail(src_id: str):
    src = query("SELECT * FROM source_record WHERE id=%s", (src_id,))
    if not src:
        raise HTTPException(404, "source not found")
    src = src[0]

    src_audits = query(
        "SELECT id, action, reason_code, operator_type, created_at FROM memory_audit_log "
        "WHERE target_type='source' AND target_id=%s ORDER BY id", (src_id,)
    )

    task = query(
        "SELECT t.id, t.status, t.started_at, t.completed_at, t.last_error, t.payload, t.created_at "
        "FROM memory_task t JOIN memory_task_source ts ON ts.task_id=t.id "
        "WHERE ts.source_id=%s ORDER BY t.created_at DESC LIMIT 1", (src_id,)
    )
    model_input: List[Dict[str, Any]] = []
    task_info = None
    if task:
        t = task[0]
        try:
            execution = (t["payload"] or {}).get("execution") or {}
            history = ((execution.get("input") or {}).get("history")) or []
            for h in history[:4]:
                model_input.append({
                    "role": h.get("role", "?"),
                    "content": (h.get("content") or "")[:400],
                })
        except Exception:
            pass
        task_info = {
            "id": t["id"], "status": t["status"],
            "started_at": fmt(t["started_at"], full=True),
            "completed_at": fmt(t["completed_at"], full=True),
            "last_error": t["last_error"],
        }

    products = query(
        "SELECT e.id AS evi_id, e.evidence_snippet, e.upstream_version, e.status AS evi_status, "
        "       m.id AS mem_id, m.summary, m.confidence, m.status AS mem_status, "
        "       m.created_at AS mem_created "
        "FROM memory_evidence e LEFT JOIN memory_item m ON m.id=e.downstream_memory_id "
        "WHERE e.upstream_source_id=%s", (src_id,)
    )

    mem_ids = [p["mem_id"] for p in products if p["mem_id"]]
    mem_audits: List[Dict[str, Any]] = []
    if mem_ids:
        mem_audits = query(
            "SELECT action, reason_code, target_id, created_at FROM memory_audit_log "
            "WHERE target_type='memory' AND target_id = ANY(%s) ORDER BY id", (mem_ids,)
        )

    return {
        "source": {
            "id": src["id"],
            "raw_content": src["raw_content"],
            "author_type": src["author_type"],
            "source_system": src["source_system"],
            "session_id": src["session_id"],
            "occurred_at": fmt(src["occurred_at"], full=True),
            "created_at": fmt(src["created_at"], full=True),
            "status": src["status"],
        },
        "unresolved": any(a["reason_code"] == "SCOPE_UNRESOLVED" for a in src_audits),
        "src_audits": [
            {"action": a["action"], "reason_code": a["reason_code"],
             "operator": a["operator_type"], "time": fmt(a["created_at"], full=True)}
            for a in src_audits
        ],
        "task": task_info,
        "model_input": model_input,
        "products": [
            {"evi_id": p["evi_id"], "snippet": (p["evidence_snippet"] or "")[:400],
             "version": p["upstream_version"], "evi_status": p["evi_status"],
             "mem_id": p["mem_id"], "summary": p["summary"],
             "confidence": float(p["confidence"]) if p["confidence"] is not None else None,
             "mem_status": p["mem_status"], "mem_created": fmt(p["mem_created"], full=True)}
            for p in products
        ],
        "mem_audits": [
            {"action": a["action"], "reason_code": a["reason_code"],
             "target_id": a["target_id"], "time": fmt(a["created_at"], full=True)}
            for a in mem_audits
        ],
    }


# ---------------- 纳入明细（回合化：1 行 = 1 个抽取回合） ----------------
# GM 的抽取粒度是回合级：一次 memories:add = 1 个 fact_extract 任务 = user+agent 两条
# source_record（经 memory_task_source 挂同一 task）。消息级平铺会让 agent 行永远显示
# "无可抽取"（GM 设计：agent 消息只作抽取上下文，禁止独立产出记忆），故按 task 聚合展示。

_TURN_SRC_SQL = """
SELECT s.id, s.raw_content, s.author_type, s.source_system, s.session_id,
       s.message_id, s.occurred_at, s.created_at,
       EXISTS(SELECT 1 FROM memory_audit_log a
              WHERE a.target_type='source' AND a.target_id=s.id
                AND a.reason_code='SCOPE_UNRESOLVED') AS unresolved,
       (SELECT ts.task_id FROM memory_task_source ts
          JOIN memory_task t ON t.id=ts.task_id
         WHERE ts.source_id=s.id AND t.task_type='fact_extract'
         ORDER BY t.created_at DESC LIMIT 1) AS task_id
FROM source_record s
ORDER BY s.created_at
"""


def _session_generation(session_id: Optional[str]) -> int:
    """从 GM 会话 ID 解析轮换代次（ai-assistant 阻断自愈产物：{sid}-g{n}）。"""
    if not session_id:
        return 0
    base, _, suf = session_id.rpartition("-g")
    return int(suf) if base and suf.isdigit() else 0


def _all_turns() -> List[Dict[str, Any]]:
    srcs = query(_TURN_SRC_SQL)
    tasks = {
        t["id"]: t for t in query(
            "SELECT id, status, batch_seq, started_at, completed_at, last_error, error "
            "FROM memory_task WHERE task_type='fact_extract'")
    }
    # 重投检测：同一 message_id 因会话轮换被重投到多代 GM 会话，会产生多条 source_record
    dup = {r["message_id"]: r["c"] for r in query(
        "SELECT message_id, count(*) c FROM source_record "
        "WHERE message_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1")}
    # 证据链（回合级 produced/stored 需在 Python 端做并集去重）
    evi_by_src: Dict[str, List[Dict[str, Any]]] = {}
    for r in query(
        "SELECT e.upstream_source_id sid, e.downstream_memory_id mid, m.status AS mem_status "
        "FROM memory_evidence e LEFT JOIN memory_item m ON m.id=e.downstream_memory_id "
        "WHERE e.status='active'"
    ):
        evi_by_src.setdefault(r["sid"], []).append(r)

    # ---- 分组：有 task 的按 task_id；无 task（SCOPE_UNRESOLVED 等）按同会话就近 user→agent 合并 ----
    by_task: Dict[str, List[Dict[str, Any]]] = {}
    loose: List[Dict[str, Any]] = []
    for s in srcs:
        if s["task_id"] and s["task_id"] in tasks:
            by_task.setdefault(s["task_id"], []).append(s)
        else:
            loose.append(s)
    loose_groups: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for s in loose:  # 已按 created_at 升序
        if (cur and s["author_type"] == "agent" and cur[-1]["author_type"] == "user"
                and s["session_id"] == cur[-1]["session_id"]
                and s["occurred_at"] and cur[-1]["occurred_at"]
                and s["occurred_at"] - cur[-1]["occurred_at"] <= timedelta(seconds=60)):
            cur.append(s)
        else:
            cur = [s]
            loose_groups.append(cur)

    def mk_turn(task_id: Optional[str], ss: List[Dict[str, Any]]) -> Dict[str, Any]:
        task = tasks.get(task_id) if task_id else None
        # 回合级产出：证据链下游记忆并集去重
        mids: Dict[str, Optional[str]] = {}
        for s in ss:
            for r in evi_by_src.get(s["id"], []):
                if r["mid"]:
                    prev = mids.get(r["mid"])
                    # active 状态优先（同一记忆多条证据时取最强状态）
                    if prev is None or (prev != "active" and r["mem_status"] == "active"):
                        mids[r["mid"]] = r["mem_status"]
        produced = len(mids)
        stored = sum(1 for v in mids.values() if v == "active")

        unresolved = all(s["unresolved"] for s in ss)
        task_status = task["status"] if task else None
        error_code = ((task or {}).get("error") or {}).get("code") if task else None

        if unresolved and not task:
            outcome = "scope"
        elif task_status in ("failed", "partial", "cancelled"):
            outcome = "blocked" if error_code == "PRIOR_TASK_FAILED" else "fail"
        elif stored > 0:
            outcome = "ok"
        elif produced > 0:
            outcome = "mg"
        else:
            outcome = "none"

        session_id = ss[0]["session_id"]
        requeued = any(dup.get(s["message_id"], 0) > 1 for s in ss if s["message_id"])
        msgs = [{
            "source_id": s["id"],
            "role": "user" if s["author_type"] == "user" else "agent",
            "content": (s["raw_content"] or "").strip().replace("\n", " "),
            "time": fmt(s["occurred_at"]),
        } for s in ss]
        return {
            "id": task_id or ("grp_" + ss[0]["id"]),
            "is_task": bool(task_id),
            "time": fmt(ss[0]["created_at"]),
            "_sort": ss[0]["created_at"],
            "session_id": session_id,
            "generation": _session_generation(session_id),
            "batch_seq": task["batch_seq"] if task else None,
            "task_status": task_status,
            "error_code": error_code,
            "messages": msgs,
            "produced": produced,
            "stored": stored,
            "outcome": outcome,
            "unresolved": unresolved,
            "requeued": requeued,
        }

    turns = [mk_turn(tid, ss) for tid, ss in by_task.items()]
    turns += [mk_turn(None, ss) for ss in loose_groups]
    turns.sort(key=lambda t: t["_sort"], reverse=True)
    return turns


_TURN_OUTCOMES = ("ok", "mg", "scope", "blocked", "fail", "none")


@app.get("/api/turns")
def turns(outcome: str = "all", q: str = "", limit: int = 200, offset: int = 0):
    """回合化纳入明细。counts 为当前搜索条件下的 outcome 分面计数。"""
    rows = _all_turns()
    if q:
        ql = q.lower()
        rows = [t for t in rows
                if ql in t["id"].lower()
                or any(ql in m["content"].lower() or ql in m["source_id"].lower()
                       for m in t["messages"])]
    counts = {k: sum(1 for t in rows if t["outcome"] == k) for k in _TURN_OUTCOMES}
    counts["all"] = len(rows)
    if outcome != "all":
        rows = [t for t in rows if t["outcome"] == outcome]
    total = len(rows)
    src_total = sum(len(t["messages"]) for t in rows)
    page = rows[offset: offset + limit]
    for t in page:
        t.pop("_sort", None)
    return {"total": total, "source_total": src_total, "counts": counts, "rows": page}


@app.get("/api/turns/{turn_id}")
def turn_detail(turn_id: str):
    """回合详情：回合消息 → 范围解析 → 抽取任务（含模型输入）→ 治理入库 → 结果。"""
    turn = next((t for t in _all_turns() if t["id"] == turn_id), None)
    if not turn:
        raise HTTPException(404, "turn not found")
    src_ids = [m["source_id"] for m in turn["messages"]]

    src_audits = query(
        "SELECT target_id, action, reason_code, operator_type, created_at FROM memory_audit_log "
        "WHERE target_type='source' AND target_id = ANY(%s) ORDER BY id", (src_ids,)
    )

    task_info = None
    model_input: List[Dict[str, Any]] = []
    if turn["is_task"]:
        t = query(
            "SELECT id, status, batch_seq, started_at, completed_at, last_error, error, payload "
            "FROM memory_task WHERE id=%s", (turn_id,)
        )
        if t:
            t = t[0]
            try:
                execution = (t["payload"] or {}).get("execution") or {}
                history = ((execution.get("input") or {}).get("history")) or []
                for h in history[:6]:
                    model_input.append({
                        "role": h.get("role", "?"),
                        "content": (h.get("content") or "")[:400],
                    })
            except Exception:
                pass
            task_info = {
                "id": t["id"], "status": t["status"], "batch_seq": t["batch_seq"],
                "started_at": fmt(t["started_at"], full=True),
                "completed_at": fmt(t["completed_at"], full=True),
                "last_error": t["last_error"],
                "error_code": (t["error"] or {}).get("code"),
                "error_message": ((t["error"] or {}).get("message") or "")[:300],
            }

    products = query(
        "SELECT e.id AS evi_id, e.evidence_snippet, e.upstream_source_id, e.status AS evi_status, "
        "       m.id AS mem_id, m.summary, m.confidence, m.status AS mem_status, "
        "       m.created_at AS mem_created "
        "FROM memory_evidence e LEFT JOIN memory_item m ON m.id=e.downstream_memory_id "
        "WHERE e.upstream_source_id = ANY(%s) ORDER BY e.id", (src_ids,)
    )
    mem_ids = [p["mem_id"] for p in products if p["mem_id"]]
    mem_audits: List[Dict[str, Any]] = []
    if mem_ids:
        mem_audits = query(
            "SELECT action, reason_code, target_id, created_at FROM memory_audit_log "
            "WHERE target_type='memory' AND target_id = ANY(%s) ORDER BY id", (mem_ids,)
        )

    src_by_id = {m["source_id"]: m for m in turn["messages"]}
    return {
        "turn": {k: v for k, v in turn.items() if k != "_sort"},
        "messages": [
            dict(m, unresolved=any(
                a["target_id"] == m["source_id"] and a["reason_code"] == "SCOPE_UNRESOLVED"
                for a in src_audits))
            for m in turn["messages"]
        ],
        "task": task_info,
        "model_input": model_input,
        "products": [
            {"evi_id": p["evi_id"], "snippet": (p["evidence_snippet"] or "")[:400],
             "from_role": (src_by_id.get(p["upstream_source_id"]) or {}).get("role", "?"),
             "evi_status": p["evi_status"],
             "mem_id": p["mem_id"], "summary": p["summary"],
             "confidence": float(p["confidence"]) if p["confidence"] is not None else None,
             "mem_status": p["mem_status"], "mem_created": fmt(p["mem_created"], full=True)}
            for p in products
        ],
        "src_audits": [
            {"source_id": a["target_id"], "action": a["action"], "reason_code": a["reason_code"],
             "operator": a["operator_type"], "time": fmt(a["created_at"], full=True)}
            for a in src_audits
        ],
        "mem_audits": [
            {"action": a["action"], "reason_code": a["reason_code"],
             "target_id": a["target_id"], "time": fmt(a["created_at"], full=True)}
            for a in mem_audits
        ],
    }


# ---------------- 记忆清单 ----------------

# memory_item.status 完整枚举（GM ck_memory_status 约束）
_STATUS_ENUM = ("active", "invalidated", "disputed", "expired")
_TYPE_ENUM = ("fact", "inference", "skill", "rule")


@app.get("/api/memories")
def memories(type: str = "all", status: str = "active", q: str = ""):
    """记忆清单。status 默认只看 active——disputed（冲突失效）/invalidated（整合作废）/
    expired（过期）均不参与召回，默认不混入清单，可通过状态筛选显式查看。
    counts 返回分面计数：by_type 在当前状态+搜索下统计，by_status 在当前类型+搜索下统计。"""
    rows = query(
        "SELECT m.id, m.subject_type, m.subject_id, m.cognitive_type, m.summary, "
        "       m.confidence, m.status, m.version, m.supersedes_id, m.created_at, m.created_by, "
        "       (SELECT count(*) FROM memory_evidence e "
        "         WHERE e.downstream_memory_id=m.id AND e.status='active') AS src_count, "
        "       EXISTS(SELECT 1 FROM memory_embedding em WHERE em.memory_id=m.id) AS has_embedding "
        "FROM memory_item m ORDER BY m.created_at DESC"
    )
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "subject_id": r["subject_id"],
            "type": r["cognitive_type"], "summary": r["summary"],
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "status": r["status"], "version": r["version"],
            "supersedes_id": r["supersedes_id"],
            "created_at": fmt(r["created_at"]), "created_by": r["created_by"],
            "src_count": r["src_count"], "has_embedding": r["has_embedding"],
        })

    def match_type(m: Dict[str, Any]) -> bool:
        return type == "all" or m["type"] == type

    def match_status(m: Dict[str, Any]) -> bool:
        return status == "all" or m["status"] == status

    def match_q(m: Dict[str, Any]) -> bool:
        if not q:
            return True
        ql = q.lower()
        return ql in m["summary"].lower() or ql in m["id"].lower()

    # 分面计数：另一维度固定为当前选择，保证 chips 数字与点击后的结果一致
    by_type = {t: sum(1 for m in out if match_status(m) and match_q(m) and m["type"] == t)
               for t in _TYPE_ENUM}
    by_type["all"] = sum(1 for m in out if match_status(m) and match_q(m))
    by_status = {s: sum(1 for m in out if match_type(m) and match_q(m) and m["status"] == s)
                 for s in _STATUS_ENUM}
    by_status["all"] = sum(1 for m in out if match_type(m) and match_q(m))

    filtered = [m for m in out if match_type(m) and match_status(m) and match_q(m)]
    return {
        "total": len(filtered),
        "rows": filtered,
        "counts": {"by_type": by_type, "by_status": by_status},
    }


@app.get("/api/memories/{mem_id}")
def memory_detail(mem_id: str):
    m = query("SELECT * FROM memory_item WHERE id=%s", (mem_id,))
    if not m:
        raise HTTPException(404, "memory not found")
    m = m[0]

    sources = query(
        "SELECT e.upstream_source_id, e.evidence_snippet, e.status AS evi_status, "
        "       s.raw_content, s.author_type, s.occurred_at "
        "FROM memory_evidence e JOIN source_record s ON s.id=e.upstream_source_id "
        "WHERE e.downstream_memory_id=%s", (mem_id,)
    )
    audits = query(
        "SELECT action, reason_code, operator_type, reason, created_at FROM memory_audit_log "
        "WHERE target_type='memory' AND target_id=%s ORDER BY id", (mem_id,)
    )
    emb = query(
        "SELECT model_id, status, content_hash, created_at FROM memory_embedding WHERE memory_id=%s",
        (mem_id,),
    )
    return {
        "memory": {
            "id": m["id"], "subject_id": m["subject_id"], "subject_type": m["subject_type"],
            "type": m["cognitive_type"], "summary": m["summary"], "content": m["content"],
            "confidence": float(m["confidence"]) if m["confidence"] is not None else None,
            "status": m["status"], "version": m["version"], "supersedes_id": m["supersedes_id"],
            "created_at": fmt(m["created_at"], full=True), "created_by": m["created_by"],
            "effective_at": fmt(m["effective_at"], full=True),
            "expired_at": fmt(m["expired_at"], full=True),
        },
        "sources": [
            {"source_id": s["upstream_source_id"],
             "snippet": (s["evidence_snippet"] or "")[:400],
             "raw": (s["raw_content"] or "").strip().replace("\n", " "),
             "author_type": s["author_type"], "time": fmt(s["occurred_at"], full=True),
             "evi_status": s["evi_status"]}
            for s in sources
        ],
        "audits": [
            {"action": a["action"], "reason_code": a["reason_code"],
             "operator": a["operator_type"], "reason": a["reason"],
             "time": fmt(a["created_at"], full=True)}
            for a in audits
        ],
        "embedding": {
            "model_id": emb[0]["model_id"], "status": emb[0]["status"],
            "content_hash": (emb[0]["content_hash"] or "")[:16],
            "created_at": fmt(emb[0]["created_at"], full=True),
        } if emb else None,
    }


@app.get("/api/health")
def health():
    query("SELECT 1")
    return {"ok": True, "db": "connected", "readonly": True}
