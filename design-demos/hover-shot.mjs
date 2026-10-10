// 用 CDP 模拟鼠标悬停漏斗第 idx 条并截图（Node 原生 WebSocket，无额外依赖）
import { writeFileSync } from 'node:fs'

const IDX = Number(process.argv[2] ?? 1)
const OUT = process.argv[3] ?? 'hover.png'
const PORT = 9222

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function getTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      const t = list.find(x => x.type === 'page' && x.webSocketDebuggerUrl)
      if (t) return t
    } catch {}
    await sleep(500)
  }
  throw new Error('no CDP target')
}

const target = await getTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
function send(method, params = {}) {
  const msgId = ++id
  ws.send(JSON.stringify({ id: msgId, method, params }))
  return new Promise(res => pending.set(msgId, res))
}
ws.onmessage = ev => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id) }
}
await new Promise(res => (ws.onopen = res))

await sleep(4000) // 等 Vue 应用与数据渲染
const rect = await send('Runtime.evaluate', {
  expression: `(() => { const el = document.querySelectorAll('.fbar')[${IDX}]; if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })()`,
  returnByValue: true,
})
const pt = rect.result?.value
if (!pt) { console.error('bar not found'); process.exit(1) }

await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pt.x, y: pt.y, buttons: 0 })
await sleep(600)
const shot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(OUT, Buffer.from(shot.data, 'base64'))
console.log('saved', OUT, 'hover at', pt)
ws.close()
process.exit(0)
