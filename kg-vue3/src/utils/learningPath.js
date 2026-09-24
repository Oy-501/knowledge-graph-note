/**
 * learningPath.js 知识导出为学习路径
 */
import { getLevelInfo } from '@/utils/mdParser'
import { downloadText } from '@/utils/download'
import { endpointId } from '@/utils/graph'

export function buildLearningPath(targetNodeId, nodes, links) {
  const nodeMap = new Map((nodes || []).map(n => [n.id, n]))
  const prereqOf = new Map()
  for (const l of (links || [])) {
    if (l.relation_type !== 'prerequisite') continue
    const s = endpointId(l.source); const t = endpointId(l.target)
    if (!prereqOf.has(s)) prereqOf.set(s, [])
    prereqOf.get(s).push(t)
  }
  const visited = new Set(); const stack = [targetNodeId]; const collected = []
  while (stack.length) {
    const id = stack.pop()
    if (visited.has(id)) continue
    visited.add(id)
    const node = nodeMap.get(id)
    if (node) collected.push(node)
    for (const p of (prereqOf.get(id) || [])) if (!visited.has(p)) stack.push(p)
  }
  const prerequisites = collected.filter(n => n.id !== targetNodeId).sort((a, b) => ((a.level || 3) - (b.level || 3)) || String(a.title || '').localeCompare(String(b.title || '')))
  return { target: nodeMap.get(targetNodeId) || null, prerequisites }
}

export function groupByLevel(prerequisites) {
  const map = new Map()
  for (const p of prerequisites) { const lv = p.level || 3; if (!map.has(lv)) map.set(lv, []); map.get(lv).push(p) }
  return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([lv, items]) => ({ level: lv, label: getLevelInfo(lv).label, items }))
}

export function toLearningPathMarkdown(target, prerequisites) {
  const title = target?.title || '未知知识点'
  const lines = [`# 学习路径：${title}`, '']
  if (!prerequisites.length) { lines.push('> 未发现前置知识点，可直接开始学习。'); return lines.join('\n') }
  const groups = groupByLevel(prerequisites)
  for (const g of groups) {
    lines.push(`## L${g.level} ${g.label}`, '')
    for (const item of g.items) { lines.push(`- ${item.title}`); if (item.description) lines.push(`  - ${item.description.slice(0, 80)}`) }
    lines.push('')
  }
  lines.push('## 目标', '', `- **${title}**`, '')
  return lines.join('\n')
}

export { downloadText }
