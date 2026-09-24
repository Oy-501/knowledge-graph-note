/**
 * graphStore.js 图谱核心状态管理（混合架构版）
 */
import { defineStore } from 'pinia'
import { useConfigStore } from './configStore'
import { useGroupStore } from './groupStore'
import { knowledgeAPI, graphAPI } from '@/api/index'
import { validateGraph, ensureNoOrphans, detectOrphans } from '@/utils/graphValidator'
import { TaskQueue, IntegrityGuard, debounce, logError } from '@/utils/resilience'
import { getNodeValidationStatus, getCredibility } from '@/utils/noteValidator'

export function canConnect(a, b) {
  if (!a || !b || a.id === b.id) return { canConnect: false, contextType: 'invalid', reason: '无效节点对' }
  if (a.fileId && b.fileId && a.fileId === b.fileId) return { canConnect: true, contextType: 'same_file', reason: '同一文件内' }
  if (a.groupId && b.groupId && a.groupId === b.groupId && a.groupId !== 'default') return { canConnect: true, contextType: 'same_group', reason: '同分组' }
  const aTime = a.uploadTime || a._uploadTime || 0
  const bTime = b.uploadTime || b._uploadTime || 0
  const sevenDays = 7 * 24 * 60 * 60 * 1000
  if (aTime > 0 && bTime > 0 && Math.abs(aTime - bTime) < sevenDays) return { canConnect: true, contextType: 'same_period', reason: '同时期内（≤7天）', thresholdBoost: 0.45 }
  return { canConnect: false, contextType: 'cross_window', reason: '跨窗口，禁止自动关联' }
}

export function getNodeHeat(node, allNodes, allLinks) {
  let connectionCount = 0
  for (const l of allLinks) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (s === node.id || t === node.id) connectionCount++
  }
  const fileSet = new Set()
  for (const n of allNodes) if (n.fileId) fileSet.add(n.fileId)
  if (connectionCount > 10) return { level: 'core', label: '核心热点', connectionCount, fileCount: fileSet.size }
  if (connectionCount >= 3) return { level: 'regular', label: '常规知识', connectionCount, fileCount: fileSet.size }
  if (connectionCount >= 1) return { level: 'edge', label: '边缘知识', connectionCount, fileCount: fileSet.size }
  return { level: 'once', label: '一次提及', connectionCount: 0, fileCount: 1 }
}

export const useGraphStore = defineStore('graph', {
  state: () => ({
    nodes: [], links: [], busy: '', busyProgress: 0, version: 0, restartTick: 0,
    orphanCount: 0, lastError: '', validationReport: null, autoAcceptLow: false,
    validationPendingCount: 0, associationMode: 'balanced', _adoptionWarnings: [], _backendReady: false,
    graphFilters: {
      colorMode: 'type', sizeMode: 'degree', folders: [], tags: [], relationTypes: [],
      nodeTypes: [], minScore: 0
    }
  }),
  getters: {
    nodeCount(s) { return s.nodes.length },
    linkCount(s) { return s.links.length },
    isBusy(s) { return !!s.busy },
    weakLinks(s) { return (s.links || []).filter(l => l.evidence_level === 'weak' && !l.semantic_bridge) },
    strongLinkCount(s) { return (s.links || []).filter(l => l.evidence_level === 'strong').length },
    weakLinkCount(s) { return (s.links || []).filter(l => l.evidence_level === 'weak').length },
    linkStats(s) {
      return { total: s.links.length, strong: s.links.filter(l => l.evidence_level === 'strong').length, medium: s.links.filter(l => l.evidence_level === 'medium').length, weak: s.links.filter(l => l.evidence_level === 'weak').length, noEvidence: s.links.filter(l => l.evidence_level === 'none').length }
    },
    discardedNodes(s) { return (s.nodes || []).filter(n => n.validate?.status === 'discarded') },
    validationStats(s) {
      const stats = { total: s.nodes.length, passed: 0, warning: 0, error: 0, pending: 0, discarded: 0 }
      for (const n of s.nodes) { const vs = getNodeValidationStatus(n); stats[vs.status] = (stats[vs.status] || 0) + 1 }
      stats.accuracy = stats.total > 0 ? Math.round((stats.passed / (stats.total - stats.discarded || 1)) * 100) : 0
      return stats
    },
    validatedNodes(s) { return (s.nodes || []).filter(n => { const vs = getNodeValidationStatus(n); return vs.status !== 'discarded' && vs.status !== 'error' }) },
    unverifiedNodes(s) { return (s.nodes || []).filter(n => { const vs = getNodeValidationStatus(n); return vs.status === 'error' || vs.status === 'pending' }) },
    adoptionWarnings(s) { return s._adoptionWarnings || [] },
    visibleNodes(s) {
      const groupStore = useGroupStore()
      if (groupStore.currentGroupId === 'all') return s.nodes.filter(n => n.validate?.status !== 'discarded')
      return s.nodes.filter(n => n.groupId === groupStore.currentGroupId && n.validate?.status !== 'discarded')
    },
    isolatedPairs(s) {
      const pairs = []; const seen = new Set()
      for (const n of s.nodes) {
        if (!n.isolateBlackList?.length) continue
        for (const targetId of n.isolateBlackList) {
          const key = n.id < targetId ? n.id + '|' + targetId : targetId + '|' + n.id
          if (seen.has(key)) continue
          const target = s.nodes.find(x => x.id === targetId)
          if (target?.isolateBlackList?.includes(n.id)) { seen.add(key); pairs.push({ nodeA: n, nodeB: target, key }) }
        }
      }
      return pairs
    },
    getNodesByFile: (s) => fileId => (s.nodes || []).filter(n => n.fileId === fileId && n.status !== 'discarded'),
    searchNodes: (s) => query => {
      const q = query.toLowerCase()
      return (s.nodes || []).filter(n => n.status !== 'discarded' && (n.title.toLowerCase().includes(q) || (n.description || '').toLowerCase().includes(q) || (n.keywords || []).some(k => k.toLowerCase().includes(q)) || (n.entities || []).some(e => e.toLowerCase().includes(q))))
    },
    folderOptions(s) {
      const map = new Map()
      for (const n of s.nodes) { if (!n.fileId || map.has(n.fileId)) continue; map.set(n.fileId, { value: n.fileId, label: n.fileId.length > 10 ? n.fileId.slice(0, 10) + '…' : n.fileId }) }
      return Array.from(map.values())
    },
    tagOptions(s) {
      const set = new Set()
      for (const n of s.nodes) { for (const k of (n.keywords || [])) set.add(k); for (const e of (n.entities || [])) set.add(e); if (set.size >= 60) break }
      return Array.from(set).slice(0, 60).map(t => ({ value: t, label: t }))
    },
    relationTypeOptions(s) {
      const map = new Map()
      for (const l of s.links) { if (!l.relation_type || map.has(l.relation_type)) continue; map.set(l.relation_type, { value: l.relation_type, label: l.relation_label || l.relation_type }) }
      return Array.from(map.values())
    },
    nodeTypeOptions() { return [{ value: 'user', label: '用户节点' }, { value: 'kb', label: '知识库节点' }, { value: 'note', label: '笔记节点' }] }
  },
  actions: {
    setGraphFilters(partial) { Object.assign(this.graphFilters, partial); this.version++; this.restartTick++ },
    setBusy(msg) { this.busy = msg || ''; if (!msg) this.busyProgress = 0 },
    setProgress(p) { this.busyProgress = p },
    async loadFromBackend() {
      this.setBusy('加载图谱数据'); this.setProgress(10)
      try {
        const data = await graphAPI.build({ groupId: 'all' })
        this._applyGraphData(data); this._backendReady = true; this.setBusy(''); this.setProgress(100)
        return { ok: true, nodes: data.nodes?.length || 0, links: data.links?.length || 0 }
      } catch (e) {
        console.warn('[graphStore] loadFromBackend failed:', e.message); this._backendReady = false; this.setBusy('')
        return { ok: false, msg: e.message }
      }
    },
    _applyGraphData(data) {
      if (data.nodes?.length) {
        this.nodes = data.nodes.map(n => ({ id: n.id, fileId: n.fileId, title: n.title || n.entity || '', description: n.description || '', keywords: n.keywords || [], entities: n.entities || [], rawText: n.rawText || '', type: n.type || 'knowledge', vector: null, groupId: n.groupId || 'default', groupName: n.groupName || '默认分组', visible: n.visible !== undefined ? n.visible : true, isolateBlackList: n.isolateBlackList || [], level: n.level || 3, levelLabel: n.levelLabel || 'L3: 具体技术', _domain: n.domain || '', uploadTime: n.uploadTime || 0, validate: n.validate || { status: 'pending', issues: [] }, validated: n.validated || false, validateStatus: n.validateStatus || 'pending', confidence: n.confidence || 0 }))
      } else { this.nodes = [] }
      if (data.links?.length) {
        this.links = data.links.map(l => ({ id: l.id, source: l.source, target: l.target, score: l.score || 0, relation_type: l.relation_type || 'related', relation_label: l.relation_label || '关联', relation_color: l.relation_color || '#8a93b0', relation_icon: l.relation_icon || '~', relation_evidence: l.evidence || '', relation_confidence: l.relation_confidence || 0.5, relation_method: l.relation_method || 'auto', evidence: l.evidence || '', source_text: l.source_text || '', source_file: l.source_file || '', evidence_level: l.evidence_level || 'medium', evidence_label: l.evidence_label || '中证据', evidence_color: l.evidence_color || '#d6def0', evidence_icon: l.evidence_icon || '🟡', source_type: l.auto_generated ? 'auto' : 'manual', timeBridge: l.timeBridge || false, semantic_bridge: l.semantic_bridge || false, auto_generated: l.auto_generated !== false, user_confirmed: l.user_confirmed || false, final_weight: l.final_weight || 1, is_render: l.is_render !== false, breakdown: { sim_text: 0, sim_vector: 0, sim_corpus: 0, sim_topology: 0, weights: { alpha: 0.15, beta: 0.25, gamma: 0.50, delta: 0.10 } } }))
      } else { this.links = [] }
      this.refreshOrphanCount(); this.version++; this.restartTick++
    },
    async ingestNewNodes(fileId, kps) {
      const cfg = useConfigStore()
      this.setBusy('提取知识点（' + kps.length + ' 条）'); this.setProgress(10)
      if (!this._backendReady) { try { const r = await this.loadFromBackend(); if (r.ok) this._backendReady = true } catch (e) {} }
      const now = Date.now()
      const newNodes = kps.map(k => ({ id: k.id, fileId, title: k.title, description: k.description, keywords: k.keywords || [], entities: k.entities || [], rawText: k.rawText || '', type: k.type || 'knowledge', vector: null, groupId: 'default', groupName: '默认分组', visible: true, isolateBlackList: [], level: k.level || 3, levelLabel: k.levelLabel || 'L3: 具体技术', _domain: k._domain || '', uploadTime: now, validate: { status: 'pending', issues: [] }, validated: false, validateStatus: 'pending', confidence: 0 }))
      this.nodes.push(...newNodes); this.setProgress(25)
      let actualNewLinks = 0
      if (this._backendReady) {
        this.setBusy('后端推理关联关系'); this.setProgress(30)
        try {
          const nodePayloads = newNodes.map(n => ({ id: n.id, title: n.title, entity: n.title, description: n.description, keywords: n.keywords, entities: n.entities, level: n.level, domain: n._domain || '', file_id: n.fileId, group_id: n.groupId }))
          const result = await knowledgeAPI.inferLinks(nodePayloads, { alpha: cfg.w_alpha, beta: cfg.w_beta, gamma: cfg.w_gamma, delta: cfg.w_delta }, cfg.threshold)
          if (result.links?.length) {
            const newLinks = result.links.map(l => ({ id: l.id || 'l_' + l.source + '_' + l.target, source: l.source, target: l.target, score: l.score || 0, relation_type: l.relation_type || 'related', relation_label: l.relation_label || '关联', relation_color: l.relation_color || '#8a93b0', relation_icon: l.relation_icon || '~', relation_evidence: l.evidence || '', relation_confidence: l.relation_confidence || 0.5, relation_method: l.relation_method || 'auto', evidence: l.evidence || '', source_text: l.source_text || '', source_file: l.source_file || '', evidence_level: l.evidence_level || 'medium', evidence_label: l.evidence_label || '中证据', evidence_color: l.evidence_color || '#d6def0', evidence_icon: l.evidence_icon || '🟡', source_type: 'auto', timeBridge: l.time_bridge || false, semantic_bridge: false, auto_generated: true, user_confirmed: false, breakdown: l.breakdown || { sim_text: 0, sim_vector: 0, sim_corpus: 0, sim_topology: 0, weights: { alpha: cfg.w_alpha, beta: cfg.w_beta, gamma: cfg.w_gamma, delta: cfg.w_delta } } }))
            const existingKeys = new Set(this.links.map(l => { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; return s < t ? s + '|' + t : t + '|' + s }))
            for (const nl of newLinks) {
              const k = nl.source < nl.target ? nl.source + '|' + nl.target : nl.target + '|' + nl.source
              if (!existingKeys.has(k)) { existingKeys.add(k); this.links.push(nl); actualNewLinks++ }
            }
          }
        } catch (e) { console.warn('[graphStore] inferLinks API failed:', e.message); this._backendReady = false }
      }
      this.setProgress(80)
      this.setBusy('孤儿节点收养校验')
      const v = validateGraph(this.nodes, this.links)
      this.links = v.links
      this.orphanCount = Math.max(0, v.stats.orphanCount - v.stats.adopted)
      this._adoptionWarnings = v.warnings || []
      this.version++; this.restartTick++; this.setProgress(95)
      this.setBusy(''); this.setProgress(100)
      return { newNodes: newNodes.length, newLinks: actualNewLinks, orphanCount: this.orphanCount }
    },
    async rebuildAll() {
      this.setBusy('全局重排：从后端获取图谱数据'); this.setProgress(10)
      try {
        const data = await graphAPI.build({ groupId: 'all' })
        this._applyGraphData(data); this.setBusy(''); this.setProgress(100)
        return { ok: this.links.length, orphanCount: this.orphanCount }
      } catch (e) { console.warn('[graphStore] rebuildAll failed:', e.message); this.setBusy(''); return { ok: 0, msg: e.message } }
    },
    recomputeScoreOnly() {
      const cfg = useConfigStore()
      for (const l of this.links) {
        if (l.semantic_bridge) { l.score = 0.3; continue }
        const b = l.breakdown
        if (!b) continue
        const alpha = cfg.w_alpha; const beta = cfg.w_beta; const gamma = cfg.corpusEnabled ? cfg.w_gamma : 0; const delta = cfg.w_delta
        l.score = Math.round((alpha * b.sim_text + beta * b.sim_vector + gamma * b.sim_corpus + delta * b.sim_topology) * 1000) / 1000
      }
      this.version++
    },
    async removeNodesByFile(fileId) {
      try {
        const removed = this.nodes.filter(n => n.fileId === fileId)
        const removedIds = new Set(removed.map(n => n.id))
        this.nodes = this.nodes.filter(n => n.fileId !== fileId)
        for (const id of removedIds) this.cleanIsolateRefs(id)
        const nodeIds = new Set(this.nodes.map(n => n.id))
        this.links = this.links.filter(l => { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; return nodeIds.has(s) && nodeIds.has(t) })
        const v = validateGraph(this.nodes, this.links)
        this.links = v.links
        this.orphanCount = Math.max(0, v.stats.orphanCount - v.stats.adopted)
        this.version++; this._repairIntegrity()
        return removed.map(n => n.id)
      } catch (e) { logError('removeNodesByFile', fileId, e); throw e }
    },
    takeSnapshot() { return { nodes: JSON.parse(JSON.stringify(this.nodes)), links: JSON.parse(JSON.stringify(this.links)), version: this.version } },
    restoreSnapshot(snapshot) { if (!snapshot) return; this.nodes = snapshot.nodes || []; this.links = snapshot.links || []; this.version = (snapshot.version || 0) + 1; this.restartTick++ },
    _repairIntegrity() {
      try {
        const guard = new IntegrityGuard(this)
        const issues = guard.checkAndRepair()
        if (issues.length > 0) { const types = issues.map(i => i.type); logError('_repairIntegrity', 'auto-repair', new Error(`修复了 ${issues.length} 个问题: ${types.join(', ')}`)); this.version++ }
      } catch (e) { logError('_repairIntegrity', 'check-failed', e) }
    },
    afterDeleteRefresh() { this.version++; this.restartTick++ },
    setAssociationMode(mode) {
      this.associationMode = mode; const cfg = useConfigStore()
      if (mode === 'precise') cfg.threshold = 0.25
      else if (mode === 'balanced') cfg.threshold = 0.15
      else if (mode === 'loose') cfg.threshold = 0.08
      this.version++
    },
    removeWeakLinks() {
      const before = this.links.length
      this.links = this.links.filter(l => { if (l.semantic_bridge) return true; if (l.source_type === 'manual') return true; return l.evidence_level !== 'weak' })
      const removed = before - this.links.length
      this.version++; this.restartTick++
      return { ok: true, removed }
    },
    reset() { this.nodes = []; this.links = []; this.busy = ''; this.busyProgress = 0; this.orphanCount = 0; this.version++; this.restartTick++ },
    refreshOrphanCount() { const { orphans } = detectOrphans(this.nodes, this.links.filter(l => !l.semantic_bridge)); this.orphanCount = orphans.size; return orphans.size },
    handleAcceptFix(nodeId, issue) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return { ok: false, msg: '节点不存在' }
      if (issue.aiFix) { node.title = issue.aiFix.title || node.title; node.description = issue.aiFix.description || node.description }
      if (node.validate?.issues) node.validate.issues = node.validate.issues.filter(i => !(i.type === issue.type && i.reason === issue.reason))
      if (!node.validate?.issues?.length) node.validate.status = 'confirmed'
      this.version++; this.restartTick++; return { ok: true, action: 'fixed' }
    },
    handleDiscardNode(nodeId) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return { ok: false, msg: '节点不存在' }
      if (!node.validate) node.validate = {}
      node.validate.status = 'discarded'
      this.cleanIsolateRefs(nodeId)
      this.links = this.links.filter(l => { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; return s !== nodeId && t !== nodeId })
      this.version++; this.restartTick++; return { ok: true }
    },
    handleRestoreNode(nodeId) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return { ok: false, msg: '节点不存在' }
      if (node.validate) node.validate.status = 'confirmed'
      this.version++; this.restartTick++; return { ok: true }
    },
    handleManualEdit(nodeId, newValue) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return { ok: false, msg: '节点不存在' }
      if (newValue.title) node.title = newValue.title
      if (newValue.description) node.description = newValue.description
      if (node.validate) node.validate.status = 'confirmed'
      this.version++; return { ok: true }
    },
    handleSkipIssue(nodeId, issue) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return { ok: false }
      if (node.validate?.issues) node.validate.issues = node.validate.issues.filter(i => !(i.type === issue.type && i.reason === issue.reason))
      if (!node.validate?.issues?.length) node.validate.status = 'confirmed'
      return { ok: true }
    },
    handleAcceptAll() {
      let accepted = 0
      for (const node of this.nodes) { if (!node.validate?.issues?.length) continue; node.validate.issues = []; node.validate.status = 'confirmed'; accepted++ }
      this.version++; this.restartTick++; return { ok: true, accepted }
    },
    handleIgnoreAll() { for (const node of this.nodes) { if (!node.validate?.issues?.length) continue; node.validate.issues = []; node.validate.status = 'confirmed' } return { ok: true } },
    toggleAutoAcceptLow(val) { this.autoAcceptLow = val ?? !this.autoAcceptLow },
    addIsolate(nodeIdA, nodeIdB) {
      const nodeA = this.nodes.find(n => n.id === nodeIdA); const nodeB = this.nodes.find(n => n.id === nodeIdB)
      if (!nodeA || !nodeB || nodeA.id === nodeB.id) return false
      if (!nodeA.isolateBlackList) nodeA.isolateBlackList = []; if (!nodeB.isolateBlackList) nodeB.isolateBlackList = []
      if (!nodeA.isolateBlackList.includes(nodeIdB)) nodeA.isolateBlackList.push(nodeIdB)
      if (!nodeB.isolateBlackList.includes(nodeIdA)) nodeB.isolateBlackList.push(nodeIdA)
      const removed = []
      this.links = this.links.filter(l => { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; if ((s === nodeIdA && t === nodeIdB) || (s === nodeIdB && t === nodeIdA)) { if (l.source_type === 'manual') return true; removed.push(l.id); return false } return true })
      this.version++; this.restartTick++; return { ok: true, removed }
    },
    removeIsolate(nodeIdA, nodeIdB) {
      const nodeA = this.nodes.find(n => n.id === nodeIdA); const nodeB = this.nodes.find(n => n.id === nodeIdB)
      if (!nodeA || !nodeB) return false
      if (nodeA.isolateBlackList) nodeA.isolateBlackList = nodeA.isolateBlackList.filter(id => id !== nodeIdB)
      if (nodeB.isolateBlackList) nodeB.isolateBlackList = nodeB.isolateBlackList.filter(id => id !== nodeIdA)
      this.version++; this.restartTick++; return { ok: true }
    },
    cleanIsolateRefs(deletedNodeId) { for (const n of this.nodes) { if (n.isolateBlackList?.includes(deletedNodeId)) n.isolateBlackList = n.isolateBlackList.filter(id => id !== deletedNodeId) } },
    setNodeValidationReport(nodeId, report) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return false
      if (!node.validationReport) node.validationReport = {}
      Object.assign(node.validationReport, report)
      if (!node.accuracyScore) node.accuracyScore = report.accuracyScore || 0
      if (!node.verified) node.verified = report.verified || false
      this.version++; return true
    },
    verifyNode(nodeId) {
      const node = this.nodes.find(n => n.id === nodeId); if (!node) return false
      node.verified = true
      if (!node.validationReport) node.validationReport = { totalAssertions: 1, passedAssertions: 1, errors: [], warnings: [], checkedAt: Date.now() }
      node.accuracyScore = 100; this.version++; return true
    },
    getNodeValidation(node) { return getNodeValidationStatus(node) },
    getNodeCredibility(node) { return getCredibility(node) }
  },
  persist: false
})
