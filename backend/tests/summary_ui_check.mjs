/**
 * 总结页改版的行为检查（真实浏览器）
 * 覆盖：版面结构、流程图文字可读、适应档、放大后可滚到边缘、0 未捕获异常。
 * 用法：node check_summary_ui.mjs
 */
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const APP = 'http://127.0.0.1:5174'
const API = 'http://127.0.0.1:8097/api'
const PORT = 9369
const sleep = ms => new Promise(r => setTimeout(r, ms))

let pass = 0, fail = 0
const check = (name, ok, detail = '') => {
  ok ? pass++ : fail++
  console.log(`  [${ok ? 'PASS' : '**FAIL**'}] ${name}${detail ? ' —— ' + detail : ''}`)
}

const profile = mkdtempSync(join(tmpdir(), 'kg-check-'))
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
  '--window-size=1440,1000', 'about:blank'], { stdio: 'ignore' })

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
  if (m.method === 'Runtime.exceptionThrown') {
    errors.push((m.params.exceptionDetails?.exception?.description || '').slice(0, 160))
  }
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
await send('Page.navigate', { url: APP }); await sleep(3000)
await ev(`const n=s=>(s||'').replace(/\\s+/g,''); const L=n('图谱总结'); const c=[...document.querySelectorAll('button,a,li,div,span')].filter(e=>{const t=n(e.innerText);return t===L||t===L+'1'}).sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length); c[0]&&c[0].click(); return 1;`)
await sleep(1200)
if (await ev(`return !![...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='生成总结')`)) {
  await ev(`[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='生成总结').click(); return 1`)
}
for (let i = 0; i < 90; i++) { if (await ev(`return !!document.querySelector('.rpt-figures')`)) break; await sleep(500) }
await sleep(1500)

const shape = await ev(`
  return {
    secs: document.querySelectorAll('.rpt-sec').length,
    figs: document.querySelectorAll('.rpt-fig').length,
    paths: document.querySelectorAll('.rpt-path').length,
    steps: document.querySelectorAll('.rpt-step').length,
    digest: (document.querySelector('.rpt-digest-body')?.innerText || '').length,
  };
`)
check('五个区块齐全', shape.secs === 5, `secs=${shape.secs}`)
check('概览五组数字', shape.figs === 5, `figs=${shape.figs}`)
check('学习主线渲染出步骤', shape.paths > 0 && shape.steps > 0, `${shape.paths} 条 / ${shape.steps} 步`)
check('AI 摘要并置可读', shape.digest > 100, `${shape.digest} 字符`)

// ---- 100% 下节点文字的实际像素高 ----
const textInfo = await ev(`
  const svg = document.querySelector('.mflow svg');
  if (!svg) return { ok: false };
  const t = svg.querySelector('g.node text, g.node tspan, g.node foreignObject');
  const r = t && t.getBoundingClientRect();
  const f = document.querySelector('.mflow');
  const sizer = document.querySelector('.mflow-sizer');
  return { ok: !!r, h: r ? +r.height.toFixed(1) : null,
           sizerW: Math.round(sizer.getBoundingClientRect().width),
           frameW: f.clientWidth, frameH: f.clientHeight,
           scrolled: f.scrollLeft > 0 || f.scrollTop > 0 };
`)
check('流程节点文字 ≥ 8px', textInfo.ok && textInfo.h >= 8,
  `文字高 ${textInfo.h}px · 框 ${textInfo.frameW}×${textInfo.frameH}`)
check('默认滚到节点密集区（不是空角落）', textInfo.scrolled === true,
  `已滚动=${textInfo.scrolled}`)

// ---- 适应档：整图缩进框内 ----
await ev(`const b=[...document.querySelectorAll('.rpt-zoom .el-radio-button')].find(x=>/适应/.test(x.innerText)); b&&b.click(); return 1;`)
await sleep(900)
const fit = await ev(`
  const f = document.querySelector('.mflow');
  const s = document.querySelector('.mflow-sizer');
  return { sizerW: Math.round(s.getBoundingClientRect().width),
           frameW: f.clientWidth, sw: f.scrollWidth, cw: f.clientWidth,
           tag: document.querySelector('.mflow-zoomtag')?.innerText.trim() || '' };
`)
check('适应档把整图缩进框内（无横向滚动）', fit.sw <= fit.cw + 2,
  `图 ${fit.sizerW}px / 框 ${fit.frameW}px · 角标「${fit.tag}」`)

// ---- 130%：占位尺寸跟着放大，右下角能滚到 ----
await ev(`const b=[...document.querySelectorAll('.rpt-zoom .el-radio-button')].find(x=>/130%/.test(x.innerText)); b&&b.click(); return 1;`)
await sleep(900)
const zoomed = await ev(`
  const f = document.querySelector('.mflow');
  const s = document.querySelector('.mflow-sizer');
  const before = Math.round(s.getBoundingClientRect().width);
  f.scrollLeft = f.scrollWidth; f.scrollTop = f.scrollHeight;
  return { sizerW: before, sw: f.scrollWidth, maxLeft: Math.round(f.scrollLeft + f.clientWidth),
           maxTop: Math.round(f.scrollTop + f.clientHeight), sh: f.scrollHeight };
`)
// 100% 时的占位宽 × 1.3 应等于现在的占位宽（±2px）
const expect130 = Math.round(textInfo.sizerW * 1.3)
check('130% 时占位尺寸随之放大',
  Math.abs(zoomed.sizerW - expect130) <= 2,
  `占位 ${textInfo.sizerW} → ${zoomed.sizerW}px（期望 ${expect130}）`)
check('130% 能滚到右边缘（不再被布局裁掉）', zoomed.maxLeft >= zoomed.sw - 2,
  `可视右界 ${zoomed.maxLeft} / 总宽 ${zoomed.sw}`)
check('130% 能滚到下边缘', zoomed.maxTop >= zoomed.sh - 2,
  `可视下界 ${zoomed.maxTop} / 总高 ${zoomed.sh}`)

check('全程 0 条未捕获异常', errors.length === 0, errors.join(' | ') || '无')

console.log(`\n  共 ${pass + fail} 项，通过 ${pass}，失败 ${fail}`)
ws.close(); chrome.kill()
process.exit(fail === 0 ? 0 : 1)
