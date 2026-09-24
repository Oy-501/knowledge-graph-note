/**
 * learningPath.js
 * 知识导出为学习路径：沿 prerequisite（前置知识）边反向追溯，
 * 收集目标节点的全部前置知识点，按层级分层生成学习大纲，可导出 Markdown。
 *
 * 前置边方向约定（后端 inference.classify_relation）：
 *   source 是更高层级的节点，target 是它的前置知识（更基础的节点）。
 *   即「要学 source，得先学 target」。
 */
import { getLevelInfo } from '@/utils/mdParser'
import { downloadText } from '@/utils/download'
import { endpointId } from '@/utils/graph'

/**
 * 从目标节点出发，沿 prerequisite 边反向收集所有前置节点（含传递前置）。
 * @param {string} targetNodeId
 * @param {Array} nodes graphStore.nodes
 * @param {Array} links graphStore.links
 * @returns {{ target: object|null, prerequisites: Array<object> }} prerequisites 已按 level 升序排列
 */
export function buildLearningPath(targetNodeId, nodes, links) {
  const nodeMap = new Map((nodes || []).map(n => [n.id, n]))
  // 前置邻接表：source -> [前置 target 列表]
  const prereqOf = new Map()
  for (const l of (links || [])) {
    if (l.relation_type !== 'prerequisite') continue
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (!prereqOf.has(s)) prereqOf.set(s, [])
    prereqOf.get(s).push(t)
  }

  // DFS 收集所有可达前置（含传递）
  const visited = new Set()
  const stack = [targetNodeId]
  const collected = []
  while (stack.length) {
    const id = stack.pop()
    if (visited.has(id)) continue
    visited.add(id)
    const node = nodeMap.get(id)
    if (node) collected.push(node)
    for (const p of (prereqOf.get(id) || [])) {
      if (!visited.has(p)) stack.push(p)
    }
  }

  const prerequisites = collected
    .filter(n => n.id !== targetNodeId)
    .sort((a, b) => ((a.level || 3) - (b.level || 3)) || String(a.title || '').localeCompare(String(b.title || '')))

  return { target: nodeMap.get(targetNodeId) || null, prerequisites }
}

/** 按层级分组（低层级基础在前），返回 [{ level, label, items: [node] }] */
export function groupByLevel(prerequisites) {
  const map = new Map()
  for (const p of prerequisites) {
    const lv = p.level || 3
    if (!map.has(lv)) map.set(lv, [])
    map.get(lv).push(p)
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([lv, items]) => ({ level: lv, label: getLevelInfo(lv).label, items }))
}

/** 生成学习路径 Markdown */
export function toLearningPathMarkdown(target, prerequisites) {
  const title = target?.title || '未知知识点'
  const lines = [`# 学习路径：${title}`, '']
  if (!prerequisites.length) {
    lines.push('> 未发现前置知识点，可直接开始学习。')
    return lines.join('\n')
  }
  const groups = groupByLevel(prerequisites)
  for (const g of groups) {
    lines.push(`## L${g.level} ${g.label}`, '')
    for (const item of g.items) {
      lines.push(`- ${item.title}`)
      if (item.description) lines.push(`  - ${item.description.slice(0, 80)}`)
    }
    lines.push('')
  }
  lines.push('## 目标', '', `- **${title}**`, '')
  return lines.join('\n')
}

/** 浏览器下载文本文件：统一收口到 @/utils/download（保持原名再导出，供 NodeDetailDrawer 等引用） */
export { downloadText }
