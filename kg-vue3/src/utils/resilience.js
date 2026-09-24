/**
 * resilience.js 韧性架构十大支柱实现
 */
const PRIORITY_MAP = { high: 0, normal: 1, low: 2 }

export class TaskQueue {
  constructor(maxConcurrent = 3) {
    this.queue = []; this.processing = false; this.maxConcurrent = maxConcurrent; this._onProgress = null; this._totalTasks = 0; this._completedTasks = 0
  }
  get pendingCount() { return this.queue.length }
  get progress() { return this._totalTasks > 0 ? Math.round((this._completedTasks / this._totalTasks) * 100) : 0 }
  onProgress(cb) { this._onProgress = cb }
  async add(task, priority = 'normal') {
    return new Promise((resolve, reject) => { this.queue.push({ task, priority, resolve, reject }); this._totalTasks++; this.process() })
  }
  async process() {
    if (this.processing || this.queue.length === 0) return
    this.processing = true
    this.queue.sort((a, b) => (PRIORITY_MAP[a.priority] || 1) - (PRIORITY_MAP[b.priority] || 1))
    const batch = this.queue.splice(0, this.maxConcurrent)
    const results = await Promise.allSettled(batch.map(item => this._execute(item)))
    this._completedTasks += batch.length
    if (this._onProgress) this._onProgress(this.progress)
    this.processing = false
    if (this.queue.length > 0) { await new Promise(r => setTimeout(r, 16)); this.process() }
    else { this._totalTasks = 0; this._completedTasks = 0 }
  }
  async _execute(item) {
    try { const result = await item.task(); item.resolve(result); return result }
    catch (e) { item.reject(e); throw e }
  }
}

export async function progressiveProcess(items, renderFn, batchSize = 20, onProgress = null) {
  const totalBatches = Math.ceil(items.length / batchSize)
  for (let i = 0; i < totalBatches; i++) {
    const batch = items.slice(i * batchSize, (i + 1) * batchSize)
    await renderFn(batch, i)
    if (onProgress) onProgress(Math.round(((i + 1) / totalBatches) * 100))
    await new Promise(resolve => setTimeout(resolve, 16))
  }
}

export class VersionedStore {
  constructor(maxHistory = 50, snapshotInterval = 5) {
    this.history = []; this.maxHistory = maxHistory; this.snapshotInterval = snapshotInterval; this.operationCount = 0; this._takeSnapshot = null; this._restoreSnapshot = null; this._onSave = null
  }
  configure({ takeSnapshot, restoreSnapshot, onSave }) { this._takeSnapshot = takeSnapshot; this._restoreSnapshot = restoreSnapshot; this._onSave = onSave }
  mutate(operation) {
    if (this._takeSnapshot) { const snapshot = this._takeSnapshot(); this.history.push(snapshot); if (this.history.length > this.maxHistory) this.history.shift() }
    const result = operation()
    this.operationCount++
    if (this.operationCount % this.snapshotInterval === 0 && this._onSave) this._onSave()
    return result
  }
  undo() { const previous = this.history.pop(); if (previous && this._restoreSnapshot) { this._restoreSnapshot(previous); return true } return false }
  get canUndo() { return this.history.length > 0 }
  get historyCount() { return this.history.length }
}

export function debounce(fn, delay = 300) {
  let timer = null; let pendingThis = null; let pendingArgs = null
  const debounced = function (...args) {
    pendingThis = this; pendingArgs = args; clearTimeout(timer)
    timer = setTimeout(() => { timer = null; fn.apply(this, args) }, delay)
  }
  debounced.flush = () => { if (timer === null) return; clearTimeout(timer); timer = null; fn.apply(pendingThis, pendingArgs); pendingThis = null; pendingArgs = null }
  debounced.cancel = () => { if (timer !== null) clearTimeout(timer); timer = null; pendingThis = null; pendingArgs = null }
  return debounced
}

export function throttle(fn, limit = 1000) {
  let inThrottle = false; let lastArgs = null
  return function (...args) {
    if (!inThrottle) { fn.apply(this, args); inThrottle = true; lastArgs = null; setTimeout(() => { inThrottle = false; if (lastArgs) { fn.apply(this, lastArgs); lastArgs = null } }, limit) }
    else lastArgs = args
  }
}

export function idempotent(fn) {
  const cache = new Map()
  return function (key, ...args) {
    const cacheKey = typeof key === 'string' ? key + JSON.stringify(args) : JSON.stringify({ key, args })
    if (cache.has(cacheKey)) return cache.get(cacheKey)
    const result = fn.apply(this, args)
    cache.set(cacheKey, result)
    return result
  }
}

export class GracefulDegradation {
  constructor() { this.level = 'full'; this._onLevelChange = null }
  onLevelChange(cb) { this._onLevelChange = cb }
  async executeWithFallback(operations) {
    for (let i = 0; i < operations.length; i++) {
      try { return await operations[i].fn() }
      catch (e) { if (i < operations.length - 1) { this.level = operations[i + 1].level || 'reduced'; if (this._onLevelChange) this._onLevelChange(this.level, e.message) } }
    }
    return null
  }
  getStatusMessage() {
    const messages = { 'full': '系统运行正常', 'reduced': '系统进入降级模式，部分功能不可用', 'minimal': '系统进入基础模式，仅支持核心功能' }
    return messages[this.level] || ''
  }
}

export class Transaction {
  constructor(store) { this.store = store; this.operations = []; this.snapshot = null }
  add(operation) { this.operations.push(operation); return this }
  async execute() {
    this.snapshot = this.store.takeSnapshot ? this.store.takeSnapshot() : null
    try {
      const results = []
      for (const op of this.operations) results.push(await op())
      if (this.store.save) this.store.save()
      return results
    } catch (e) {
      if (this.snapshot && this.store.restoreSnapshot) this.store.restoreSnapshot(this.snapshot)
      throw new Error(`事务执行失败，已回滚: ${e.message}`)
    }
  }
}

export class IntegrityGuard {
  constructor(store) { this.store = store }
  checkAndRepair() {
    const issues = []; const nodes = this.store.nodes || []; const links = this.store.links || []; const nodeIds = new Set(nodes.map(n => n.id))
    const validLinks = []
    for (const link of links) {
      const s = typeof link.source === 'object' ? link.source.id : link.source
      const t = typeof link.target === 'object' ? link.target.id : link.target
      if (!nodeIds.has(s)) { issues.push({ type: 'dangling_link_source', linkId: link.id, missing: s }); continue }
      if (!nodeIds.has(t)) { issues.push({ type: 'dangling_link_target', linkId: link.id, missing: t }); continue }
      validLinks.push(link)
    }
    const removedLinks = links.length - validLinks.length
    if (removedLinks > 0) { this.store.links = validLinks; issues.push({ type: 'repaired_dangling_links', count: removedLinks }) }
    for (const node of nodes) {
      if (!node.isolateBlackList?.length) continue
      const valid = node.isolateBlackList.filter(id => nodeIds.has(id))
      if (valid.length !== node.isolateBlackList.length) { const removed = node.isolateBlackList.length - valid.length; node.isolateBlackList = valid; issues.push({ type: 'repaired_blacklist', nodeId: node.id, removed }) }
    }
    if (this.store.groups) {
      const counts = {}
      for (const n of nodes) counts[n.groupId] = (counts[n.groupId] || 0) + 1
      for (const g of this.store.groups) { const expected = counts[g.id] || 0; if (g.count !== expected) { g.count = expected; issues.push({ type: 'repaired_group_count', groupId: g.id, expected, was: g.count }) } }
    }
    return issues
  }
}

export class PreloadManager {
  constructor() { this.cache = new Map(); this.maxCache = 10 }
  onHover(key, loaderFn) {
    if (!this.cache.has(key)) {
      setTimeout(async () => {
        try { const data = await loaderFn(); this.cache.set(key, data); if (this.cache.size > this.maxCache) { const first = this.cache.keys().next().value; this.cache.delete(first) } } catch (e) { /* silent */ }
      }, 100)
    }
  }
  get(key) { return this.cache.get(key) }
  clear() { this.cache.clear() }
}

let _errorLog = []

export function logError(source, context, error) {
  const entry = { time: Date.now(), source, context: String(context || ''), message: error?.message || String(error), stack: error?.stack || '' }
  _errorLog.push(entry)
  if (_errorLog.length > 100) _errorLog.shift()
  console.error(`[Resilience] ${source}:`, error)
  return entry
}

export function getErrorLog() { return [..._errorLog] }
export function clearErrorLog() { _errorLog = [] }

export class HealthMonitor {
  constructor() {
    this.metrics = { nodeCount: 0, linkCount: 0, pendingTasks: 0, memoryUsageMB: 0, lastResponseTime: 0, errorCount: 0, degradedLevel: 'full' }
    this.warnings = []; this._intervalId = null; this._onUpdate = null
  }
  onUpdate(cb) { this._onUpdate = cb }
  startMonitoring(intervalMs = 5000) {
    this.stopMonitoring()
    this._intervalId = setInterval(() => { this.collectMetrics(); this.checkThresholds(); if (this._onUpdate) this._onUpdate(this.metrics, this.warnings) }, intervalMs)
  }
  stopMonitoring() { if (this._intervalId) { clearInterval(this._intervalId); this._intervalId = null } }
  collectMetrics() {
    this.metrics.memoryUsageMB = performance.memory?.usedJSHeapSize ? Math.round(performance.memory.usedJSHeapSize / 1024 / 1024) : 0
    this.metrics.errorCount = _errorLog.length
  }
  updateStoreMetrics(nodes, links, pendingTasks) { this.metrics.nodeCount = nodes?.length || 0; this.metrics.linkCount = links?.length || 0; this.metrics.pendingTasks = pendingTasks || 0 }
  checkThresholds() {
    this.warnings = []
    if (this.metrics.nodeCount > 500) this.warnings.push({ level: 'info', msg: '知识点超过500个，建议使用分组功能提升性能' })
    if (this.metrics.nodeCount > 1000) this.warnings.push({ level: 'warn', msg: '知识点超过1000个，图谱渲染可能变慢' })
    if (this.metrics.pendingTasks > 10) this.warnings.push({ level: 'warn', msg: '有大量任务排队中，请耐心等待' })
    if (this.metrics.memoryUsageMB > 500) this.warnings.push({ level: 'warn', msg: `内存占用较高（${this.metrics.memoryUsageMB}MB），建议刷新页面释放缓存` })
    if (this.metrics.errorCount > 20) this.warnings.push({ level: 'error', msg: '错误数量较多，建议重启应用' })
  }
  getStatus() {
    if (this.warnings.some(w => w.level === 'error')) return 'error'
    if (this.warnings.some(w => w.level === 'warn')) return 'warning'
    return 'healthy'
  }
}

export async function resilientDeleteFile(store, fileId) {
  const tx = new Transaction(store); const guard = new IntegrityGuard(store)
  tx.add(async () => {
    const nodeIds = store.nodes.filter(n => n.fileId === fileId).map(n => n.id)
    store.nodes = store.nodes.filter(n => n.fileId !== fileId)
    store.links = store.links.filter(l => {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      return !nodeIds.includes(s) && !nodeIds.includes(t)
    })
    for (const node of store.nodes) { if (node.isolateBlackList?.length) node.isolateBlackList = node.isolateBlackList.filter(id => !nodeIds.includes(id)) }
    return true
  })
  try { await tx.execute(); const issues = guard.checkAndRepair(); return { success: true, issues } }
  catch (e) { logError('deleteFile', fileId, e); return { success: false, issues: [], error: e.message } }
}
