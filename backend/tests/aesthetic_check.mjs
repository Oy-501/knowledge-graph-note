/**
 * 美学升级验收（真实浏览器）
 * 对着任务清单的 6 条验收标准逐条实测，而不是"看起来对了"。
 * 用法：node aesthetic_check.mjs
 */
import { spawn } from 'node:child_process'
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const APP = 'http://127.0.0.1:5174'
const API = 'http://127.0.0.1:8097/api'
const PORT = 9375
const OUT = '.tmp-verify/aesthetic-shots'
const sleep = ms => new Promise(r => setTimeout(r, ms))
mkdirSync(OUT, { recursive: true })

let pass = 0, fail = 0
const check = (name, ok, detail = '') => {
  ok ? pass++ : fail++
  console.log(`  [${ok ? 'PASS' : '**FAIL**'}] ${name}${detail ? ' —— ' + detail : ''}`)
}

const profile = mkdtempSync(join(tmpdir(), 'kg-aes-'))
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
  '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' })

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
const shot = async name => {
  const r = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, `${name}.png`), Buffer.from(r.data, 'base64'))
}

await send('Page.enable'); await send('Runtime.enable')
await send('Page.navigate', { url: APP }); await sleep(1500)
await ev(`const r = await fetch('${API}/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'demo_admin',password:'Demo#12345'})}); const j = await r.json(); localStorage.setItem('kg-session-token', j.token); return 1;`)
await send('Page.navigate', { url: APP }); await sleep(4500)

// ---- 暗色下的画布与控件（默认主题）----
const dark = await ev(`
  const html = document.documentElement;
  const isDark = html.classList.contains('dark');
  const canvas = document.querySelector('.canvas-wrap');
  const cs = canvas && getComputedStyle(canvas);
  const before = canvas && getComputedStyle(canvas, '::before');
  const circle = document.querySelector('.node-circle');
  const btn = document.querySelector('.el-button--primary:not(.is-text):not(.is-link)');
  const btnAfter = btn && getComputedStyle(btn, '::after');
  const sliderBar = document.querySelector('.el-slider__bar');
  const appView = document.querySelector('.app-view');
  return {
    isDark,
    canvasImage: cs ? cs.backgroundImage : '',
    canvasColor: cs ? cs.backgroundColor : '',
    canvasBeforeContent: before ? before.content : 'none',
    nodeFilter: circle ? getComputedStyle(circle).filter : null,
    btnShadow: btn ? getComputedStyle(btn).boxShadow : null,
    btnAfterContent: btnAfter ? btnAfter.content : null,
    sliderBg: sliderBar ? getComputedStyle(sliderBar).backgroundColor : null,
    sliderImg: sliderBar ? getComputedStyle(sliderBar).backgroundImage : null,
    viewAnim: appView ? getComputedStyle(appView).animation : null,
    radius: getComputedStyle(html).getPropertyValue('--radius').trim(),
    radiusSm: getComputedStyle(html).getPropertyValue('--radius-sm').trim(),
    radiusLg: getComputedStyle(html).getPropertyValue('--radius-lg').trim(),
    panelW: document.querySelector('.control-panel')?.getBoundingClientRect().width,
  };
`)
console.log('  主题：', dark.isDark ? '暗色' : '亮色')
check('画布没有彩色光斑（只剩网格）',
  !/radial-gradient/.test(dark.canvasImage) && /linear-gradient/.test(dark.canvasImage),
  dark.canvasImage.slice(0, 90))
check('画布 ::before 极光层已移除', dark.canvasBeforeContent === 'none' || dark.canvasBeforeContent === 'normal',
  `content=${dark.canvasBeforeContent}`)
check('节点静止时无发光', dark.nodeFilter === null || dark.nodeFilter === 'none', `filter=${dark.nodeFilter}`)
check('主按钮无辉光阴影', dark.btnShadow === null || dark.btnShadow === 'none', `box-shadow=${dark.btnShadow}`)
check('主按钮无扫光伪元素', dark.btnAfterContent === null || dark.btnAfterContent === 'none' || dark.btnAfterContent === 'normal',
  `::after content=${dark.btnAfterContent}`)
check('滑块为单色（无渐变）', dark.sliderImg === 'none' && !!dark.sliderBg,
  `bg=${dark.sliderBg} image=${dark.sliderImg}`)
check('视图切换为 0.18s 纯淡入', /0\.18s/.test(dark.viewAnim || ''), dark.viewAnim)
check('圆角三档 10/6/14', dark.radius === '10px' && dark.radiusSm === '6px' && dark.radiusLg === '14px',
  `${dark.radius} / ${dark.radiusSm} / ${dark.radiusLg}`)
check('控制面板宽度 288', Math.round(dark.panelW) === 288, `${Math.round(dark.panelW)}px`)
await shot('01-dark-graph')

// ---- 排版：大写清零、面板正文 ≥12px ----
const typo = await ev(`
  const upper = [...document.querySelectorAll('*')].filter(el => {
    const t = getComputedStyle(el).textTransform;
    return t === 'uppercase' && (el.innerText || '').trim().length > 0;
  }).map(el => (el.innerText || '').trim().slice(0, 20));
  const foot = document.querySelector('.panel-foot');
  const h3 = document.querySelector('.panel-section h3');
  const label = document.querySelector('.node-label');
  return {
    upperCount: upper.length, upperSample: upper.slice(0, 5),
    footSize: foot ? getComputedStyle(foot).fontSize : null,
    h3Size: h3 ? getComputedStyle(h3).fontSize : null,
    nodeLabelSize: label ? getComputedStyle(label).fontSize : null,
  };
`)
check('全站没有 uppercase 文本', typo.upperCount === 0, typo.upperSample.join(' / ') || '无')
check('面板状态行 ≥12px', parseFloat(typo.footSize) >= 12, typo.footSize)
check('面板小标题 ≥12px', parseFloat(typo.h3Size) >= 12, typo.h3Size)
check('图谱标签 12px', typo.nodeLabelSize === null || parseFloat(typo.nodeLabelSize) >= 12, typo.nodeLabelSize)

// ---- 切到亮色，确认没有断裂 ----
await ev(`document.querySelector('.nav-theme-btn')?.click(); return 1;`)
await sleep(1200)
const light = await ev(`
  const html = document.documentElement;
  const canvas = document.querySelector('.canvas-wrap');
  const cs = getComputedStyle(canvas);
  const body = getComputedStyle(document.body);
  return {
    isDark: html.classList.contains('dark'),
    canvasImage: cs.backgroundImage,
    bodyColor: body.color,
    primary: getComputedStyle(html).getPropertyValue('--accent').trim(),
  };
`)
check('切到亮色主题成功', light.isDark === false, `--accent=${light.primary}`)
check('亮色下画布同样无彩色光斑', !/radial-gradient/.test(light.canvasImage),
  light.canvasImage.slice(0, 70))
await shot('02-light-graph')

check('全程 0 条未捕获异常', errors.length === 0, errors.join(' | ') || '无')

console.log(`\n  共 ${pass + fail} 项，通过 ${pass}，失败 ${fail}`)
console.log(`  截图：${OUT}/`)
ws.close(); chrome.kill()
process.exit(fail === 0 ? 0 : 1)
