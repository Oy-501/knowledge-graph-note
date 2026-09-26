/**
 * errorReporter.js —— 前端错误统一上报
 *
 * 解决的问题：此前前端报错只落在 console 与内存数组里
 *   - 刷新页面即丢失
 *   - 后端与「后台管理」完全看不到
 *   - 用户截图只有一个红色报错，没有复现路径
 *
 * 现在把现场（路由 / 组件 / 调用栈 / 浏览器）报送后端，
 * 写入操作审计，后台即可看到故障清单。三条自我约束：
 *   1. 去重  —— 同一错误 30 秒内只报一次，避免循环报错刷爆
 *   2. 限流  —— 每分钟最多 N 条，服务端异常时也不会打满带宽
 *   3. 静默  —— 上报失败绝不抛错、绝不弹窗（否则错误处理本身成了新错误源）
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const DEDUPE_WINDOW_MS = 30_000
const MAX_PER_MINUTE = 10

/** 签名 -> 上次上报时间 */
const _seen = new Map()
/** 最近上报时间戳 */
let _sentTimes = []
let _installed = false
/** 供上层（如个人页/后台）展示的本地留档 */
const _localLog = []

function _now() {
  return Date.now()
}

function _signature(payload) {
  return `${payload.source}|${payload.component}|${(payload.message || '').slice(0, 120)}`
}

function _allowedByRateLimit() {
  const cutoff = _now() - 60_000
  _sentTimes = _sentTimes.filter(t => t > cutoff)
  return _sentTimes.length < MAX_PER_MINUTE
}

function _currentRoute() {
  try {
    return window.location.hash || window.location.pathname || ''
  } catch {
    return ''
  }
}

/**
 * 上报一条前端错误。永不抛出、永不阻塞。
 * @returns {boolean} 是否真的发出（被去重/限流拦截时返回 false）
 */
export function reportClientError({
  message = '',
  stack = '',
  source = 'vue',
  component = '',
  info = '',
  extra = {}
} = {}) {
  const payload = {
    message: String(message || '').slice(0, 2000),
    stack: String(stack || '').slice(0, 4000),
    source,
    component: String(component || '').slice(0, 200),
    info: String(info || '').slice(0, 500),
    route: _currentRoute(),
    user_agent: (typeof navigator !== 'undefined' ? navigator.userAgent : '').slice(0, 400),
    occurred_at: new Date().toISOString()
  }
  if (extra && Object.keys(extra).length) {
    payload.info = (payload.info + ' ' + JSON.stringify(extra)).slice(0, 500)
  }

  // 本地留一份（供开发期查看；不上报到远端也能看到最近发生了什么）
  _localLog.push({ ...payload, time: _now() })
  if (_localLog.length > 50) _localLog.shift()

  const sig = _signature(payload)
  const last = _seen.get(sig)
  if (last && _now() - last < DEDUPE_WINDOW_MS) return false
  if (!_allowedByRateLimit()) return false

  _seen.set(sig, _now())
  _sentTimes.push(_now())

  try {
    // keepalive 让页面正在卸载（白屏/刷新）时请求也尽量发出去
    fetch(`${API_BASE}/system/client-error`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(() => {})
  } catch {
    /* 静默：上报失败不是业务错误 */
  }
  return true
}

/** 供 UI 展示的本地错误留档（最近 50 条） */
export function getLocalErrorLog() {
  return [..._localLog]
}

/**
 * 安装全局兜底：
 *   - window.onerror / unhandledrejection：非组件内的错误
 *   - Vue 的 errorHandler 由 main.js 注册（能拿到组件名与生命周期阶段）
 */
export function installGlobalErrorHooks() {
  if (_installed || typeof window === 'undefined') return
  _installed = true

  window.addEventListener('error', event => {
    // 资源加载失败（img/script）也会走这里，单独标注便于区分
    const target = event.target
    const isResource = target && target !== window && (target.src || target.href)
    reportClientError({
      message: event.message || (isResource ? `资源加载失败: ${target.src || target.href}` : '未知错误'),
      stack: event.error?.stack || '',
      source: isResource ? 'resource' : 'window',
      component: '',
      info: event.filename ? `${event.filename}:${event.lineno}:${event.colno}` : ''
    })
  }, true)

  window.addEventListener('unhandledrejection', event => {
    const reason = event.reason
    reportClientError({
      message: reason?.message || String(reason || '未处理的 Promise 拒绝'),
      stack: reason?.stack || '',
      source: 'promise',
      component: '',
      info: ''
    })
  })
}

export default { reportClientError, getLocalErrorLog, installGlobalErrorHooks }
