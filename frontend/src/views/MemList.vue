<template>
  <section class="panel on">
    <div class="chead">
      <h1>记忆清单</h1>
      <span class="sub">memory_item · 实体 <b class="mono" style="font-weight:600">gm_user_lw</b>（老王 · user）· 默认仅展示生效（active）记忆 · 点击行查看记忆详情与来源追溯</span>
    </div>

    <div class="ftools">
      <div class="fchips">
        <button v-for="c in typeChips" :key="c.k" class="fchip" :class="{ on: type === c.k }" @click="setType(c.k)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>
      <span class="fsep"></span>
      <div class="fchips">
        <button v-for="c in statusChips" :key="c.k" class="fchip" :class="[{ on: status === c.k }, c.chipCls]" @click="setStatus(c.k)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>
      <span class="searchbox">
        <svg class="i" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4"/><path d="M10.2 10.2l3.3 3.3"/></svg>
        <input v-model="q" placeholder="搜索记忆内容 / memory ID" @input="reload">
      </span>
    </div>

    <div v-if="status === 'disputed'" class="banner-er">
      <svg class="i" viewBox="0 0 16 16"><path d="M8 1.8L14.5 13H1.5z"/><path d="M8 6v3.4M8 11.2v.1"/></svg>
      争议失效记忆：与既有记忆冲突时被治理机制标记（事实冲突双方一并标 disputed），检索召回不可见，等待治理任务仲裁。冲突消解前请勿作为有效记忆使用。
    </div>
    <div v-else-if="status === 'invalidated'" class="banner-gray">
      已作废记忆：被整合治理（合并/替代）作废，由新版本记忆接替，检索召回不可见。
    </div>
    <div v-else-if="status === 'expired'" class="banner-gray">
      已过期记忆：超过有效期（expired_at）自动失效，检索召回不可见。
    </div>
    <div v-else-if="status === 'all'" class="banner-gray">
      当前展示全部状态记忆。非 active（争议失效 / 已作废 / 已过期）记忆不参与检索召回，行内容以灰色弱化显示。
    </div>

    <div class="card tblwrap">
      <table class="tbl">
        <thead><tr>
          <th>记忆 ID</th><th>内容</th><th>类型</th><th>置信度</th><th>状态</th><th>版本</th><th>来源数</th><th>向量</th><th>创建时间</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="m in rows" :key="m.id" :class="{ rowdim: m.status !== 'active' }" @click="open(m.id)">
            <td class="mono">{{ m.id }}</td>
            <td class="clip" style="max-width:320px">{{ m.summary }}</td>
            <td><span :class="typeCls(m.type)">{{ typeLabel(m.type) }}</span></td>
            <td>{{ m.confidence?.toFixed(2) }}<span class="minibar"><i :style="{ width: (m.confidence || 0) * 100 + '%' }"></i></span></td>
            <td><span class="chip" :class="statusChip(m.status).cls" :title="statusChip(m.status).tip"><span class="dot"></span>{{ statusChip(m.status).label }}</span></td>
            <td>v{{ m.version }}</td>
            <td>{{ m.src_count }}</td>
            <td><span class="chip" :class="m.has_embedding ? 'ok' : 'gray'"><span class="dot"></span>{{ m.has_embedding ? '已生成' : '无' }}</span></td>
            <td>{{ m.created_at }}</td>
            <td><span class="lk">详情</span></td>
          </tr>
        </tbody>
      </table>
      <div class="nomatch" :class="{ show: !loading && !rows.length }">无匹配记忆</div>
      <div class="tfoot">
        <span>共 {{ total }} 条 memory_item{{ status !== 'all' ? '（状态：' + statusChip(status).label + '）' : '' }}</span>
        <span class="right">推断（cognitive_type=inference）按产品决策并入事实记忆展示，以紫色角标区分 · 状态口径：仅 active 参与检索召回</span>
      </div>
    </div>

    <!-- 记忆详情抽屉 -->
    <div class="mask" :class="{ on: dw }" @click="dw = false"></div>
    <div class="dw" id="dwMem" :class="{ on: dw }">
      <div class="dw-head">
        <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>
        记忆详情 · <span class="mono">{{ detail?.memory?.id || '--' }}</span>
        <button class="ibtn" @click="dw = false"><svg class="i" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>
      </div>
      <div v-if="detail" class="dw-body">
        <div v-if="detail.memory.status !== 'active'" class="banner-er" style="margin-bottom:12px">
          <svg class="i" viewBox="0 0 16 16"><path d="M8 1.8L14.5 13H1.5z"/><path d="M8 6v3.4M8 11.2v.1"/></svg>
          该记忆当前为「{{ statusChip(detail.memory.status).label }}」，不参与检索召回。{{ statusChip(detail.memory.status).tip }}
        </div>
        <div class="quote" style="font-size:16px">{{ detail.memory.summary }}</div>

        <div class="ov" style="margin-top:12px">
          <div class="cell"><div class="k">类型 cognitive_type</div><div class="v">{{ detail.memory.type }}{{ detail.memory.type === 'inference' ? '（推断）' : '' }}</div></div>
          <div class="cell"><div class="k">置信度 confidence</div><div class="v">{{ detail.memory.confidence?.toFixed(2) ?? '--' }}</div></div>
          <div class="cell"><div class="k">状态 status</div><div class="v"><span class="chip" :class="statusChip(detail.memory.status).cls"><span class="dot"></span>{{ statusChip(detail.memory.status).label }}</span> <span class="mono" style="font-weight:400;color:var(--t3)">{{ detail.memory.status }}</span></div></div>
          <div class="cell"><div class="k">版本 version / supersedes</div><div class="v">v{{ detail.memory.version }} · {{ detail.memory.supersedes_id || '无前序版本' }}</div></div>
          <div class="cell"><div class="k">实体 subject</div><div class="v mono" style="font-weight:600">{{ detail.memory.subject_id }}</div></div>
          <div class="cell"><div class="k">创建时间 / 来源系统</div><div class="v">{{ detail.memory.created_at }} · {{ detail.memory.created_by }}</div></div>
          <div class="cell"><div class="k">生效时间 effective_at</div><div class="v">{{ detail.memory.effective_at }}</div></div>
          <div class="cell"><div class="k">过期时间 expired_at</div><div class="v">{{ detail.memory.expired_at }}</div></div>
        </div>

        <div class="sect">来源追溯（这条记忆怎么抽出来的）</div>
        <div v-if="detail.sources.length">
          <div v-for="s in detail.sources" :key="s.source_id" class="quote" style="margin-bottom:10px">
            {{ s.raw }}
            <div class="qmeta">
              <span>来源：<span class="mono">{{ s.source_id }}</span>（source_record）</span>
              <span>作者：{{ s.author_type === 'user' ? '用户' : '智能体' }}</span>
              <span>时间：{{ s.time }}</span>
            </div>
          </div>
        </div>
        <div v-else class="note-blue">无证据链关联（可能来自历史数据或整合任务产出）</div>

        <div class="sect">向量状态（memory_embedding）</div>
        <div v-if="detail.embedding" class="audit">
          <span class="mono">{{ detail.embedding.model_id }}</span>
          <span>{{ detail.embedding.status }}</span>
          <span class="mono">{{ detail.embedding.content_hash }}…</span>
          <span class="at">{{ detail.embedding.created_at }}</span>
        </div>
        <div v-else class="note-blue">该记忆暂无向量记录（disputed 时治理机制会删除检索向量）</div>

        <div class="sect">相关审计（memory_audit_log）</div>
        <div v-for="a in detail.audits" :key="a.action + a.time" class="audit">
          <span class="mono">{{ detail.memory.id }}</span>
          <span>{{ a.action }} · {{ a.reason_code }}</span>
          <span class="at">{{ a.time }} · {{ a.operator }}</span>
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
const type = ref('all')
const status = ref('active')
const q = ref('')
const loading = ref(false)
const dw = ref(false)
const detail = ref(null)
const counts = ref({ by_type: {}, by_status: {} })

// 状态展示口径：仅 active 参与检索召回；disputed=冲突失效（治理待仲裁）；
// invalidated=整合作废（被新版本替代）；expired=过期。枚举与 GM ck_memory_status 约束一致。
const STATUS_META = {
  active: { label: '生效', cls: 'ok', chipCls: '', tip: '参与检索召回' },
  disputed: { label: '争议失效', cls: 'err', chipCls: 'st-er', tip: '与既有记忆冲突，被治理标记争议，召回不可见，等待仲裁消解' },
  invalidated: { label: '已作废', cls: 'warn', chipCls: 'st-wn', tip: '被整合治理合并/替代作废，召回不可见' },
  expired: { label: '已过期', cls: 'gray', chipCls: '', tip: '超过有效期自动失效，召回不可见' }
}

const typeChips = computed(() => {
  const bt = counts.value.by_type || {}
  return [
    { k: 'all', label: '全部类型', count: bt.all ?? 0 },
    { k: 'fact', label: '事实', count: bt.fact ?? 0 },
    { k: 'inference', label: '推断', count: bt.inference ?? 0 },
    { k: 'skill', label: '技能', count: bt.skill ?? 0 }
  ]
})

const statusChips = computed(() => {
  const bs = counts.value.by_status || {}
  return [
    { k: 'active', label: '生效', count: bs.active ?? 0, chipCls: '' },
    { k: 'disputed', label: '争议失效', count: bs.disputed ?? 0, chipCls: 'st-er' },
    { k: 'invalidated', label: '已作废', count: bs.invalidated ?? 0, chipCls: 'st-wn' },
    { k: 'expired', label: '已过期', count: bs.expired ?? 0, chipCls: '' },
    { k: 'all', label: '全部状态', count: bs.all ?? 0, chipCls: '' }
  ]
})

function typeLabel(t) { return { fact: '事实', inference: '推断', skill: '技能', rule: '规则' }[t] || t }
function typeCls(t) { return t === 'inference' ? 'tag inf' : 'tag blue' }
function statusChip(s) { return STATUS_META[s] || { label: s, cls: 'gray', tip: '' } }

function setType(k) { type.value = k; reload() }
function setStatus(k) { status.value = k; reload() }

async function reload() {
  loading.value = true
  try {
    const r = await api.memories({ type: type.value, status: status.value, q: q.value })
    rows.value = r.rows
    total.value = r.total
    if (r.counts) counts.value = r.counts
  } finally { loading.value = false }
}

async function open(id) {
  dw.value = true
  detail.value = null
  detail.value = await api.memoryDetail(id)
  syncHash('list', 'mem', id)
}
watch(dw, v => { if (!v) syncHash('list', '', '') })

onMounted(() => {
  reload()
  const h = deepLink.value
  if (h && h.page === 'list' && h.view === 'mem' && h.id) open(h.id)
})
</script>
