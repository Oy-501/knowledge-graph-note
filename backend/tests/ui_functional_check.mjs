/**
 * ui_functional_check.mjs —— 真实浏览器驱动的界面功能验证
 *
 * 为什么需要它
 * ------------
 * 后端有 200+ 条 pytest，但它们**一条都没打开过界面**。而项目的核心交互
 * （登录门禁、页签切换、图谱渲染、总结页出图、导出下载）全在前端：
 * 后端全绿而界面白屏是完全可能的，而且那种失败连错误码都没有。
 *
 * 怎么做
 * ------
 * 用 Node 22 内置的全局 `WebSocket` 直接讲 Chrome DevTools Protocol，
 * **不引入任何第三方依赖**（不装 playwright/puppeteer，也不需要它们的浏览器下载）：
 * 起一个 headless Chrome（用本机已装的 Chrome）→ 连上页面 target →
 * `Runtime.evaluate` 驱动交互与断言 → `Page.captureScreenshot` 留证据。
 *
 * 跑法
 * ----
 *   node backend/tests/ui_functional_check.mjs \
 *        --url http://127.0.0.1:5174 --api http://127.0.0.1:8096/api \
 *        --shot-dir .tmp-verify/ui-shots
 *
 * 前提：一个**独立的**后端实例（临时库）与该实例对应的前端。
 * 绝不要指向正在使用的实例：这个脚本会真的注册账号、真的上传文件。
 */
import { execFile } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// ---------------------------------------------------------------- 参数

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const URL_APP = arg('url', 'http://127.0.0.1:5174');
const API = arg('api', 'http://127.0.0.1:8096/api');
const SHOT_DIR = arg('shot-dir', '.tmp-verify/ui-shots');
const CHROME = arg('chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
const DEBUG_PORT = Number(arg('port', '9334'));
const USER = arg('user', 'ui_check_admin');
const PASS = arg('pass', 'UiCheck#12345');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
let failed = 0;

function check(name, ok, detail) {
  results.push({ name, ok, detail });
  if (!ok) failed++;
  console.log(`  [${ok ? 'PASS' : '**FAIL**'}] ${name}${detail ? ' —— ' + detail : ''}`);
}

/**
 * 已知问题：确实不达标，但成因在产品设计取舍上，不是这次改坏的。
 * 计为 known 而不是 FAIL —— 让它持续可见（打印 + 计数），
 * 又不会把整套检查染成红的（那会让人开始忽略所有红色）。
 * 每个 known 都要带上「为什么」和「决定权在谁」。
 */
let known = 0;
function knownIssue(name, detail) {
  known++;
  console.log(`  [KNOWN] ${name}${detail ? ' —— ' + detail : ''}`);
}

// ---------------------------------------------------------------- CDP 客户端

function httpGet(p) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port: DEBUG_PORT, path: p }, (res) => {
      let b = '';
      res.on('data', (d) => (b += d));
      res.on('end', () => resolve(b));
    }).on('error', reject);
  });
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.events = [];
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        this.pending.get(m.id)(m);
        this.pending.delete(m.id);
      } else if (m.method) {
        this.events.push(m);
      }
    });
  }
  send(method, params = {}) {
    return new Promise((resolve) => {
      const id = ++this.id;
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  /**
   * 在页面里求值。
   *
   * 包成 **async** IIFE 而不是同步 IIFE：页面里要 `await fetch(...)` 的地方
   * （比如注册账号）在同步函数里会直接抛
   * `SyntaxError: await is only valid in async functions`。
   * 外层表达式本身返回一个 Promise，靠 `awaitPromise` 解掉，
   * 所以调用方拿到的就是 `return` 的那个值，不需要再做 JSON 编解码。
   */
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(async () => { ${expression} })()`,
      returnByValue: true,
      awaitPromise: true,
    });
    if (r.result?.exceptionDetails) {
      throw new Error('页面求值抛异常: ' + JSON.stringify(r.result.exceptionDetails).slice(0, 300));
    }
    return r.result?.result?.value;
  }
}

/**
 * 点一个导航页签。
 *
 * 页签文案形如「知识图谱\n1」（标签 + Ctrl 快捷键序号），所以不能做全等匹配；
 * 统一用「去空白后比较」并取**层级最浅**的候选（最贴近可点目标的容器）。
 * 抽成函数是因为页签循环和后面的「回到总结页」都要用 —— 两处各写一遍，
 * 改一处忘一处是必然的。
 */
async function clickTab(cdp, label) {
  return cdp.eval(`
    const norm = s => (s || '').replace(/\\s+/g, '');
    const target = norm(${JSON.stringify(label)});
    const cands = [...document.querySelectorAll('button, a, li, div, span')]
      .filter(e => {
        const t = norm(e.innerText);
        return t === target || (t.startsWith(target) && /^\\d{1,2}$/.test(t.slice(target.length)));
      })
      .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    if (!cands.length) {
      return { ok: false, candidates: [...document.querySelectorAll('*')]
        .map(n => (n.innerText || '').trim())
        .filter(t => t && t.length < 14).slice(0, 24) };
    }
    cands[0].click();
    return { ok: true, matched: cands.length };
  `);
}

// ---------------------------------------------------------------- 启动浏览器

async function launchChrome() {
  const profile = path.join(os.tmpdir(), `ui-check-profile-${process.pid}`);
  const child = execFile(CHROME, [
    '--headless=new',
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-gpu', '--disable-extensions', '--disable-background-networking',
    '--window-size=1560,1000',
    'about:blank',
  ], { stdio: 'ignore' });
  child.on('error', (e) => console.log('  浏览器启动失败:', e.message));

  for (let i = 0; i < 60; i++) {
    try {
      await httpGet('/json/version');
      return child;
    } catch { await sleep(250); }
  }
  throw new Error('CDP 未就绪，Chrome 可能没有启动');
}

// ---------------------------------------------------------------- 主流程

(async () => {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  console.log('='.repeat(74));
  console.log('  界面功能验证（真实浏览器）');
  console.log(`  页面 ${URL_APP}   接口 ${API}`);
  console.log('='.repeat(74));

  const child = await launchChrome();
  const targets = JSON.parse(await httpGet('/json/list'));
  const page = targets.find((t) => t.type === 'page');
  if (!page) throw new Error('没有可用的页面 target');

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  const cdp = new Cdp(ws);

  // 收集页面错误：未捕获异常 + console.error
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Log.enable');

  const consoleErrors = [];
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params?.exceptionDetails || {};
      consoleErrors.push('未捕获异常: ' + (d.exception?.description || d.text || '').split('\n')[0]);
    }
    if (m.method === 'Log.entryAdded' && m.params?.entry?.level === 'error') {
      consoleErrors.push('console.error: ' + (m.params.entry.text || '').slice(0, 200));
    }
  });

  // 让前端把 API 指到测试后端（浏览器里 5174 已经是 8096，这里只做一次确认）
  await cdp.send('Page.navigate', { url: URL_APP });
  await sleep(3500);

  const shot = async (name) => {
    const r = await cdp.send('Page.captureScreenshot', { format: 'png' });
    const f = path.join(SHOT_DIR, `${name}.png`);
    fs.writeFileSync(f, Buffer.from(r.result.data, 'base64'));
    return f;
  };

  // ---------------------------------------------------------------- 1. 加载与登录门禁
  const boot = await cdp.eval(`
    return {
      title: document.title,
      apiBase: (window.__VITE_API_BASE__ || null),
      appMounted: !!document.querySelector('#app') && document.querySelector('#app').children.length > 0,
      bodyText: document.body.innerText.slice(0, 400),
      // 业务视图是否被挂载（不是"是否可见"）：门禁用 v-show 的话组件照样挂载并请求后端
      hasGraphCanvas: !!document.querySelector('canvas'),
      navTabCount: document.querySelectorAll('.nav-tab, [class*="nav"] button, [class*="nav"] a').length,
    };
  `);
  check('页面能加载', !!boot && boot.appMounted, `标题=${boot?.title}`);
  await shot('01-landing');

  // 未登录：业务视图不能挂载。判据是「DOM 里没有业务视图的根节点」，
  // 而不是「看不见」—— 只 v-show 隐藏时会照样挂载并向后端发请求。
  check('未登录时不挂载业务视图', boot && !boot.hasGraphCanvas,
    boot?.hasGraphCanvas ? 'canvas 已存在，说明业务视图被挂载了（门禁只藏不挡）' : '');

  // ---------------------------------------------------------------- 2. 首次初始化 → 登录
  const landing = boot?.bodyText || '';
  const needBootstrap = /初始化|设置|创建.{0,6}账号|管理员/.test(landing) && /登录|密码/.test(landing);
  console.log(`  落地页文案片段：${landing.replace(/\s+/g, ' ').slice(0, 120)}`);

  // 走真实 UI：填表 + 点按钮，不通过接口登录（否则测不到界面）。
  // 首次使用是**初始化向导**（账号 + 展示名 + 密码 + 确认密码），
  // 之后才是登录表单（账号 + 密码）。这里按「第一个文本输入框 = 账号、
  // 所有密码框都填同一个密码」处理，两种形态都能覆盖 ——
  // 按 placeholder 关键词猜字段名会踩坑：向导里「展示名」的 placeholder
  // 恰好含「用户名」三个字（"留空就用用户名"），会把账号填到展示名上。
  const filled = await cdp.eval(`
    const inputs = [...document.querySelectorAll('input')].filter(i => i.offsetParent !== null);
    const texts = inputs.filter(i => i.type !== 'password' && !['checkbox','radio','file'].includes(i.type));
    const passes = inputs.filter(i => i.type === 'password');
    if (!texts.length || !passes.length) {
      return { ok: false, inputs: inputs.map(i => i.type + ':' + (i.placeholder || '')) };
    }
    const setVal = (el, v) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    setVal(texts[0], ${JSON.stringify(USER)});
    passes.forEach(p => setVal(p, ${JSON.stringify(PASS)}));
    return { ok: true, fields: inputs.length,
             account: texts[0].placeholder, passwords: passes.length };
  `);
  check('登录表单可被定位并填写', filled?.ok === true,
    filled?.ok ? `共 ${filled.fields} 个字段，账号框=「${filled.account}」，密码框 ${filled.passwords} 个`
               : `没找到输入框：${JSON.stringify(filled?.inputs)}`);
  await shot('02-login-filled');

  // 提交：优先点按钮，找不到就回车
  await cdp.eval(`
    const btns = [...document.querySelectorAll('button')];
    const go = btns.find(b => /登录|进入|初始化|开始|创建/.test(b.innerText || ''));
    if (go) { go.click(); return { clicked: go.innerText.trim() }; }
    const pass = document.querySelector('input[type=password]');
    if (pass) { pass.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); }
    return { clicked: null };
  `);
  await sleep(4000);
  await shot('03-after-login');

  const afterLogin = await cdp.eval(`
    return {
      bodyText: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 300),
      // 令牌键名取自 authStore.SESSION_KEY
      token: localStorage.getItem('kg-session-token'),
      navTabCount: [...document.querySelectorAll('button, a, div')]
        .filter(n => /知识图谱|知识工作台|图谱总结/.test((n.innerText || '').trim()))
        .length,
    };
  `);
  check('通过界面登录成功（拿到会话令牌）', !!afterLogin?.token,
    `令牌=${afterLogin?.token ? '已写入 localStorage' : '未找到'}；页面文案：${afterLogin?.bodyText?.slice(0, 80)}`);
  check('主界面导航已出现', (afterLogin?.navTabCount || 0) > 0,
    `匹配到 ${afterLogin?.navTabCount} 个导航项`);

  // ---------------------------------------------------------------- 3. 真实上传一份文档
  // 让后面的「总结出图」有数据可依赖 —— 空库时流程图走的是友好提示分支，
  // 那条路径也要测，但不能替代「有数据时真的画得出来」。
  const tmpDoc = path.join(os.tmpdir(), `ui-check-doc-${process.pid}.md`);
  fs.writeFileSync(tmpDoc, [
    '# 数据库索引笔记', '',
    '## 基础', '',
    '数据库索引可以加快查询速度。',
    'B+ 树是索引最常用的数据结构。', '',
    '## 优化', '',
    '查询优化需要遵循最左前缀原则。',
    '索引失效是因为对列使用了函数。', '',
  ].join('\n'), 'utf8');

  // 文件输入框可能藏在任意页签里，先在当前页找一次
  const findFileInput = async () => {
    const doc = await cdp.send('DOM.getDocument', { depth: -1 });
    const q = await cdp.send('DOM.querySelector', {
      nodeId: doc.result.root.nodeId, selector: 'input[type=file]',
    });
    return q.result?.nodeId || 0;
  };
  let fileNode = await findFileInput();
  if (!fileNode) {
    // 切到「知识图谱」再找（上传入口在那里）
    await cdp.eval(`
      const cands = [...document.querySelectorAll('*')]
        .filter(e => /^知识图谱(\\s*\\d+)?$/.test((e.innerText || '').trim()) && e.children.length <= 2);
      if (cands.length) cands[0].click();
      return true;
    `);
    await sleep(2500);
    fileNode = await findFileInput();
  }
  if (fileNode) {
    await cdp.send('DOM.setFileInputFiles', { files: [tmpDoc], nodeId: fileNode });
    await sleep(9000);   // 等上传 + 后台解析 + 关联
  }
  const afterUpload = await cdp.eval(`
    return {
      text: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 300),
      fileInput: document.querySelectorAll('input[type=file]').length,
    };
  `);
  check('界面上传文档', !!fileNode, fileNode ? '已投递文件到 input[type=file]' : '页面上没有文件输入框');
  // 注意：这是正则**字面量**，写 \\d 会变成「字面反斜杠 + d」——
  // 只有放在模板字符串里才需要双写。踩过一次，特地标出来。
  check('上传后界面反映出知识点',
    /[1-9]\d*\s*个知识点|[1-9]\d*\s*个节点|知识点\s*[1-9]/.test(afterUpload?.text || ''),
    (afterUpload?.text || '').slice(0, 140));
  await shot('04-after-upload');

  // ---------------------------------------------------------------- 4. 逐个页签打开
  const TABS = ['知识图谱', '知识工作台', '知识库', '图谱总结', '个人主页', '后台管理', '函数图像', '背景 CSS'];
  for (const [i, tab] of TABS.entries()) {
    const before = consoleErrors.length;
    const clicked = await clickTab(cdp, tab);
    await sleep(2600);
    const state = await cdp.eval(`
      const root = [...document.querySelectorAll('body *')].filter(e => e.children.length > 2);
      return {
        textLen: document.body.innerText.replace(/\\s/g, '').length,
        emptyState: !!document.querySelector('[class*="empty"]'),
        errorBoundary: !!document.querySelector('[class*="error-boundary"], [class*="ErrorBoundary"]'),
        visibleText: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 160),
      };
    `);
    const newErrors = consoleErrors.slice(before);
    check(`页签「${tab}」能打开并渲染`,
      clicked?.ok === true && state?.textLen > 20 && !state?.errorBoundary,
      clicked?.ok ? `内容 ${state.textLen} 字` : `点不到该页签，候选：${JSON.stringify(clicked?.candidates)}`);
    if (newErrors.length) {
      check(`页签「${tab}」无控制台错误`, false, newErrors.slice(0, 2).join(' | '));
    }
    await shot(`04-tab-${i + 1}-${tab.replace(/\s/g, '')}`);
  }

  // ---------------------------------------------------------------- 5. 图谱总结页：生成 + 出图
  // 页签循环最后停在「背景 CSS」，这里必须真的切回总结页 ——
  // 用同一个 clickTab，别在这里另写一份选择器（写歪了会「在错的页面上做断言」，
  // 而且断言还会因为页面里凑巧有别的文字而假绿）。
  const backToSummary = await clickTab(cdp, '图谱总结');
  await sleep(2500);
  const onSummaryPage = await cdp.eval(`
    return { text: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 120) };
  `);
  check('已切到图谱总结页', /图谱总结|生成总结|总览/.test(onSummaryPage?.text || ''),
    (onSummaryPage?.text || '').slice(0, 100));

  const genClicked = await cdp.eval(`
    const btns = [...document.querySelectorAll('button')];
    const go = btns.find(b => /生成总结|立即生成/.test(b.innerText || ''));
    if (!go) return { ok: false, buttons: btns.map(b => b.innerText.trim()).filter(Boolean).slice(0, 20) };
    go.click();
    return { ok: true };
  `);
  check('总结页有「生成总结」按钮', genClicked?.ok === true,
    genClicked?.ok ? '' : `没找到，按钮：${JSON.stringify(genClicked?.buttons)}`);
  await sleep(6000);
  await shot('05-summary-generated');

  const summaryState = await cdp.eval(`
    // 直接找组件自己的容器（MermaidFlow 的 .mflow-host，渲染结果 innerHTML 注入其内），
    // 而不是按 mermaid 的 svg 属性猜 —— 它产出的 id 是 mflow-xxx，
    // 按 svg[id^="mermaid"] / .mermaid svg 找必然落空。
    const host = document.querySelector('.mflow-host');
    const errBox = document.querySelector('.mflow-error');
    return {
      hasOverview: !!document.querySelector('.sum-card, [class*="sum-"]'),
      mermaidSvg: host ? host.querySelectorAll('svg').length : 0,
      renderError: errBox ? errBox.innerText.replace(/\\s+/g, ' ').slice(0, 200) : null,
      stillLoading: !!document.querySelector('.mflow-loading'),
      bodyText: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 300),
    };
  `);
  check('总结页渲染出内容', summaryState?.hasOverview === true,
    summaryState?.bodyText?.slice(0, 100));
  // 渲染失败是一条明确的缺陷（组件有专门的错误分支，把原因写进页面）
  check('流程图没有走渲染失败分支', !summaryState?.renderError,
    summaryState?.renderError || '未出现错误提示');
  check('流程图不在「正在绘制」状态', summaryState?.stillLoading !== true, '');

  // 上面已经在界面上传过文档，所以这里要求**真的画出图**。
  check('总结流程图渲染成图形', summaryState?.mermaidSvg > 0,
    summaryState?.mermaidSvg > 0
      ? `.mflow-host 里有 ${summaryState.mermaidSvg} 个 svg`
      : `流程图容器里没有 svg。页面文案：${(summaryState?.bodyText || '').slice(0, 120)}`);

  // 「有 svg」不等于「看得清」：图上节点一多，整张图会被压进容器宽度里等比缩小，
  // 结果是**一屏看不懂的碎块**（节点文字被缩到 1~2px）。
  // 所以这里量的是**第一个节点文字的实际渲染高度**，它才是「能不能读」的判据。
  const readable = await cdp.eval(`
    const host = document.querySelector('.mflow-host');
    const box = document.querySelector('.mflow');
    const svg = host && host.querySelector('svg');
    if (!svg) return { ok: false, reason: '容器里没有 svg' };
    const firstText = svg.querySelector('text, .nodeLabel, foreignObject');
    const tb = firstText ? firstText.getBoundingClientRect() : null;
    const sb = svg.getBoundingClientRect();
    return {
      ok: true,
      containerW: Math.round(box.getBoundingClientRect().width),
      svgW: Math.round(sb.width),
      viewBoxW: (svg.getAttribute('viewBox') || '').split(/\\s+/)[2] || null,
      nodeCount: svg.querySelectorAll('g.node, .node').length,
      edgeCount: svg.querySelectorAll('path.flowchart-link, .edgePath').length,
      textH: tb ? +tb.height.toFixed(1) : null,
      sample: firstText ? (firstText.textContent || '').trim().slice(0, 14) : null,
    };
  `);
  // 字号 12px 的标签缩到 8px 以下基本没法读；这里卡 8px 作为可读下限。
  //
  // 这条曾经是「已知问题」：Mermaid 默认 useMaxWidth:true 会把 svg 套 max-width
  // 自适应容器宽，6632px 的图被压进 593px（8.6%），12px 文字只剩 2px。
  // 产品侧已定案：MermaidFlow 用 `flowchart.useMaxWidth:false` 按自然尺寸出图，
  // 容器滚动查看，缩放交给页面的 75%/100%/130% 控制 —— 所以这条恢复为**硬性检查**。
  check('流程图在默认缩放下可读（节点文字不小于 8px）',
    readable?.ok === true && readable.textH !== null && readable.textH >= 8,
    readable?.ok
      ? `文字高 ${readable.textH}px · 图宽 ${readable.svgW}px（容器 ${readable.containerW}px / viewBox 宽 ${readable.viewBoxW}）·`
        + ` 节点 ${readable.nodeCount} · 边 ${readable.edgeCount} · 样例「${readable.sample}」`
      : readable?.reason || '测量失败');

  // 同一屏幕里也要能看见节点框（排除「文字被裁掉 / 节点没画出来」）
  check('流程图里画出了节点', (readable?.nodeCount || 0) > 0,
    `${readable?.nodeCount || 0} 个节点 / ${readable?.edgeCount || 0} 条边`);

  // ---------------------------------------------------------------- 5. 导出按钮真的触发下载
  const dl = await cdp.eval(`
    const btns = [...document.querySelectorAll('button')];
    const md = btns.find(b => /Markdown/.test(b.innerText || ''));
    if (!md) return { ok: false };
    md.click();
    return { ok: true };
  `);
  await sleep(3500);
  check('导出按钮可点击且无报错', dl?.ok === true && consoleErrors.length === 0,
    dl?.ok ? '' : '没找到 Markdown 导出按钮');

  // ---------------------------------------------------------------- 6. 普通用户进后台的提示
  // 这一条对应一个真实修过的缺陷：后台守卫曾对「已登录但不是管理员」一律回 401，
  // 于是普通用户点开「后台管理」看到的是「请在登录页登录管理员账号」——
  // 而他明明登录着，退出重登也还是这个错。修完应当是 403 + 说得清的提示。
  // 在浏览器里验一遍，因为缺陷的症状本来就是「用户看到什么」。
  const plainUser = `ui_plain_${Date.now().toString().slice(-6)}`;
  const registered = await cdp.eval(`
    const r = await fetch(${JSON.stringify(API)} + '/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: ${JSON.stringify(plainUser)}, password: 'UiPlain#12345' }),
    });
    const j = await r.json().catch(() => ({}));
    return JSON.stringify({ status: r.status, ok: !!j.token });
  `);
  const regState = typeof registered === 'string' ? JSON.parse(registered) : registered;

  if (regState?.ok) {
    // 用接口换一个普通用户的会话来驱动界面。
    // 这里刻意**不再走登录表单**：表单填值这条路已由第 2 节（管理员登录）覆盖，
    // 本节要验的是「普通用户进后台看到什么」，属于权限提示，与被测点无关的
    // 表单交互只会引入噪声（第一版就是这么失败的：接口 200、界面却因为填值没生效而停在登录页）。
    const login = await cdp.eval(`
      const r = await fetch(${JSON.stringify(API)} + '/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: ${JSON.stringify(plainUser)}, password: 'UiPlain#12345' }),
      });
      const j = await r.json().catch(() => ({}));
      if (j.token) localStorage.setItem('kg-session-token', j.token);
      return { status: r.status, hasToken: !!j.token };
    `);
    await cdp.send('Page.navigate', { url: URL_APP });
    await sleep(4000);

    let plainState = await cdp.eval(`
      return {
        token: !!localStorage.getItem('kg-session-token'),
        text: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 120),
      };
    `);
    if (!plainState?.token) {
      plainState = plainState || {};
      plainState.diag = `用接口登录返回 ${login?.status}（token=${login?.hasToken}），但页面仍未带上会话`;
    }

    await clickTab(cdp, '后台管理');
    await sleep(3000);
    const adminPage = await cdp.eval(`
      return JSON.stringify({
        text: document.body.innerText.replace(/\\s+/g, ' ').slice(0, 260),
        stillLoggedIn: !!localStorage.getItem('kg-session-token'),
      });
    `);
    const adminState = typeof adminPage === 'string' ? JSON.parse(adminPage) : adminPage;

    check('普通账号能登录并进入业务界面', plainState?.token === true,
      plainState?.diag || (plainState?.text || '').slice(0, 80));
    // 提示必须指向真正的原因（权限），而不是让人去重新登录
    check('普通账号进后台看到的是「权限不足」而不是「请重新登录」',
      /管理员|权限/.test(adminState?.text || '') && !/请在登录页登录管理员账号/.test(adminState?.text || ''),
      (adminState?.text || '').slice(0, 160));
    // 401 会触发前端的「会话失效」流程把人踢回登录页；403 不会
    check('普通账号会话没有被误清（未被踢回登录页）', adminState?.stillLoggedIn === true,
      adminState?.stillLoggedIn ? '' : '会话已被清掉 —— 403 被当成 401 处理了');
    await shot('07-plain-user-admin');
  } else {
    check('注册普通账号（用于验权限提示）', false, `注册返回 ${regState?.status}`);
  }

  // ---------------------------------------------------------------- 7. 全局错误收口
  check('全程无未捕获异常', consoleErrors.length === 0,
    consoleErrors.length ? consoleErrors.slice(0, 3).join(' | ') : '0 条');

  await shot('06-final');
  ws.close();
  child.kill();

  console.log('='.repeat(74));
  console.log(`  共 ${results.length} 项，通过 ${results.length - failed}，失败 ${failed}`
    + (known ? `，已知问题 ${known}` : ''));
  console.log(`  截图目录：${SHOT_DIR}`);
  console.log('='.repeat(74));
  process.exit(failed === 0 ? 0 : 1);
})().catch((e) => {
  console.log('  脚本异常：' + e.message);
  process.exit(2);
});
