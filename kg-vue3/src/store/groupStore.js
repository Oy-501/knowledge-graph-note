/**
 * groupStore.js
 * 分组管理模块（增强版 v3）
 *
 * 功能：
 *  - 分组 CRUD（新建/重命名/删除/切换当前分组）
 *  - 分组嵌套层级（父子分组树形结构）
 *  - 分组可见性控制（一键显示/隐藏整个分组）
 *  - 分组描述与备注
 *  - 分组自动归类（基于关键词匹配）
 *  - 节点归属分组管理
 *  - 分组颜色标识
 *  - 分组排序、搜索、折叠
 *  - 批量节点操作
 *  - 节点拖拽入组
 *  - 持久化到 LocalStorage
 */

import { defineStore } from 'pinia'

// 延迟引用以避免循环依赖问题
let _graphStore = null
function _setGraphStoreRef(store) { _graphStore = store }
function _getGraphStore() { return _graphStore }

// 分组颜色调色板（20种颜色，自动轮转分配）
const GROUP_COLORS = [
  '#6C8EBF', '#82B366', '#D79B00', '#B85450', '#9673A6',
  '#4D90C1', '#7EAE5A', '#E6A817', '#C44B4B', '#8C6BAE',
  '#5B9BD5', '#67AB5A', '#F0A030', '#D9544D', '#9B7EC4',
  '#3B82C4', '#5EA85C', '#E8A020', '#C74545', '#8B69C0'
]

export const useGroupStore = defineStore('group', {
  state: () => ({
    groups: [
      {
        id: 'default', name: '默认分组', count: 0, color: '#8a93b0',
        collapsed: false, parentId: null, visible: true,
        description: '', keywords: []
      }
    ],
    currentGroupId: 'all', // 'all' 表示全部
    groupSortBy: 'name',   // 'name' | 'count' | 'created'
    groupSortAsc: true,
    groupSearch: '',       // 搜索关键词
    batchSelectedNodes: [], // 批量选中的节点ID列表
    treeCollapsed: {},     // 树形视图中折叠的分组ID → true
    autoClassifyThreshold: 0.3  // 自动归类关键词匹配阈值
  }),

  getters: {
    currentGroup(state) {
      if (state.currentGroupId === 'all') return { id: 'all', name: '全部', count: 0 }
      return state.groups.find(g => g.id === state.currentGroupId) || state.groups[0]
    },

    totalNodeCount(state) {
      return state.groups.reduce((sum, g) => sum + (g.count || 0), 0)
    },

    groupOptions(state) {
      return state.groups.map(g => ({ value: g.id, label: g.name }))
    },

    isAllMode(state) {
      return state.currentGroupId === 'all'
    },

    /** 过滤 + 排序后的分组列表 */
    filteredGroups(state) {
      let list = [...state.groups]
      // 搜索过滤
      if (state.groupSearch) {
        const kw = state.groupSearch.toLowerCase()
        list = list.filter(g => g.name.toLowerCase().includes(kw))
      }
      // 排序
      list.sort((a, b) => {
        let cmp = 0
        if (state.groupSortBy === 'name') {
          cmp = a.name.localeCompare(b.name, 'zh')
        } else if (state.groupSortBy === 'count') {
          cmp = (a.count || 0) - (b.count || 0)
        } else if (state.groupSortBy === 'created') {
          cmp = (a._createdAt || 0) - (b._createdAt || 0)
        }
        return state.groupSortAsc ? cmp : -cmp
      })
      return list
    },

    /** 分组颜色映射 */
    groupColorMap(state) {
      const map = {}
      for (const g of state.groups) {
        map[g.id] = g.color || '#8a93b0'
      }
      return map
    },

    // ======== 嵌套层级 getters ========

    /** 获取根分组（无父分组的顶层分组） */
    rootGroups(state) {
      return state.groups.filter(g => !g.parentId || g.parentId === 'root')
    },

    /** 获取指定分组的直接子分组 */
    childrenOf: (state) => groupId => {
      return state.groups.filter(g => g.parentId === groupId)
    },

    /** 获取指定分组的所有后代（递归） */
    descendantsOf: (state) => groupId => {
      const result = []
      const stack = state.groups.filter(g => g.parentId === groupId)
      const visited = new Set()
      while (stack.length) {
        const g = stack.pop()
        if (visited.has(g.id)) continue
        visited.add(g.id)
        result.push(g)
        const children = state.groups.filter(c => c.parentId === g.id)
        stack.push(...children)
      }
      return result
    },

    /** 获取指定分组的祖先链 */
    ancestorChain: (state) => groupId => {
      const chain = []
      let current = state.groups.find(g => g.id === groupId)
      const visited = new Set()
      while (current?.parentId) {
        if (visited.has(current.id)) break
        visited.add(current.id)
        const parent = state.groups.find(g => g.id === current.parentId)
        if (!parent) break
        chain.unshift(parent)
        current = parent
      }
      return chain
    },

    /** 分组树形结构（用于渲染） */
    groupTree(state) {
      return buildGroupTree(state.groups, null)
    },

    /** 可见分组列表（用于图谱过滤） */
    visibleGroups(state) {
      return state.groups.filter(g => g.visible !== false)
    },

    /** 隐藏的分组ID集合 */
    hiddenGroupIds(state) {
      const ids = new Set()
      for (const g of state.groups) {
        if (g.visible === false) {
          ids.add(g.id)
          // 子分组也一同隐藏
          const descendants = state.groups
            .filter(d => d.parentId === g.id)
            .map(d => d.id)
          descendants.forEach(id => ids.add(id))
        }
      }
      return ids
    },

    /** 获取可见节点（排除隐藏分组的节点，排除discarded节点） */
    visibleNodeIds(state) {
      const graphStore = _getGraphStore()
      if (!graphStore) return new Set()
      const hiddenIds = this.hiddenGroupIds
      const ids = new Set()
      for (const n of graphStore.nodes) {
        if (n.validate?.status === 'discarded') continue
        if (hiddenIds.has(n.groupId)) continue
        ids.add(n.id)
      }
      return ids
    }
  },

  actions: {
    /**
     * 创建新分组
     * @param {string} name - 分组名称
     * @param {string} color - 分组颜色
     * @param {string|null} parentId - 父分组ID（null = 顶层）
     * @param {string} description - 分组描述
     * @param {string[]} keywords - 自动归类关键词
     */
    createGroup(name, color, parentId = null, description = '', keywords = []) {
      if (!name?.trim()) return null
      let groupName = name.trim()
      // 处理重名
      let suffix = 1
      const baseName = groupName
      while (this.groups.some(g => g.name === groupName)) {
        groupName = `${baseName} (${suffix++})`
      }
      const id = 'g_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6)
      // 自动分配颜色
      const usedColors = new Set(this.groups.map(g => g.color))
      const autoColor = color ||
        GROUP_COLORS.find(c => !usedColors.has(c)) ||
        GROUP_COLORS[this.groups.length % GROUP_COLORS.length]
      const group = {
        id,
        name: groupName,
        count: 0,
        color: autoColor,
        collapsed: false,
        parentId: parentId || null,
        visible: true,
        description: description || '',
        keywords: keywords || [],
        _createdAt: Date.now()
      }
      this.groups.push(group)
      return group
    },

    /**
     * 重命名分组
     */
    renameGroup(groupId, newName) {
      if (!newName?.trim()) return false
      const group = this.groups.find(g => g.id === groupId)
      if (!group || group.id === 'default') return false
      let name = newName.trim()
      let suffix = 1
      const baseName = name
      while (this.groups.some(g => g.id !== groupId && g.name === name)) {
        name = `${baseName} (${suffix++})`
      }
      group.name = name
      this._syncGroupNameToNodes(groupId, name)
      return true
    },

    /**
     * 设置分组颜色
     */
    setGroupColor(groupId, color) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group || group.id === 'default') return false
      group.color = color
      return true
    },

    /**
     * 设置分组描述
     */
    setGroupDescription(groupId, description) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return false
      group.description = description || ''
      return true
    },

    /**
     * 设置分组关键词（用于自动归类）
     */
    setGroupKeywords(groupId, keywords) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return false
      group.keywords = Array.isArray(keywords) ? keywords : []
      return true
    },

    /**
     * 设置父分组（移动分组层级）
     */
    setParentGroup(groupId, parentId) {
      if (groupId === parentId) return false
      if (groupId === 'default') return false
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return false
      // 防止循环引用
      if (parentId) {
        let current = this.groups.find(g => g.id === parentId)
        while (current) {
          if (current.id === groupId) return false
          current = current.parentId ? this.groups.find(g => g.id === current.parentId)
            : null
        }
      }
      group.parentId = parentId || null
      return true
    },

    // ======== 可见性控制 ========

    /**
     * 切换分组可见性
     */
    toggleGroupVisibility(groupId) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return false
      group.visible = group.visible === false ? true : false
      // 子分组同步
      const descendants = this.groups.filter(g => g.parentId === groupId)
      for (const d of descendants) {
        d.visible = group.visible
      }
      return group.visible
    },

    /**
     * 设置分组可见性
     */
    setGroupVisibility(groupId, visible) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return false
      group.visible = !!visible
      return true
    },

    /**
     * 显示所有分组
     */
    showAllGroups() {
      for (const g of this.groups) {
        g.visible = true
      }
    },

    /**
     * 获取当前需要隐藏的节点ID列表（不可见分组中的节点）
     */
    getHiddenNodeIds() {
      const graphStore = _getGraphStore()
      if (!graphStore) return new Set()
      const hiddenGroupIds = new Set()
      for (const g of this.groups) {
        if (g.visible === false) {
          hiddenGroupIds.add(g.id)
          // 递归子分组
          const stack = [g.id]
          while (stack.length) {
            const pid = stack.pop()
            for (const child of this.groups) {
              if (child.parentId === pid) {
                hiddenGroupIds.add(child.id)
                stack.push(child.id)
              }
            }
          }
        }
      }
      const ids = new Set()
      for (const n of graphStore.nodes) {
        if (hiddenGroupIds.has(n.groupId)) ids.add(n.id)
      }
      return ids
    },

    // ======== 自动归类 ========

    /**
     * 计算节点与分组关键词的匹配度
     * @param {Object} node - 节点对象
     * @param {Object} group - 分组对象
     * @returns {number} 0-1 匹配分数
     */
    _calcNodeGroupMatch(node, group) {
      if (!group.keywords?.length) return 0
      const nodeText = [
        node.title || '',
        node.description || '',
        ...(node.keywords || []),
        ...(node.entities || [])
      ].join(' ').toLowerCase()

      let matchCount = 0
      let totalWeight = 0
      for (const kw of group.keywords) {
        const kwLower = kw.toLowerCase()
        totalWeight += 1
        // 精确匹配
        if (nodeText.includes(kwLower)) {
          matchCount += 1
          continue
        }
        // 分词部分匹配
        const parts = kwLower.split(/\s+/)
        let partialMatch = 0
        for (const part of parts) {
          if (part.length > 1 && nodeText.includes(part)) {
            partialMatch += 0.5
          }
        }
        matchCount += Math.min(partialMatch, 1)
      }
      return totalWeight > 0 ? matchCount / totalWeight : 0
    },

    /**
     * 自动归类：将未分组的节点自动匹配到最合适的分组
     * @returns {{classified: number, details: Array}}
     */
    autoClassifyNodes() {
      const graphStore = _getGraphStore()
      if (!graphStore) return { classified: 0, details: [] }

      // 获取有关键词的分组（排除默认分组）
      const classifiableGroups = this.groups.filter(
        g => g.id !== 'default' && g.keywords?.length > 0
      )
      if (!classifiableGroups.length) {
        return { classified: 0, details: [], msg: '没有设置关键词的分组，请先为分组添加关键词' }
      }

      // 获取未分组或默认分组的节点
      const unclassifiedNodes = graphStore.nodes.filter(
        n => n.validate?.status !== 'discarded' &&
             (!n.groupId || n.groupId === 'default')
      )

      const details = []
      let classified = 0

      for (const node of unclassifiedNodes) {
        let bestGroup = null
        let bestScore = 0

        for (const group of classifiableGroups) {
          const score = this._calcNodeGroupMatch(node, group)
          if (score > bestScore) {
            bestScore = score
            bestGroup = group
          }
        }

        if (bestGroup && bestScore >= this.autoClassifyThreshold) {
          node.groupId = bestGroup.id
          node.groupName = bestGroup.name
          classified++
          details.push({
            nodeId: node.id,
            nodeTitle: node.title,
            groupId: bestGroup.id,
            groupName: bestGroup.name,
            score: Math.round(bestScore * 100) / 100
          })
        }
      }

      if (classified > 0) {
        this._recount()
        if (graphStore.version !== undefined) graphStore.version++
      }

      return { classified, details }
    },

    /**
     * 预览自动归类结果（不实际执行）
     */
    previewAutoClassify() {
      const graphStore = _getGraphStore()
      if (!graphStore) return { total: 0, details: [] }

      const classifiableGroups = this.groups.filter(
        g => g.id !== 'default' && g.keywords?.length > 0
      )
      if (!classifiableGroups.length) return { total: 0, details: [] }

      const unclassifiedNodes = graphStore.nodes.filter(
        n => n.validate?.status !== 'discarded' &&
             (!n.groupId || n.groupId === 'default')
      )

      const details = []
      for (const node of unclassifiedNodes) {
        let bestGroup = null
        let bestScore = 0
        for (const group of classifiableGroups) {
          const score = this._calcNodeGroupMatch(node, group)
          if (score > bestScore) {
            bestScore = score
            bestGroup = group
          }
        }
        if (bestGroup && bestScore >= this.autoClassifyThreshold) {
          details.push({
            nodeId: node.id,
            nodeTitle: node.title,
            groupId: bestGroup.id,
            groupName: bestGroup.name,
            score: Math.round(bestScore * 100) / 100
          })
        }
      }
      return { total: details.length, details }
    },

    // ======== 折叠控制 ========

    /**
     * 切换分组折叠
     */
    toggleCollapse(groupId) {
      const group = this.groups.find(g => g.id === groupId)
      if (!group) return
      group.collapsed = !group.collapsed
    },

    /**
     * 切换树形视图中的折叠
     */
    toggleTreeCollapse(groupId) {
      this.treeCollapsed[groupId] = !this.treeCollapsed[groupId]
    },

    // ======== 排序与搜索 ========

    /**
     * 设置排序方式
     */
    setSortBy(sortBy) {
      if (this.groupSortBy === sortBy) {
        this.groupSortAsc = !this.groupSortAsc
      } else {
        this.groupSortBy = sortBy
        this.groupSortAsc = true
      }
    },

    /**
     * 设置搜索关键词
     */
    setSearch(keyword) {
      this.groupSearch = keyword || ''
    },

    // ======== 分组合并 ========

    /**
     * 分组合并：将 sourceGroup 的所有节点合并到 targetGroup，删除 sourceGroup
     */
    mergeGroups(sourceGroupId, targetGroupId) {
      if (sourceGroupId === targetGroupId) return { ok: false, mergedCount: 0, reason: '不能合并到自身' }
      if (sourceGroupId === 'default' || targetGroupId === 'default') return { ok: false, mergedCount: 0, reason: '不能合并默认分组' }
      const sourceGroup = this.groups.find(g => g.id === sourceGroupId)
      const targetGroup = this.groups.find(g => g.id === targetGroupId)
      if (!sourceGroup || !targetGroup) return { ok: false, mergedCount: 0, reason: '分组不存在' }

      // 检查 targetGroupId 是否在 sourceGroupId 的后代中（防环）
      const descendants = this.descendantsOf(sourceGroupId)
      if (descendants.some(d => d.id === targetGroupId)) {
        return { ok: false, mergedCount: 0, reason: '目标分组是源分组的后代，会导致循环' }
      }

      const graphStore = _getGraphStore()
      let mergedCount = 0
      if (graphStore) {
        for (const n of graphStore.nodes) {
          if (n.groupId === sourceGroupId) {
            n.groupId = targetGroupId
            n.groupName = targetGroup.name
            mergedCount++
          }
        }
      }

      // 子分组重新归属
      const childGroups = this.groups.filter(g => g.parentId === sourceGroupId)
      for (const cg of childGroups) {
        cg.parentId = targetGroupId
      }

      // 移除 sourceGroup
      const idx = this.groups.findIndex(g => g.id === sourceGroupId)
      if (idx >= 0) this.groups.splice(idx, 1)

      // 更新 targetGroup 计数
      targetGroup.count = (targetGroup.count || 0) + mergedCount

      // 如果当前切换在 sourceGroup，切换到 targetGroup
      if (this.currentGroupId === sourceGroupId) {
        this.currentGroupId = targetGroupId
      }

      return {
        ok: true,
        mergedCount,
        sourceName: sourceGroup.name,
        targetName: targetGroup.name
      }
    },

    /**
     * 删除分组（节点归入默认分组，子分组归入父分组或默认）
     */
    deleteGroup(groupId) {
      if (groupId === 'default') return false
      const idx = this.groups.findIndex(g => g.id === groupId)
      if (idx === -1) return false
      const removed = this.groups.splice(idx, 1)[0]

      // 子分组重新归属到被删除分组的父分组
      const childGroups = this.groups.filter(g => g.parentId === groupId)
      for (const cg of childGroups) {
        cg.parentId = removed.parentId || null
      }

      // 被删除分组的所有节点归入默认分组
      const graphStore = _getGraphStore()
      if (graphStore) {
        for (const n of graphStore.nodes) {
          if (n.groupId === groupId) {
            n.groupId = 'default'
            n.groupName = '默认分组'
          }
        }
      }
      // 更新默认分组计数
      const defaultGroup = this.groups[0]
      if (defaultGroup) {
        defaultGroup.count = (graphStore?.nodes || []).filter(n => n.groupId === 'default').length
      }
      // 如果当前切换在该分组，回到全部
      if (this.currentGroupId === groupId) {
        this.currentGroupId = 'all'
      }
      return true
    },

    /**
     * 切换当前分组
     */
    switchGroup(groupId) {
      this.currentGroupId = groupId || 'all'
    },

    // ======== 节点归属管理 ========

    /**
     * 将节点移入指定分组
     */
    moveNodeToGroup(nodeId, groupId) {
      const graphStore = _getGraphStore()
      if (!graphStore) return false
      const node = graphStore.nodes.find(n => n.id === nodeId)
      if (!node) return false
      const targetGroup = this.groups.find(g => g.id === groupId)
      if (!targetGroup && groupId !== 'all') return false
      node.groupId = groupId
      node.groupName = targetGroup?.name || '默认分组'
      this._recount()
      return true
    },

    /**
     * 批量移动节点到分组
     */
    batchMoveToGroup(nodeIds, groupId) {
      if (!nodeIds?.length) return 0
      const graphStore = _getGraphStore()
      if (!graphStore) return 0
      const targetGroup = this.groups.find(g => g.id === groupId)
      if (!targetGroup) return 0
      let count = 0
      for (const nid of nodeIds) {
        const node = graphStore.nodes.find(n => n.id === nid)
        if (!node) continue
        node.groupId = groupId
        node.groupName = targetGroup.name
        count++
      }
      if (count > 0) this._recount()
      return count
    },

    /**
     * 拖拽节点到分组（单个节点快速入组）
     */
    dropNodeToGroup(nodeId, groupId) {
      const result = this.moveNodeToGroup(nodeId, groupId)
      if (result) {
        this.batchSelectedNodes = this.batchSelectedNodes.filter(id => id !== nodeId)
      }
      return result
    },

    // ======== 批量选择 ========

    /**
     * 批量选择节点切换
     */
    toggleBatchSelect(nodeId) {
      const idx = this.batchSelectedNodes.indexOf(nodeId)
      if (idx >= 0) {
        this.batchSelectedNodes.splice(idx, 1)
      } else {
        this.batchSelectedNodes.push(nodeId)
      }
    },

    /**
     * 全选/取消全选
     */
    toggleSelectAll() {
      const graphStore = _getGraphStore()
      if (!graphStore) return
      if (this.batchSelectedNodes.length === graphStore.nodeCount) {
        this.batchSelectedNodes = []
      } else {
        this.batchSelectedNodes = graphStore.nodes.map(n => n.id)
      }
    },

    /**
     * 清空批量选择
     */
    clearBatchSelection() {
      this.batchSelectedNodes = []
    },

    /**
     * 为新节点批量分配分组
     */
    assignGroupForNodes(nodes, groupName) {
      if (!nodes?.length) return
      let group = this.groups.find(g => g.name === groupName)
      if (!group) {
        group = this.createGroup(groupName)
      }
      if (!group) return
      for (const n of nodes) {
        n.groupId = group.id
        n.groupName = group.name
        n.visible = true
        if (!n.isolateBlackList) n.isolateBlackList = []
      }
      this._recount()
    },

    // ======== 内部工具 ========

    /**
     * 重新计算各分组节点数
     */
    _recount() {
      const graphStore = _getGraphStore()
      if (!graphStore) return
      const counts = {}
      for (const n of graphStore.nodes) {
        counts[n.groupId] = (counts[n.groupId] || 0) + 1
      }
      for (const g of this.groups) {
        g.count = counts[g.id] || 0
      }
    },

    /**
     * 同步分组名到所有节点
     */
    _syncGroupNameToNodes(groupId, name) {
      const graphStore = _getGraphStore()
      if (!graphStore) return
      for (const n of graphStore.nodes) {
        if (n.groupId === groupId) n.groupName = name
      }
    }
  },

  persist: {
    key: 'kg-groups-v3',
    storage: localStorage
  }
})

/**
 * 构建分组树形结构
 * @param {Array} groups - 所有分组
 * @param {string|null} parentId - 父分组ID
 * @returns {Array} 树形节点数组
 */
function buildGroupTree(groups, parentId = null) {
  return groups
    .filter(g => g.parentId === parentId)
    .map(g => ({
      ...g,
      children: buildGroupTree(groups, g.id)
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
}

// 导出引用设置函数
export function setGraphStoreRef(store) { _setGraphStoreRef(store) }

// 导出颜色常量供外部使用
export { GROUP_COLORS }