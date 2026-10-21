/**
 * conn_probe.mjs —— 前端到后端的连接探针（只读，不写库）
 *
 * 打开真实浏览器页面，从页面上下文直接 fetch 后端接口，
 * 验证「浏览器 → CORS → 后端」这条链路，而不是只看 curl。
 *
 * 跑法：
 *   node backend/tests/conn_probe.mjs --url http://127.0.0.1:5173 --api http://127.0.0.1:8080/api
 */
import { execFile } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const APP = arg('url', 'http://127.0.0.1:5173');
const API = arg('api', 'http://127.0.0.1:8080/api');
const CHROME = arg('chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
const DEBUG_PORT = 9400 + (process.pid % 300);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        this.pending.get(m.id)(m);
        this.pending.delete(m.id);
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

(async () => {
  const profile = path.join(os.tmpdir(), `conn-probe-${process.pid}`);
  const child = execFile(CHROME, [
    '--headless=new',
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-gpu', '--disable-extensions', '--disable-background-networking',
    '--window-size=1440,900',
    'about:blank',
  ], { stdio: 'ignore' });
  child.on('error', (e) => { console.error('浏览器启动失败:', e.message); process.exit(2); });

  let ready = false;
  for (let i = 0; i < 60; i++) {
    try { await httpGet('/json/version'); ready = true; break; } catch { await sleep(250); }
  }
  if (!ready) { console.error('CDP 未就绪'); child.kill(); process.exit(2); }

  const targets = JSON.parse(await httpGet('/json/list'));
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  const cdp = new Cdp(ws);

  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Log.enable');

  const errors = [];
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params?.exceptionDetails || {};
      errors.push('未捕获异常: ' + (d.exception?.description || d.text || '').split('\n')[0]);
    }
    if (m.method === 'Log.entryAdded' && m.params?.entry?.level === 'error') {
      errors.push('console.error: ' + (m.params.entry.text || '').slice(0, 200));
    }
  });

  await cdp.send('Page.navigate', { url: APP });
  await sleep(3000);

  const probe = await cdp.eval(`
    const out = { page: location.href };
    try {
      const r = await fetch(${JSON.stringify(API + '/auth/status')}, { headers: { Accept: 'application/json' } });
      out.api = { ok: r.ok, status: r.status, body: await r.json() };
    } catch (e) {
      out.api = { ok: false, error: String(e) };
    }
    return out;
  `);

  console.log(JSON.stringify({ app: APP, api: API, probe, consoleErrors: errors }, null, 2));
  child.kill();
  process.exit(probe.api?.ok ? 0 : 1);
})();
