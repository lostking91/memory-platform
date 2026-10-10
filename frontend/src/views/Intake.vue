<template>
  <section class="panel on">
    <div class="chead">
      <h1>纳入明细</h1>
      <span class="sub">每次写入保存的抽取过程：原文 → 范围解析 → 模型抽取 → 治理 → 入库 · 点击行查看「怎么抽出来的」</span>
    </div>

    <div class="ftools">
      <div class="fchips">
        <button v-for="c in chips" :key="c.k" class="fchip" :class="{ on: outcome === c.k }" @click="setOutcome(c.k)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>
      <span class="searchbox">
        <svg class="i" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4"/><path d="M10.2 10.2l3.3 3.3"/></svg>
        <input v-model="q" placeholder="搜索原文内容 / source ID" @input="reload">
      </span>
    </div>

    <div class="card tblwrap">
      <table class="tbl">
        <thead><tr>
          <th>时间</th><th>来源 ID</th><th>作者</th><th>原始内容</th><th>范围解析</th><th>产出</th><th>现存</th><th>纳入结果</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" @click="open(r.id)">
            <td>{{ r.time }}</td>
            <td class="mono">{{ r.id.slice(0, 12) }}…</td>
            <td><span class="chip" :class="r.author_type === 'user' ? 'run' : 'gray'">{{ r.author_type === 'user' ? '用户' : '智能体' }}</span></td>
            <td class="clip">{{ r.content }}</td>
            <td>
              <span v-if="r.outcome === 'scope'" class="chip err"><span class="dot"></span>SCOPE_UNRESOLVED</span>
              <span v-else class="chip run"><span class="dot"></span>已匹配</span>
            </td>
            <td>{{ r.produced }}</td>
            <td>{{ r.stored }}</td>
            <td><span class="chip" :class="outChip(r.outcome).cls"><span class="dot"></span>{{ outChip(r.outcome).label }}</span></td>
            <td><span class="lk">抽取过程</span></td>
          </tr>
        </tbody>
      </table>
      <div class="nomatch" :class="{ show: !loading && !rows.length }">无匹配记录</div>
      <div class="tfoot">
        <span>共 {{ total }} 条 source_record{{ filtered ? '（已筛选）' : '' }}</span>
        <span class="right">口径：产出 = 证据链产出过的记忆条目；现存 = 其中仍为 active 的条目</span>
      </div>
    </div>

    <!-- 抽取过程抽屉 -->
    <div class="mask" :class="{ on: dw }" @click="dw = false"></div>
    <div class="dw" id="dwSrc" :class="{ on: dw }">
      <div class="dw-head">
        <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><path d="M5 2.5h4l2.5 2.5v8.5H5z"/><path d="M6.5 8h3M6.5 10.5h3"/></svg>
        抽取过程 · <span class="mono">{{ detail?.source?.id || '--' }}</span>
        <button class="ibtn" @click="dw = false"><svg class="i" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>
      </div>
      <div v-if="detail" class="dw-body">
        <div class="sect">原始内容（source_record）</div>
        <div class="quote">{{ detail.source.raw_content }}
          <div class="qmeta">
            <span>作者：{{ detail.source.author_type === 'user' ? '用户' : '智能体' }}</span>
            <span>时间：{{ detail.source.occurred_at }}</span>
            <span>系统：{{ detail.source.source_system }}</span>
            <span>会话：<span class="mono">{{ (detail.source.session_id || '').slice(0, 16) }}</span></span>
          </div>
        </div>

        <div class="tl" style="margin-top:16px">
          <!-- 1 范围解析 -->
          <div class="tstep" :class="{ err: detail.unresolved }">
            <div class="tt">范围解析（business_scene）
              <span v-if="detail.unresolved" class="chip err"><span class="dot"></span>SCOPE_UNRESOLVED</span>
              <span v-else class="chip run"><span class="dot"></span>已匹配</span>
            </div>
            <div class="td" v-if="detail.unresolved">内容未匹配任何 business_scene，不进入抽取管线 —— 这条内容「漏」在这里。</div>
            <div class="td" v-else>语义匹配通过 · 租户 {{ 'cmic-yun' }}</div>
            <div v-if="detail.unresolved" class="note-er">
              审计记录：UPDATE source · SCOPE_UNRESOLVED（{{ (detail.src_audits.find(a => a.reason_code === 'SCOPE_UNRESOLVED') || {}).time || '--' }}）
            </div>
          </div>

          <!-- 2 抽取任务 -->
          <div class="tstep" :class="{ off: !detail.task }">
            <div class="tt" :style="detail.task ? '' : 'color:var(--t3)'">抽取任务（fact_extract）
              <span v-if="detail.task" class="chip ok"><span class="dot"></span>{{ detail.task.status }}</span>
            </div>
            <template v-if="detail.task">
              <div class="td">{{ detail.task.id }} · 开始 {{ detail.task.started_at }} · 完成 {{ detail.task.completed_at }}</div>
              <div v-if="detail.model_input.length" class="tb">
                <div v-for="(m, i) in detail.model_input" :key="i" class="cand">
                  <div class="chd"><span class="tag blue">{{ m.role }}</span><span style="color:var(--t3);font-size:12px">模型输入历史</span></div>
                  <div class="ct" style="white-space:pre-wrap">{{ m.content }}</div>
                </div>
              </div>
            </template>
            <div v-else class="td">范围未解析，抽取任务未创建</div>
          </div>

          <!-- 3 治理与入库 -->
          <div class="tstep" :class="{ off: !detail.products.length }">
            <div class="tt" :style="detail.products.length ? '' : 'color:var(--t3)'">治理判定与入库（memory_evidence → memory_item）</div>
            <div v-if="detail.products.length" class="tb">
              <div v-for="p in detail.products" :key="p.evi_id" class="cand">
                <div class="chd">
                  <span class="tag blue">{{ p.summary ? '记忆' : '证据' }}</span>
                  <span v-if="p.summary" class="mono" style="color:var(--t2)">{{ p.mem_id }}</span>
                  <span class="disp" :class="p.mem_status === 'active' ? 'in' : 'lo'">{{ p.mem_status === 'active' ? '现存' : '已失效' }}</span>
                  <span v-if="p.confidence != null" style="margin-left:auto;font-size:13px;font-weight:700;color:var(--blue-deep)">
                    {{ p.confidence.toFixed(2) }}<span class="minibar"><i :style="{ width: p.confidence * 100 + '%' }"></i></span>
                  </span>
                </div>
                <div v-if="p.summary" class="ct">{{ p.summary }}</div>
                <div class="cft"><span>证据：{{ p.snippet }}</span></div>
              </div>
            </div>
            <div v-else class="td">{{ detail.unresolved ? '未执行' : '本条内容无可抽取事实（任务产出为空）' }}</div>
          </div>

          <!-- 4 结果 -->
          <div class="tstep" :class="{ err: detail.unresolved }">
            <div class="tt">纳入结果
              <span class="chip" :class="outChip(outcomeOf(detail)).cls"><span class="dot"></span>{{ outChip(outcomeOf(detail)).label }}</span>
            </div>
            <div class="note-blue" style="margin-top:8px">{{ outNote(detail) }}</div>
            <div v-for="a in detail.src_audits" :key="a.action + a.time" class="audit">
              <span class="mono">audit</span><span>{{ a.action }} · {{ a.reason_code }}</span><span class="at">{{ a.time }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="dw-body" style="color:var(--t3)">加载中…</div>
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
const outcome = ref('all')
const q = ref('')
const loading = ref(false)
const dw = ref(false)
const detail = ref(null)

const chips = computed(() => {
  const all = total.value || rows.value.length
  const cnt = k => (outcome.value === k ? rows.value.length : '')
  return [
    { k: 'all', label: '全部', count: outcome.value === 'all' ? rows.value.length : '' },
    { k: 'ok', label: '已纳入', count: cnt('ok') },
    { k: 'mg', label: '合并/失效', count: cnt('mg') },
    { k: 'scope', label: '范围未解析', count: cnt('scope') },
    { k: 'none', label: '无可抽取', count: cnt('none') }
  ]
})
const filtered = computed(() => outcome.value !== 'all' || q.value !== '')

function outChip(k) {
  return {
    ok: { cls: 'ok', label: '已纳入' },
    mg: { cls: 'run', label: '合并/失效' },
    scope: { cls: 'err', label: '范围未解析' },
    none: { cls: 'gray', label: '无可抽取' }
  }[k] || { cls: 'gray', label: k }
}

function outcomeOf(d) {
  if (d.unresolved) return 'scope'
  const act = d.products.filter(p => p.mem_status === 'active').length
  if (act > 0) return 'ok'
  if (d.products.length) return 'mg'
  return 'none'
}

function outNote(d) {
  const k = outcomeOf(d)
  if (k === 'scope') return '该内容未进入记忆管线（SCOPE_UNRESOLVED）。若判定为误拦，需在 GM business_scene 补充场景词条（属管理平台任务5的配置能力）。'
  if (k === 'ok') return `产出 ${d.products.length} 条记忆，现存 active ${d.products.filter(p => p.mem_status === 'active').length} 条。`
  if (k === 'mg') return '产出过记忆条目，但已被整合治理合并或失效，无独立存留条目。'
  return '范围解析通过，但模型未抽取到可入库的事实内容。'
}

async function reload() {
  loading.value = true
  try {
    const r = await api.sources({ outcome: outcome.value, q: q.value })
    rows.value = r.rows
    total.value = r.total
  } finally { loading.value = false }
}

function setOutcome(k) { outcome.value = k; reload() }

async function open(id) {
  dw.value = true
  detail.value = null
  detail.value = await api.sourceDetail(id)
  syncHash('intake', 'src', id)
}
watch(dw, v => { if (!v) syncHash('intake', '', '') })

onMounted(() => {
  reload()
  const h = deepLink.value
  if (h && h.page === 'intake' && h.view === 'src' && h.id) open(h.id)
})
</script>
