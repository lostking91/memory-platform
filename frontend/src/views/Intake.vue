<template>
  <section class="panel on">
    <div class="chead">
      <h1>纳入明细</h1>
      <span class="sub">1 行 = 1 个对话回合（用户提问 + 智能体回答一并抽取）：原文 → 范围解析 → 模型抽取 → 治理 → 入库 · 点击行查看「怎么抽出来的」</span>
    </div>

    <div class="ftools">
      <div class="fchips">
        <button v-for="c in chips" :key="c.k" class="fchip" :class="[c.chipOn || '', { on: outcome === c.k }]" @click="setOutcome(c.k)">
          {{ c.label }} <b>{{ counts[c.k] ?? '' }}</b>
        </button>
      </div>
      <span class="searchbox">
        <svg class="i" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4"/><path d="M10.2 10.2l3.3 3.3"/></svg>
        <input v-model="q" placeholder="搜索回合内消息 / 任务 ID" @input="reload">
      </span>
    </div>

    <div class="card tblwrap">
      <table class="tbl">
        <thead><tr>
          <th>时间</th><th>对话回合（用户 → 智能体）</th><th>范围解析</th><th>抽取任务</th><th>产出</th><th>现存</th><th>纳入结果</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="t in rows" :key="t.id" :class="{ rowdim: t.outcome === 'blocked' }" @click="open(t.id)">
            <td>
              {{ t.time }}
              <span v-if="t.generation" class="tag gen" title="ai-assistant 阻断自愈轮换出的第 N 代 GM 会话">g{{ t.generation }}</span>
            </td>
            <td class="turncell">
              <div v-for="m in t.messages" :key="m.source_id" class="bub" :class="m.role === 'user' ? 'bub-user' : 'bub-agent'" :title="m.content">
                <span class="brole">{{ m.role === 'user' ? '用户' : '智能体' }}</span>
                <span class="btxt">{{ m.content }}</span>
              </div>
              <div class="turnmeta">
                <span v-if="t.requeued" class="tag wn" title="同一消息曾被重投到新一代 GM 会话（阻断自愈产物）">重投</span>
                <span class="mono tid">{{ t.id.slice(0, 16) }}…</span>
              </div>
            </td>
            <td>
              <span v-if="t.outcome === 'scope'" class="chip err"><span class="dot"></span>未解析</span>
              <span v-else class="chip run"><span class="dot"></span>已匹配</span>
            </td>
            <td>
              <span v-if="t.task_status" class="chip" :class="taskChip(t).cls"><span class="dot"></span>{{ taskChip(t).label }}</span>
              <span v-else class="chip gray">未创建</span>
            </td>
            <td>{{ t.produced }}</td>
            <td>{{ t.stored }}</td>
            <td><span class="chip" :class="outChip(t.outcome).cls"><span class="dot"></span>{{ outChip(t.outcome).label }}</span></td>
            <td><span class="lk">抽取过程</span></td>
          </tr>
        </tbody>
      </table>
      <div class="nomatch" :class="{ show: !loading && !rows.length }">无匹配回合</div>
      <div class="tfoot">
        <span>共 {{ total }} 个回合 / {{ sourceTotal }} 条来源消息{{ filtered ? '（已筛选）' : '' }}</span>
        <span class="right">口径：产出 = 回合证据链产出过的记忆条目（并集去重）；现存 = 其中仍为 active 的条目</span>
      </div>
    </div>

    <!-- 抽取过程抽屉（回合视角） -->
    <div class="mask" :class="{ on: dw }" @click="dw = false"></div>
    <div class="dw" id="dwSrc" :class="{ on: dw }">
      <div class="dw-head">
        <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><path d="M5 2.5h4l2.5 2.5v8.5H5z"/><path d="M6.5 8h3M6.5 10.5h3"/></svg>
        抽取过程 · 回合 <span class="mono">{{ detail?.turn?.id || '--' }}</span>
        <button class="ibtn" @click="dw = false"><svg class="i" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>
      </div>
      <div v-if="detail" class="dw-body">
        <div class="sect">① 写入内容（对话回合 · {{ detail.messages.length }} 条消息）</div>
        <div v-for="m in detail.messages" :key="m.source_id" class="quote" :class="m.role === 'agent' ? 'q-agent' : ''">
          <span class="tag" :class="m.role === 'user' ? 'blue' : ''">{{ m.role === 'user' ? '用户' : '智能体' }}</span>
          {{ m.content }}
          <div class="qmeta">
            <span>时间：{{ m.time }}</span>
            <span>source：<span class="mono">{{ m.source_id.slice(0, 20) }}…</span></span>
            <span v-if="m.role === 'agent'" class="ctxnote">仅作抽取上下文，不独立产出记忆</span>
          </div>
        </div>
        <div v-if="detail.turn.requeued" class="note-amber">
          本回合消息曾因前序会话抽取失败被阻断，ai-assistant 自愈机制将其重投到第 {{ detail.turn.generation }} 代 GM 会话（会话 ID 后缀 -g{{ detail.turn.generation }}），本行即重投后的执行结果。
        </div>
        <div class="note-amber" style="margin-top:8px">
          GM 证据约束：每条抽取出的记忆必须引用至少一条<b>用户</b>消息（提示词硬约束 + 代码级校验），智能体回答只用于消解指代、提供上下文，防止智能体幻觉被固化为用户记忆。
        </div>

        <div class="tl" style="margin-top:16px">
          <!-- 2 范围解析 -->
          <div class="tstep" :class="{ err: detail.turn.outcome === 'scope' }">
            <div class="tt">② 范围解析（business_scene）
              <span v-if="detail.turn.outcome === 'scope'" class="chip err"><span class="dot"></span>SCOPE_UNRESOLVED</span>
              <span v-else class="chip run"><span class="dot"></span>已匹配</span>
            </div>
            <div class="td" v-if="detail.turn.outcome === 'scope'">回合内消息均未匹配 business_scene，不进入抽取管线 —— 内容「漏」在这里。</div>
            <div class="td" v-else>语义匹配通过 · 租户 cmic-yun · 会话 <span class="mono">{{ (detail.turn.session_id || '').slice(0, 24) }}</span></div>
            <div v-for="a in scopeAudits" :key="a.source_id + a.time" class="note-er">
              审计：{{ a.action }} · SCOPE_UNRESOLVED（{{ a.time }}）
            </div>
          </div>

          <!-- 3 抽取任务 -->
          <div class="tstep" :class="{ off: !detail.task, err: detail.task && ['failed', 'cancelled'].includes(detail.task.status) }">
            <div class="tt" :style="detail.task ? '' : 'color:var(--t3)'">③ 抽取任务（fact_extract）
              <span v-if="detail.task" class="chip" :class="taskChip(detail.turn).cls"><span class="dot"></span>{{ taskChip(detail.turn).label }}</span>
            </div>
            <template v-if="detail.task">
              <div class="td">{{ detail.task.id }} · batch_seq {{ detail.task.batch_seq }} · 开始 {{ detail.task.started_at }} · 完成 {{ detail.task.completed_at }}</div>
              <div v-if="detail.task.error_code" class="note-er" style="margin-top:6px">
                {{ detail.task.error_code }}<template v-if="detail.task.error_message">：{{ detail.task.error_message }}</template>
                <div v-if="detail.task.error_code === 'PRIOR_TASK_FAILED'" style="margin-top:4px">
                  同会话更早的抽取任务失败，GM 顺序保护跳过了本任务。ai-assistant 会自动重投到新一代会话（见「重投」标记），以重投副本的结果为准。
                </div>
              </div>
              <div v-if="detail.model_input.length" class="tb">
                <div v-for="(m, i) in detail.model_input" :key="i" class="cand">
                  <div class="chd"><span class="tag blue">{{ m.role }}</span><span style="color:var(--t3);font-size:12px">模型输入历史</span></div>
                  <div class="ct" style="white-space:pre-wrap">{{ m.content }}</div>
                </div>
              </div>
            </template>
            <div v-else class="td">{{ detail.turn.outcome === 'scope' ? '范围未解析，抽取任务未创建' : '无关联抽取任务' }}</div>
          </div>

          <!-- 4 治理与入库 -->
          <div class="tstep" :class="{ off: !detail.products.length }">
            <div class="tt" :style="detail.products.length ? '' : 'color:var(--t3)'">④ 治理判定与入库（memory_evidence → memory_item）</div>
            <div v-if="detail.products.length" class="tb">
              <div v-for="p in detail.products" :key="p.evi_id" class="cand">
                <div class="chd">
                  <span class="tag blue">{{ p.summary ? '记忆' : '证据' }}</span>
                  <span v-if="p.summary" class="mono" style="color:var(--t2)">{{ p.mem_id }}</span>
                  <span class="disp" :class="p.mem_status === 'active' ? 'in' : 'lo'">{{ p.mem_status === 'active' ? '现存' : '已失效' }}</span>
                  <span v-if="p.from_role" class="tag" style="margin-left:6px">证据来自：{{ p.from_role === 'user' ? '用户' : '智能体' }}消息</span>
                  <span v-if="p.confidence != null" style="margin-left:auto;font-size:13px;font-weight:700;color:var(--blue-deep)">
                    {{ p.confidence.toFixed(2) }}<span class="minibar"><i :style="{ width: p.confidence * 100 + '%' }"></i></span>
                  </span>
                </div>
                <div v-if="p.summary" class="ct">{{ p.summary }}</div>
                <div class="cft"><span>证据：{{ p.snippet }}</span></div>
              </div>
            </div>
            <div v-else class="td">{{ noProductNote }}</div>
          </div>

          <!-- 5 结果 -->
          <div class="tstep" :class="{ err: ['scope', 'fail'].includes(detail.turn.outcome) }">
            <div class="tt">⑤ 纳入结果
              <span class="chip" :class="outChip(detail.turn.outcome).cls"><span class="dot"></span>{{ outChip(detail.turn.outcome).label }}</span>
            </div>
            <div class="note-blue" style="margin-top:8px">{{ outNote(detail.turn) }}</div>
            <div v-for="a in detail.src_audits" :key="a.source_id + a.action + a.time" class="audit">
              <span class="mono">audit</span><span>{{ a.action }} · {{ a.reason_code }}</span><span class="at">{{ a.time }}</span>
            </div>
            <div v-for="a in detail.mem_audits" :key="a.target_id + a.action + a.time" class="audit">
              <span class="mono">audit</span><span>{{ a.action }} · {{ a.reason_code }} · <span class="mono">{{ (a.target_id || '').slice(0, 12) }}…</span></span><span class="at">{{ a.time }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="dw-body" style="color:var(--t3)">{{ loadErr || '加载中…' }}</div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import api from '../api.js'

const deepLink = inject('deepLink', ref(null))
const syncHash = inject('syncHash', () => {})

const rows = ref([])
const total = ref(0)
const sourceTotal = ref(0)
const counts = ref({})
const outcome = ref('all')
const q = ref('')
const loading = ref(false)
const dw = ref(false)
const detail = ref(null)
const loadErr = ref('')

const chips = [
  { k: 'all', label: '全部回合' },
  { k: 'ok', label: '已纳入' },
  { k: 'mg', label: '合并/失效' },
  { k: 'scope', label: '范围未解析' },
  { k: 'blocked', label: '前序阻断', chipOn: 'st-er' },
  { k: 'fail', label: '抽取失败', chipOn: 'st-wn' },
  { k: 'none', label: '无可抽取' }
]
const filtered = computed(() => outcome.value !== 'all' || q.value !== '')

function outChip(k) {
  return {
    ok: { cls: 'ok', label: '已纳入' },
    mg: { cls: 'run', label: '合并/失效' },
    scope: { cls: 'err', label: '范围未解析' },
    blocked: { cls: 'err', label: '前序阻断' },
    fail: { cls: 'warn', label: '抽取失败' },
    none: { cls: 'gray', label: '无可抽取' }
  }[k] || { cls: 'gray', label: k }
}

function taskChip(t) {
  const s = t.task_status
  if (s === 'succeeded') return { cls: 'ok', label: 'succeeded' }
  if (s === 'partial') return { cls: 'warn', label: 'partial' }
  if (s === 'failed') return { cls: 'err', label: 'failed' }
  if (s === 'cancelled') return { cls: 'gray', label: 'cancelled' }
  if (s === 'pending' || s === 'processing') return { cls: 'run', label: s }
  return { cls: 'gray', label: s || '--' }
}

function outNote(t) {
  if (t.outcome === 'scope') return '该回合未进入记忆管线（SCOPE_UNRESOLVED）。若判定为误拦，需在 GM business_scene 补充场景词条。'
  if (t.outcome === 'blocked') return '同会话更早的抽取任务失败，本回合未执行抽取' + (t.requeued ? '。消息已自动重投到新一代会话（见「重投」标记行），以重投副本的结果为准。' : '。')
  if (t.outcome === 'fail') return '抽取任务执行失败。ai-assistant 自愈机制会隔离该消息并重投同会话其余被阻断的消息。'
  if (t.outcome === 'ok') return `回合产出 ${t.produced} 条记忆，现存 active ${t.stored} 条。`
  if (t.outcome === 'mg') return '回合产出过记忆条目，但已被整合治理合并或失效，无独立存留条目。'
  return '范围解析与抽取任务均正常，但模型未从本回合抽取到可入库的事实内容。'
}

const scopeAudits = computed(() =>
  (detail.value?.src_audits || []).filter(a => a.reason_code === 'SCOPE_UNRESOLVED'))
const noProductNote = computed(() => {
  const o = detail.value?.turn?.outcome
  if (o === 'scope') return '未执行（范围未解析）'
  if (o === 'blocked') return '未执行（同会话前序任务失败，GM 跳过了本任务）'
  if (o === 'fail') return '任务失败，无产出'
  return '本回合无可抽取事实（任务产出为空）'
})

async function reload() {
  loading.value = true
  try {
    const r = await api.turns({ outcome: outcome.value, q: q.value })
    rows.value = r.rows
    total.value = r.total
    sourceTotal.value = r.source_total
    counts.value = r.counts || {}
  } finally { loading.value = false }
}

function setOutcome(k) { outcome.value = k; reload() }

async function open(id) {
  dw.value = true
  detail.value = null
  loadErr.value = ''
  try {
    detail.value = await api.turnDetail(id)
    syncHash('intake', 'turn', id)
  } catch (e) {
    loadErr.value = '回合详情加载失败：' + (e?.response?.status === 404 ? '未找到该回合（可能是旧消息级深链）' : e.message)
  }
}
watch(dw, v => { if (!v) syncHash('intake', '', '') })

onMounted(() => {
  reload()
  const h = deepLink.value
  if (h && h.page === 'intake' && (h.view === 'turn' || h.view === 'src') && h.id) open(h.id)
})
</script>
