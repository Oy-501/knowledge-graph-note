/**
 * 模块令牌与组件原语的实测（真实浏览器）
 * 验证：切页签只换「标记位」颜色、组件样式没被改坏、0 未捕获异常。
 * 用法：node check_module_tokens.mjs
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const APP = 'http://127.0.0.1:5174'
const API = 'http://127.0.0.1:8097/api'
const PORT = 9371
const OUT = '.tmp-verify/module-shots'
const sleep = ms => new Promise(r => setTimeout(r, ms))
mkdirSync(OUT, { recursive: true })

let pass = 0, fail = 0
const check = (name, ok, detail = '') => {
  ok ? pass++ : fail++
  console.log(`  [${ok ? 'PASS' : '**FAIL**'}] ${name}${detail ? ' —— ' + detail : ''}`)
}

const profile = mkdtempSync(join(tmpdir(), 'kg-mod-'))
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
  '--window-size=1440,960', 'about:blank'], { stdio: 'ignore' })

let wsUrl
for (let i = 0; i < 60; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
    const p = list.find(t => t.type === 'page')
    if (p) { wsUrl = p.webSocketDebuggerUrl; break }
  } catch { }
  await sleep(200)
}
const ws = new WebSocket(wsUrl)
await new Promise(r => { ws.onopen = r })
let seq = 0
const pending = new Map()
const errors = []
ws.onmessage = e => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); return }
  if (m.method === 'Runtime.exceptionThrown') errors.push((m.params.exceptionDetails?.exception?.description || '').slice(0, 160))
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
    errors.push(m.params.args.map(a => a.value ?? a.description ?? '').join(' ').slice(0, 160))
  }
}
const send = (method, params = {}) => new Promise(r => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })) })
const ev = async expr => {
  const r = await send('Runtime.evaluate', { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 300))
  return r.result?.value
}

await send('Page.enable'); await send('Runtime.enable')
await send('Page.navigate', { url: APP }); await sleep(1500)
await ev(`const r = await fetch('${API}/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'demo_admin',password:'Demo#12345'})}); const j = await r.json(); localStorage.setItem('kg-session-token', j.token); return 1;`)
await send('Page.navigate', { url: APP }); await sleep(3200)

const clickTab = label => ev(`
  const norm = s => (s || '').replace(/\\s+/g, '');
  const L = norm(${JSON.stringify('')} || '${label}');
  const cands = [...document.querySelectorAll('button, a, li, div, span')]
    .filter(e => { const t = norm(e.innerText); return t === L || t === L + '1' || new RegExp('^' + L + '\\\\d+$').test(t) })
    .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  if (!cands.length) return false;
  cands[0].click(); return true;
`)

async function markerOf(viewId) {
  // 有的视图是纯画布（图谱页没有页面标题），它的身份落点是导航上的当前页下划线
  return ev(`
    const root = document.querySelector('#${viewId}');
    const h2 = root && root.querySelector('h2');
    const tab = document.querySelector('.nav-tab.active');
    const el = h2 || tab;
    if (!el) return null;
    const cs = getComputedStyle(el, h2 ? '::before' : '::after');
    return { color: cs.backgroundColor, w: cs.width, h: cs.height,
             via: h2 ? 'h2::before' : 'nav underline',
             shell: document.querySelector('.app-shell').dataset.module };
  `)
}

const MODULES = [
  ['知识图谱', 'view-graph'],
  ['知识库', 'view-kb'],
  ['图谱总结', 'view-summary'],
  ['后台管理', 'view-admin'],
]
const marks = []
for (const [label, view] of MODULES) {
  await clickTab(label)
  await sleep(1600)
  const m = await markerOf(view)
  marks.push({ label, ...m })
  check(`「${label}」有模块色标记`, !!m && m.color && m.color !== 'rgba(0, 0, 0, 0)',
    m ? `${m.via} ${m.color} · ${m.w}×${m.h}` : '找不到标记')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false })
  const shot = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, `${label}.png`), Buffer.from(shot.data, 'base64'))
}

const uniq = new Set(marks.map(m => m.color))
check('不同模块的标记色确实不同（说明令牌生效）', uniq.size >= 3,
  [...uniq].join(' / '))

// 组件原语是否真的接管了样式（先确保有内容：空态下没有分节）
await clickTab('图谱总结')
await sleep(1500)
if (await ev(`return !![...document.querySelectorAll('button')].find(x => (x.innerText || '').trim() === '生成总结')`)) {
  await ev(`[...document.querySelectorAll('button')].find(x => (x.innerText || '').trim() === '生成总结').click(); return 1`)
}
for (let i = 0; i < 90; i++) {
  if (await ev(`return !!document.querySelector('.rpt-figures')`)) break
  await sleep(500)
}
await sleep(1200)
const btn = await ev(`
  const b = document.querySelector('.rpt-bar-export .u-btn');
  if (!b) return null;
  const cs = getComputedStyle(b);
  return { h: cs.height, size: cs.fontSize, radius: cs.borderRadius, color: cs.color,
           cursor: cs.cursor, cls: b.className };
`)
check('导出按钮改用原语（.u-btn--text）', !!btn && /u-btn/.test(btn.cls),
  btn ? `${btn.cls} · ${btn.size} · r=${btn.radius}` : '没找到')

const secTitle = await ev(`
  const s = document.querySelector('.u-sec-title');
  if (!s) return null;
  const no = s.querySelector('.u-sec-title__no');
  const fill = s.querySelector('.u-sec-title__fill');
  return { no: no ? getComputedStyle(no).color : null,
           fillW: fill ? Math.round(fill.getBoundingClientRect().width) : 0,
           h3: s.querySelector('h3')?.innerText };
`)
check('分节头用原语且发丝线仍在', !!secTitle && secTitle.fillW > 20,
  secTitle ? `栏号 ${secTitle.no} · 发丝线 ${secTitle.fillW}px · 标题「${secTitle.h3}」` : '没找到')

// 内容态截图：确认分节头换成原语后，栏号/发丝线/缩放档的排布没坏
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 960, deviceScaleFactor: 1, mobile: false })
const last = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(join(OUT, '图谱总结-内容态.png'), Buffer.from(last.data, 'base64'))

check('全程 0 条未捕获异常', errors.length === 0, errors.join(' | ') || '无')

console.log(`\n  共 ${pass + fail} 项，通过 ${pass}，失败 ${fail}`)
console.log(`  截图：${OUT}/`)
ws.close(); chrome.kill()
process.exit(fail === 0 ? 0 : 1)
