<template>
  <section class="panel on">
    <div class="chead">
      <h1>概览统计</h1>
      <span class="sub">口径：纳入率 = 现存记忆 ÷ 写入保存 · 租户 {{ data?.tenant || '--' }}</span>
      <div class="right">
        <button class="btn sm" @click="load"><svg class="i" style="width:13px;height:13px" viewBox="0 0 16 16"><path d="M13 8a5 5 0 1 1-1.8-3.8"/><path d="M13 2.5V5h-2.5"/></svg>刷新</button>
        <span class="sub">最后更新：{{ data?.refreshed_at || '--' }}</span>
      </div>
    </div>

    <div v-if="data" class="stats">
      <div class="stat"><div class="lb">写入保存（source_record）</div><div class="vl">{{ s.saved }}<small>条</small></div><span class="ic"><svg class="i" viewBox="0 0 16 16"><path d="M5 2.5h4l2.5 2.5v8.5H5z"/><path d="M6.5 8h3M6.5 10.5h3"/></svg></span></div>
      <div class="stat"><div class="lb">抽取产出（FACT_EXTRACTED）</div><div class="vl">{{ s.extracted }}<small>条</small></div><span class="ic"><svg class="i" viewBox="0 0 16 16"><path d="M2.5 5.5l5.5-3 5.5 3v5l-5.5 3-5.5-3z"/><path d="M2.5 5.5l5.5 3 5.5-3M8 8.5v5"/></svg></span></div>
      <div class="stat"><div class="lb">现存记忆（active）</div><div class="vl">{{ s.active }}<small>条</small></div><span class="ic"><svg class="i" viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg></span></div>
      <div class="stat hi"><div class="lb">记忆纳入率</div><div class="vl">{{ s.rate }}%<small>{{ s.active }} / {{ s.saved }}</small></div><span class="ic"><svg class="i" viewBox="0 0 16 16"><path d="M3 13.5h10"/><path d="M5 13.5V9.5M8 13.5V6.5M11 13.5V4.5"/></svg></span></div>
      <div class="stat"><div class="lb">待处理任务 / 证据</div><div class="vl">{{ s.pending }}<small>pending / {{ s.evidence }} evi</small></div><span class="ic"><svg class="i" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5M8 10.5v.1"/></svg></span></div>
    </div>

    <div v-if="data" class="card">
      <div class="chd">
        <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><path d="M2 3.5h12l-4.5 5.2v3.8L6.5 14V8.7z"/></svg>
        记忆纳入漏斗（全部累计，审计码口径）
        <span class="note">悬停比例条查看审计码与流失原因 · 可下钻至「纳入明细」</span>
      </div>
      <div class="funnel">
        <template v-for="(st, idx) in data.funnel" :key="st.key">
          <div class="fstage">
            <div class="fbar" :class="'f' + (idx + 1)" :style="{ width: fw(idx) }"
                 @mouseenter="showTip($event, idx)" @mousemove="moveTip" @mouseleave="hideTip">
              <span class="lbl">{{ shortLabel(st.label) }}</span>
              <span class="n">{{ st.value }}<small>条</small></span>
            </div>
          </div>
          <div v-if="idx < data.funnel.length - 1" class="fconn" :style="{ width: fw(idx) }">
            <div class="ftrap" :style="{ clipPath: trapClip(idx) }"></div>
            <span class="fchip">{{ data.funnel[idx + 1].conv ?? '--' }}%</span>
          </div>
        </template>
        <div class="ffoot">整体纳入率 <b>{{ s.rate }}%</b>（现存记忆 {{ s.active }} / 写入保存 {{ s.saved }}）</div>
      </div>
      <div v-show="tip.show" class="ftip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
        <div class="tt">{{ tip.st ? shortLabel(tip.st.label) : '' }}<span v-if="tip.st && codeOf(tip.st.label)" class="tc">{{ codeOf(tip.st.label) }}</span></div>
        <div class="tr"><span>本环节</span><b>{{ tip.st ? tip.st.value : 0 }} 条</b></div>
        <div v-if="tip.st && tip.idx > 0" class="tr"><span>较上一环节转化</span><b>{{ tip.st.conv ?? '--' }}%</b></div>
        <div v-if="tip.st && tip.st.leak > 0" class="tr"><span>流失</span><b class="lk">{{ tip.st.leak }} 条</b></div>
        <div v-if="tip.st && tip.st.leak > 0" class="tn">{{ tip.st.leak_note }}</div>
        <div v-if="tip.st && tip.st.key === 'active'" class="tr"><span>整体纳入率</span><b>{{ s.rate }}%</b></div>
      </div>
    </div>

    <div v-if="data" class="dgrid">
      <div class="card">
        <div class="chd">
          <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><path d="M5 2.5h4l2.5 2.5v8.5H5z"/><path d="M6.5 8h3M6.5 10.5h3"/></svg>
          纳入结果分布（来源条目口径）
        </div>
        <div class="dist">
          <div v-for="r in data.reasons" :key="r.label" class="drow">
            <span class="dl">{{ r.label }}</span>
            <span class="dbar"><i :class="r.cls" :style="{ width: barW(r.value) }"></i></span>
            <span class="dn">{{ r.value }}</span>
            <span class="dp">{{ pct(r.value, reasonSum) }}</span>
          </div>
          <div style="font-size:12px;color:var(--t3);margin-top:14px">{{ data.reasons_note }}</div>
        </div>
      </div>
      <div class="card">
        <div class="chd">
          <svg class="i" style="color:var(--blue)" viewBox="0 0 16 16"><path d="M3 13.5h10"/><path d="M5 13.5V9.5M8 13.5V6.5M11 13.5V4.5"/></svg>
          纳入趋势（按日）
          <span class="note legend"><span><i style="background:#a8c3ff"></i>写入保存</span><span><i style="background:#0e4fd8"></i>新增记忆</span></span>
        </div>
        <div class="dist">
          <svg v-if="trendMax > 0" viewBox="0 0 520 190" preserveAspectRatio="xMidYMid meet" style="width:100%;max-height:212px;display:block">
            <line x1="28" y1="10" x2="510" y2="10" stroke="#eef1f6" stroke-dasharray="3 3"/>
            <line x1="28" y1="160" x2="510" y2="160" stroke="#e3e8f0"/>
            <text x="24" y="163" font-size="10" fill="#6b7688" text-anchor="end">0</text>
            <text x="24" y="42" font-size="10" fill="#6b7688" text-anchor="end">{{ trendMax }}</text>
            <template v-for="(d, i) in data.trend" :key="d.day">
              <rect :x="slotX(i)" :y="barY(d.saved)" :width="barWd" :height="barH(d.saved)" rx="2" fill="#a8c3ff"/>
              <rect :x="slotX(i) + barWd + 4" :y="barY(d.active)" :width="barWd" :height="barH(d.active)" rx="2" fill="#0e4fd8"/>
              <text :x="slotX(i) + barWd + 2" y="175" font-size="10" fill="#6b7688" text-anchor="middle">{{ d.day }}</text>
            </template>
          </svg>
          <div v-else class="empty"><span class="ebox"><svg viewBox="0 0 16 16"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/></svg></span>暂无数据</div>
        </div>
      </div>
    </div>

    <div v-else class="card"><div class="empty" style="padding-top:120px">
      <span class="ebox"><svg viewBox="0 0 16 16"><path d="M8 2.5l5.5 3-5.5 3-5.5-3z"/></svg></span>
      {{ loading ? '加载中…' : '加载失败：BFF 服务（:8002）或数据库未连接' }}
    </div></div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api.js'

const data = ref(null)
const loading = ref(false)
const s = computed(() => data.value?.stats || {})
const reasonSum = computed(() => (data.value?.reasons || []).reduce((a, r) => a + r.value, 0))
const trendMax = computed(() => Math.max(1, ...(data.value?.trend || []).flatMap(d => [d.saved, d.active])))

function barW(v) { return Math.max(2, Math.round(v / Math.max(1, reasonSum.value) * 100)) + '%' }
function pct(v, sum) { return sum ? Math.round(v / sum * 1000) / 10 + '%' : '--' }
function barH(v) { return v * (160 - 38) / trendMax.value }
function barY(v) { return 160 - barH(v) }
/* 趋势图固定 520 宽 viewBox，按天数均分槽位，柱宽自适应，避免少天数时被拉伸放大 */
const TREND_W = 520, TREND_X0 = 36, TREND_X1 = 512
const slotW = computed(() => (TREND_X1 - TREND_X0) / Math.max(1, (data.value?.trend || []).length))
const barWd = computed(() => Math.max(6, Math.min(16, (slotW.value - 10) / 2)))
function slotX(i) { return TREND_X0 + i * slotW.value + (slotW.value - (barWd.value * 2 + 4)) / 2 }
/* 漏斗条内只放短标签，括号里的审计码/表名移入悬停浮层，避免窄条换行溢出 */
function codeOf(label) { const m = /（([^）]+)）/.exec(label || ''); return m ? m[1] : '' }
function shortLabel(label) { return (label || '').replace(/（[^）]*）/, '').trim() }

/* 方案B 居中真漏斗：条宽按 value/max 比例，梯形连接件按上下两级宽度裁切 */
const FW_MIN = 150
function fw(idx) {
  const f = data.value?.funnel || []
  const max = Math.max(1, ...f.map(x => x.value))
  const w = Math.max(FW_MIN, Math.round(f[idx].value / max * 660))
  return w + 'px'
}
function fwPx(idx) { return parseInt(fw(idx), 10) }
function trapClip(idx) {
  const wTop = fwPx(idx), wBot = fwPx(idx + 1)
  const l = ((wTop - wBot) / 2 / wTop * 100).toFixed(2)
  const r = (100 - (wTop - wBot) / 2 / wTop * 100).toFixed(2)
  return `polygon(0 0, 100% 0, ${r}% 100%, ${l}% 100%)`
}
/* 悬停浮层：鼠标跟随，视口边缘自动翻转/下移 */
const tip = ref({ show: false, x: 0, y: 0, idx: 0, st: null })
function placeTip(e) {
  const el = document.querySelector('.ftip')
  const w = el ? el.offsetWidth : 240, h = el ? el.offsetHeight : 120
  let x = e.clientX + 14, y = e.clientY + 16
  if (x + w > window.innerWidth - 8) x = e.clientX - w - 14
  if (y + h > window.innerHeight - 8) y = e.clientY - h - 14
  tip.value.x = Math.max(8, x); tip.value.y = Math.max(8, y)
}
function showTip(e, idx) {
  tip.value = { show: true, x: e.clientX + 14, y: e.clientY + 16, idx, st: data.value.funnel[idx] }
  placeTip(e)
}
function moveTip(e) { if (tip.value.show) placeTip(e) }
function hideTip() { tip.value.show = false }

async function load() {
  loading.value = true
  try { data.value = await api.overview() } finally { loading.value = false }
}
onMounted(load)
</script>
