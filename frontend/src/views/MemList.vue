<template>
  <section class="panel on">
    <div class="chead">
      <h1>记忆清单</h1>
      <span class="sub">memory_item 全量 · 实体 <b class="mono" style="font-weight:600">gm_user_lw</b>（老王 · user）· 点击行查看记忆详情与来源追溯</span>
    </div>

    <div class="ftools">
      <div class="fchips">
        <button v-for="c in chips" :key="c.k" class="fchip" :class="{ on: type === c.k }" @click="setType(c.k)">
          {{ c.label }} <b>{{ c.count }}</b>
        </button>
      </div>
      <span class="searchbox">
        <svg class="i" viewBox="0 0 16 16"><circle cx="7" cy="7" r="4"/><path d="M10.2 10.2l3.3 3.3"/></svg>
        <input v-model="q" placeholder="搜索记忆内容 / memory ID" @input="reload">
      </span>
    </div>

    <div class="card tblwrap">
      <table class="tbl">
        <thead><tr>
          <th>记忆 ID</th><th>内容</th><th>类型</th><th>置信度</th><th>状态</th><th>版本</th><th>来源数</th><th>向量</th><th>创建时间</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="m in rows" :key="m.id" @click="open(m.id)">
            <td class="mono">{{ m.id }}</td>
            <td class="clip" style="max-width:320px">{{ m.summary }}</td>
            <td><span :class="typeCls(m.type)">{{ typeLabel(m.type) }}</span></td>
            <td>{{ m.confidence?.toFixed(2) }}<span class="minibar"><i :style="{ width: (m.confidence || 0) * 100 + '%' }"></i></span></td>
            <td><span class="chip ok"><span class="dot"></span>{{ m.status }}</span></td>
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
        <span>共 {{ total }} 条 memory_item</span>
        <span class="right">推断（cognitive_type=inference）按产品决策并入事实记忆展示，以紫色角标区分</span>
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
        <div class="quote" style="font-size:16px">{{ detail.memory.summary }}</div>

        <div class="ov" style="margin-top:12px">
          <div class="cell"><div class="k">类型 cognitive_type</div><div class="v">{{ detail.memory.type }}{{ detail.memory.type === 'inference' ? '（推断）' : '' }}</div></div>
          <div class="cell"><div class="k">置信度 confidence</div><div class="v">{{ detail.memory.confidence?.toFixed(2) ?? '--' }}</div></div>
          <div class="cell"><div class="k">状态 status</div><div class="v">{{ detail.memory.status }}</div></div>
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
        <div v-else class="note-blue">该记忆暂无向量记录</div>

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
const q = ref('')
const loading = ref(false)
const dw = ref(false)
const detail = ref(null)
const allRows = ref([])

const chips = computed(() => {
  const byType = k => allRows.value.filter(m => m.type === k).length
  return [
    { k: 'all', label: '全部', count: allRows.value.length },
    { k: 'fact', label: '事实', count: byType('fact') },
    { k: 'inference', label: '推断', count: byType('inference') },
    { k: 'skill', label: '技能', count: byType('skill') }
  ]
})

function typeLabel(t) { return { fact: '事实', inference: '推断', skill: '技能' }[t] || t }
function typeCls(t) { return t === 'inference' ? 'tag inf' : 'tag blue' }

function setType(k) { type.value = k; reload() }

async function reload() {
  loading.value = true
  try {
    const r = await api.memories({ type: type.value, q: q.value })
    rows.value = r.rows
    total.value = r.total
    if (type.value === 'all' && !q.value) allRows.value = r.rows
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
