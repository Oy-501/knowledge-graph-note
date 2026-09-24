/**
 * groupStore.js 分组管理模块（增强版 v3）
 */
import { defineStore } from 'pinia'

let _graphStore = null
function _setGraphStoreRef(store) { _graphStore = store }
function _getGraphStore() { return _graphStore }

const GROUP_COLORS = [
  '#6C8EBF', '#82B366', '#D79B00', '#B85450', '#9673A6',
  '#4D90C1', '#7EAE5A', '#E6A817', '#C44B4B', '#8C6BAE',
  '#5B9BD5', '#67AB5A', '#F0A030', '#D9544D', '#9B7EC4',
  '#3B82C4', '#5EA85C', '#E8A020', '#C74545', '#8B69C0'
]

export const useGroupStore = defineStore('group', {
  state: () => ({
    groups: [{ id: 'default', name: '默认分组', count: 0, color: '#8a93b0', collapsed: false, parentId: null, visible: true, description: '', keywords: [] }],
    currentGroupId: 'all', groupSortBy: 'name', groupSortAsc: true,
    groupSearch: '', batchSelectedNodes: [], treeCollapsed: {},
    autoClassifyThreshold: 0.3
  }),
  getters: {
    currentGroup(state) { if (state.currentGroupId === 'all') return { id: 'all', name: '全部', count: 0 }; return state.groups.find(g => g.id === state.currentGroupId) || state.groups[0] },
    totalNodeCount(state) { return state.groups.reduce((sum, g) => sum + (g.count || 0), 0) },
    groupOptions(state) { return state.groups.map(g => ({ value: g.id, label: g.name })) },
    isAllMode(state) { return state.currentGroupId === 'all' },
    filteredGroups(state) {
      let list = [...state.groups]
      if (state.groupSearch) { const kw = state.groupSearch.toLowerCase(); list = list.filter(g => g.name.toLowerCase().includes(kw)) }
      list.sort((a, b) => {
        let cmp = 0
        if (state.groupSortBy === 'name') cmp = a.name.localeCompare(b.name, 'zh')
        else if (state.groupSortBy === 'count') cmp = (a.count || 0) - (b.count || 0)
        else if (state.groupSortBy === 'created') cmp = (a._createdAt || 0) - (b._createdAt || 0)
        return state.groupSortAsc ? cmp : -cmp
      })
      return list
    },
    groupColorMap(state) { const map = {}; for (const g of state.groups) map[g.id] = g.color || '#8a93b0'; return map },
    rootGroups(state) { return state.groups.filter(g => !g.parentId || g.parentId === 'root') },
    childrenOf: (state) => groupId => state.groups.filter(g => g.parentId === groupId),
    descendantsOf: (state) => groupId => {
      const result = []; const stack = state.groups.filter(g => g.parentId === groupId); const visited = new Set()
      while (stack.length) { const g = stack.pop(); if (visited.has(g.id)) continue; visited.add(g.id); result.push(g); stack.push(...state.groups.filter(c => c.parentId === g.id)) }
      return result
    },
    ancestorChain: (state) => groupId => {
      const chain = []; let current = state.groups.find(g => g.id === groupId); const visited = new Set()
      while (current?.parentId) { if (visited.has(current.id)) break; visited.add(current.id); const parent = state.groups.find(g => g.id === current.parentId); if (!parent) break; chain.unshift(parent); current = parent }
      return chain
    },
    groupTree(state) { return buildGroupTree(state.groups, null) },
    visibleGroups(state) { return state.groups.filter(g => g.visible !== false) },
    hiddenGroupIds(state) {
      const ids = new Set()
      for (const g of state.groups) { if (g.visible === false) { ids.add(g.id); state.groups.filter(d => d.parentId === g.id).map(d => d.id).forEach(id => ids.add(id)) } }
      return ids
    },
    visibleNodeIds(state) {
      const graphStore = _getGraphStore()
      if (!graphStore) return new Set()
      const hiddenIds = this.hiddenGroupIds
      const ids = new Set()
      for (const n of graphStore.nodes) { if (n.validate?.status === 'discarded') continue; if (hiddenIds.has(n.groupId)) continue; ids.add(n.id) }
      return ids
    }
  },
  actions: {
    createGroup(name, color, parentId = null, description = '', keywords = []) {
      if (!name?.trim()) return null
      let groupName = name.trim(); let suffix = 1; const baseName = groupName
      while (this.groups.some(g => g.name === groupName)) groupName = `${baseName} (${suffix++})`
      const id = 'g_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6)
      const usedColors = new Set(this.groups.map(g => g.color))
      const autoColor = color || GROUP_COLORS.find(c => !usedColors.has(c)) || GROUP_COLORS[this.groups.length % GROUP_COLORS.length]
      const group = { id, name: groupName, count: 0, color: autoColor, collapsed: false, parentId: parentId || null, visible: true, description: description || '', keywords: keywords || [], _createdAt: Date.now() }
      this.groups.push(group)
      return group
    },
    renameGroup(groupId, newName) {
      if (!newName?.trim()) return false
      const group = this.groups.find(g => g.id === groupId)
      if (!group || group.id === 'default') return false
      let name = newName.trim(); let suffix = 1; const baseName = name
      while (this.groups.some(g => g.id !== groupId && g.name === name)) name = `${baseName} (${suffix++})`
      group.name = name; this._syncGroupNameToNodes(groupId, name); return true
    },
    setGroupColor(groupId, color) { const group = this.groups.find(g => g.id === groupId); if (!group || group.id === 'default') return false; group.color = color; return true },
    setGroupDescription(groupId, description) { const group = this.groups.find(g => g.id === groupId); if (!group) return false; group.description = description || ''; return true },
    setGroupKeywords(groupId, keywords) { const group = this.groups.find(g => g.id === groupId); if (!group) return false; group.keywords = Array.isArray(keywords) ? keywords : []; return true },
    setParentGroup(groupId, parentId) {
      if (groupId === parentId || groupId === 'default') return false
      const group = this.groups.find(g => g.id === groupId); if (!group) return false
      if (parentId) { let current = this.groups.find(g => g.id === parentId); while (current) { if (current.id === groupId) return false; current = current.parentId ? this.groups.find(g => g.id === current.parentId) : null } }
      group.parentId = parentId || null; return true
    },
    toggleGroupVisibility(groupId) {
      const group = this.groups.find(g => g.id === groupId); if (!group) return false
      group.visible = group.visible === false ? true : false
      this.groups.filter(g => g.parentId === groupId).forEach(d => { d.visible = group.visible })
      return group.visible
    },
    setGroupVisibility(groupId, visible) { const group = this.groups.find(g => g.id === groupId); if (!group) return false; group.visible = !!visible; return true },
    showAllGroups() { for (const g of this.groups) g.visible = true },
    getHiddenNodeIds() {
      const graphStore = _getGraphStore(); if (!graphStore) return new Set()
      const hiddenGroupIds = new Set()
      for (const g of this.groups) { if (g.visible === false) { hiddenGroupIds.add(g.id); const stack = [g.id]; while (stack.length) { const pid = stack.pop(); for (const child of this.groups) { if (child.parentId === pid) { hiddenGroupIds.add(child.id); stack.push(child.id) } } } } }
      const ids = new Set()
      for (const n of graphStore.nodes) if (hiddenGroupIds.has(n.groupId)) ids.add(n.id)
      return ids
    },
    _calcNodeGroupMatch(node, group) {
      if (!group.keywords?.length) return 0
      const nodeText = [node.title || '', node.description || '', ...(node.keywords || []), ...(node.entities || [])].join(' ').toLowerCase()
      let matchCount = 0; let totalWeight = 0
      for (const kw of group.keywords) {
        const kwLower = kw.toLowerCase(); totalWeight += 1
        if (nodeText.includes(kwLower)) { matchCount += 1; continue }
        const parts = kwLower.split(/\s+/); let partialMatch = 0
        for (const part of parts) { if (part.length > 1 && nodeText.includes(part)) partialMatch += 0.5 }
        matchCount += Math.min(partialMatch, 1)
      }
      return totalWeight > 0 ? matchCount / totalWeight : 0
    },
    autoClassifyNodes() {
      const graphStore = _getGraphStore(); if (!graphStore) return { classified: 0, details: [] }
      const classifiableGroups = this.groups.filter(g => g.id !== 'default' && g.keywords?.length > 0)
      if (!classifiableGroups.length) return { classified: 0, details: [], msg: '没有设置关键词的分组，请先为分组添加关键词' }
      const unclassifiedNodes = graphStore.nodes.filter(n => n.validate?.status !== 'discarded' && (!n.groupId || n.groupId === 'default'))
      const details = []; let classified = 0
      for (const node of unclassifiedNodes) {
        let bestGroup = null; let bestScore = 0
        for (const group of classifiableGroups) { const score = this._calcNodeGroupMatch(node, group); if (score > bestScore) { bestScore = score; bestGroup = group } }
        if (bestGroup && bestScore >= this.autoClassifyThreshold) {
          node.groupId = bestGroup.id; node.groupName = bestGroup.name; classified++
          details.push({ nodeId: node.id, nodeTitle: node.title, groupId: bestGroup.id, groupName: bestGroup.name, score: Math.round(bestScore * 100) / 100 })
        }
      }
      if (classified > 0) { this._recount(); if (graphStore.version !== undefined) graphStore.version++ }
      return { classified, details }
    },
    previewAutoClassify() {
      const graphStore = _getGraphStore(); if (!graphStore) return { total: 0, details: [] }
      const classifiableGroups = this.groups.filter(g => g.id !== 'default' && g.keywords?.length > 0)
      if (!classifiableGroups.length) return { total: 0, details: [] }
      const unclassifiedNodes = graphStore.nodes.filter(n => n.validate?.status !== 'discarded' && (!n.groupId || n.groupId === 'default'))
      const details = []
      for (const node of unclassifiedNodes) {
        let bestGroup = null; let bestScore = 0
        for (const group of classifiableGroups) { const score = this._calcNodeGroupMatch(node, group); if (score > bestScore) { bestScore = score; bestGroup = group } }
        if (bestGroup && bestScore >= this.autoClassifyThreshold) details.push({ nodeId: node.id, nodeTitle: node.title, groupId: bestGroup.id, groupName: bestGroup.name, score: Math.round(bestScore * 100) / 100 })
      }
      return { total: details.length, details }
    },
    toggleCollapse(groupId) { const group = this.groups.find(g => g.id === groupId); if (!group) return; group.collapsed = !group.collapsed },
    toggleTreeCollapse(groupId) { this.treeCollapsed[groupId] = !this.treeCollapsed[groupId] },
    setSortBy(sortBy) { if (this.groupSortBy === sortBy) { this.groupSortAsc = !this.groupSortAsc } else { this.groupSortBy = sortBy; this.groupSortAsc = true } },
    setSearch(keyword) { this.groupSearch = keyword || '' },
    mergeGroups(sourceGroupId, targetGroupId) {
      if (sourceGroupId === targetGroupId) return { ok: false, mergedCount: 0, reason: '不能合并到自身' }
      if (sourceGroupId === 'default' || targetGroupId === 'default') return { ok: false, mergedCount: 0, reason: '不能合并默认分组' }
      const sourceGroup = this.groups.find(g => g.id === sourceGroupId); const targetGroup = this.groups.find(g => g.id === targetGroupId)
      if (!sourceGroup || !targetGroup) return { ok: false, mergedCount: 0, reason: '分组不存在' }
      if (this.descendantsOf(sourceGroupId).some(d => d.id === targetGroupId)) return { ok: false, mergedCount: 0, reason: '目标分组是源分组的后代，会导致循环' }
      const graphStore = _getGraphStore(); let mergedCount = 0
      if (graphStore) { for (const n of graphStore.nodes) { if (n.groupId === sourceGroupId) { n.groupId = targetGroupId; n.groupName = targetGroup.name; mergedCount++ } } }
      const childGroups = this.groups.filter(g => g.parentId === sourceGroupId)
      for (const cg of childGroups) cg.parentId = targetGroupId
      const idx = this.groups.findIndex(g => g.id === sourceGroupId)
      if (idx >= 0) this.groups.splice(idx, 1)
      targetGroup.count = (targetGroup.count || 0) + mergedCount
      if (this.currentGroupId === sourceGroupId) this.currentGroupId = targetGroupId
      return { ok: true, mergedCount, sourceName: sourceGroup.name, targetName: targetGroup.name }
    },
    deleteGroup(groupId) {
      if (groupId === 'default') return false
      const idx = this.groups.findIndex(g => g.id === groupId); if (idx === -1) return false
      const removed = this.groups.splice(idx, 1)[0]
      const childGroups = this.groups.filter(g => g.parentId === groupId)
      for (const cg of childGroups) cg.parentId = removed.parentId || null
      const graphStore = _getGraphStore()
      if (graphStore) { for (const n of graphStore.nodes) { if (n.groupId === groupId) { n.groupId = 'default'; n.groupName = '默认分组' } } }
      const defaultGroup = this.groups[0]
      if (defaultGroup) defaultGroup.count = (graphStore?.nodes || []).filter(n => n.groupId === 'default').length
      if (this.currentGroupId === groupId) this.currentGroupId = 'all'
      return true
    },
    switchGroup(groupId) { this.currentGroupId = groupId || 'all' },
    moveNodeToGroup(nodeId, groupId) {
      const graphStore = _getGraphStore(); if (!graphStore) return false
      const node = graphStore.nodes.find(n => n.id === nodeId); if (!node) return false
      const targetGroup = this.groups.find(g => g.id === groupId); if (!targetGroup && groupId !== 'all') return false
      node.groupId = groupId; node.groupName = targetGroup?.name || '默认分组'; this._recount(); return true
    },
    batchMoveToGroup(nodeIds, groupId) {
      if (!nodeIds?.length) return 0
      const graphStore = _getGraphStore(); if (!graphStore) return 0
      const targetGroup = this.groups.find(g => g.id === groupId); if (!targetGroup) return 0
      let count = 0
      for (const nid of nodeIds) { const node = graphStore.nodes.find(n => n.id === nid); if (!node) continue; node.groupId = groupId; node.groupName = targetGroup.name; count++ }
      if (count > 0) this._recount()
      return count
    },
    dropNodeToGroup(nodeId, groupId) { const result = this.moveNodeToGroup(nodeId, groupId); if (result) this.batchSelectedNodes = this.batchSelectedNodes.filter(id => id !== nodeId); return result },
    toggleBatchSelect(nodeId) { const idx = this.batchSelectedNodes.indexOf(nodeId); if (idx >= 0) this.batchSelectedNodes.splice(idx, 1); else this.batchSelectedNodes.push(nodeId) },
    toggleSelectAll() {
      const graphStore = _getGraphStore(); if (!graphStore) return
      if (this.batchSelectedNodes.length === graphStore.nodeCount) this.batchSelectedNodes = []
      else this.batchSelectedNodes = graphStore.nodes.map(n => n.id)
    },
    clearBatchSelection() { this.batchSelectedNodes = [] },
    assignGroupForNodes(nodes, groupName) {
      if (!nodes?.length) return
      let group = this.groups.find(g => g.name === groupName)
      if (!group) group = this.createGroup(groupName)
      if (!group) return
      for (const n of nodes) { n.groupId = group.id; n.groupName = group.name; n.visible = true; if (!n.isolateBlackList) n.isolateBlackList = [] }
      this._recount()
    },
    _recount() {
      const graphStore = _getGraphStore(); if (!graphStore) return
      const counts = {}
      for (const n of graphStore.nodes) counts[n.groupId] = (counts[n.groupId] || 0) + 1
      for (const g of this.groups) g.count = counts[g.id] || 0
    },
    _syncGroupNameToNodes(groupId, name) {
      const graphStore = _getGraphStore(); if (!graphStore) return
      for (const n of graphStore.nodes) if (n.groupId === groupId) n.groupName = name
    }
  },
  persist: { key: 'kg-groups-v3', storage: localStorage }
})

function buildGroupTree(groups, parentId = null) {
  return groups.filter(g => g.parentId === parentId).map(g => ({ ...g, children: buildGroupTree(groups, g.id) })).sort((a, b) => a.name.localeCompare(b.name, 'zh'))
}

export function setGraphStoreRef(store) { _setGraphStoreRef(store) }
export { GROUP_COLORS }
