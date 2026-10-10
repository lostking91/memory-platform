<template>
  <div class="app">
    <header class="top">
      <div class="logo"><svg viewBox="0 0 16 16"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg></div>
      <span class="pname">智能体公共记忆运营监控平台</span>
      <span class="pdiv"></span>
      <span class="psub">GeneralMemory-2.1.0（MemoryCMIC）· 只读直连 GM Postgres :5433</span>
      <div class="right">
        <span class="vtag">v1</span>
        <span class="envchip" :class="{ err: !dbOk }">
          <span class="dot"></span>{{ dbOk ? '数据源：GM 库只读 · 已连接' : 'BFF / 数据库未连接' }}
        </span>
        <span class="uname">记忆运营管理员</span>
        <span class="avatar">运</span>
      </div>
    </header>

    <div class="body">
      <aside>
        <div class="navlb">运营监控</div>
        <nav class="nav">
          <a :class="{ on: page === 'overview' }" @click="go('overview')">
            <svg class="i" viewBox="0 0 16 16"><rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/></svg>概览统计
          </a>
          <a :class="{ on: page === 'intake' }" @click="go('intake')">
            <svg class="i" viewBox="0 0 16 16"><path d="M2.5 3.5h11l-4 5v4l-3 1v-5z"/></svg>纳入明细
          </a>
          <a :class="{ on: page === 'list' }" @click="go('list')">
            <svg class="i" viewBox="0 0 16 16"><ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/></svg>记忆清单
          </a>
        </nav>
      </aside>

      <div class="main">
        <OverviewPage v-show="page === 'overview'" />
        <IntakePage v-show="page === 'intake'" />
        <MemListPage v-show="page === 'list'" />
      </div>
    </div>

    <div class="toast" :class="{ on: toastOn }">
      <svg class="i" viewBox="0 0 16 16"><path d="M3 8.5l3 3 7-7"/></svg><span>{{ toastMsg }}</span>
    </div>
    <div class="srcnote">正式版 · 数据实时取自 GM Postgres（只读）</div>
  </div>
</template>

<script setup>
import { ref, provide, onMounted } from 'vue'
import api from './api.js'
import OverviewPage from './views/Overview.vue'
import IntakePage from './views/Intake.vue'
import MemListPage from './views/MemList.vue'

const page = ref('overview')
const dbOk = ref(false)
const toastMsg = ref('')
const toastOn = ref(false)
let toastTimer = null

function toast(msg) {
  toastMsg.value = msg
  toastOn.value = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toastOn.value = false), 2200)
}
provide('toast', toast)

function go(p) {
  page.value = p
  if (location.hash !== '#page=' + p) location.hash = '#page=' + p
  document.title = '智能体公共记忆运营监控平台 · ' + { overview: '概览统计', intake: '纳入明细', list: '记忆清单' }[p]
}
provide('go', go)

/* 深链：#page=intake&view=src&id=xxx 或 #page=list&view=mem&id=xxx，供截图/分享直达抽屉 */
function parseHash() {
  const m = location.hash.match(/#page=(\w+)(?:&view=(\w+))?(?:&id=([\w-]+))?/)
  if (!m) return null
  return { page: m[1], view: m[2] || '', id: m[3] || '' }
}
const deepLink = ref(parseHash())
provide('deepLink', deepLink)

onMounted(() => {
  const m = location.hash.match(/#page=(\w+)/)
  if (m && ['overview', 'intake', 'list'].includes(m[1])) page.value = m[1]
  api.health().then(() => (dbOk.value = true)).catch(() => (dbOk.value = false))
  window.addEventListener('hashchange', () => {
    const h = parseHash()
    if (h && ['overview', 'intake', 'list'].includes(h.page)) page.value = h.page
    deepLink.value = h
  })
})

/* 抽屉开合时同步 hash（开=带 view/id，关=清掉），保证刷新/分享可复现 */
function syncHash(p, view, id) {
  let h = '#page=' + p
  if (view && id) h += '&view=' + view + '&id=' + id
  if (location.hash !== h) location.hash = h
}
provide('syncHash', syncHash)
</script>
