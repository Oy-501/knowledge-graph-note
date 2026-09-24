/**
 * qa.js
 * 轻量知识问答引擎（纯图遍历，不依赖外部 LLM）。
 *
 * 支持两类问题：
 *  1) 关系查询：「X 和 Y 有什么关系」→ 图最短路径 + 逐跳关系类型 + 证据原文
 *  2) 主题查询：「我学过哪些关于 X 的知识」→ 匹配相关节点列表 + 摘要
 */
import { extractTerms, matchGraphNodes } from '@/utils/noteParser'
import { endpointId } from '@/utils/graph'

/** 从文本中识别图谱实体（节点标题包含匹配，最长优先去重） */
export function findEntities(text, nodes) {
  const lower = (text || '').toLowerCase()
  const found = []
  for (const n of nodes || []) {
    if (n.validate?.status === 'discarded') continue
    const title = (n.title || '').toLowerCase()
    if (title && lower.includes(title)) found.push(n)
  }
  found.sort((a, b) => (b.title || '').length - (a.title || '').length)
  const seen = new Set()
  return found.filter(n => {
    if (seen.has(n.id)) return false
    seen.add(n.id)
    return true
  })
}

/** 无向图 BFS 最短路径：返回 { found, path: [nodeId], edges: [{a, b, link}] } */
export function findShortestPath(sourceId, targetId, nodes, links) {
  const adj = new Map()
  const edgeMap = new Map()
  for (const l of links || []) {
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (!adj.has(s)) adj.set(s, [])
    if (!adj.has(t)) adj.set(t, [])
    adj.get(s).push(t)
    adj.get(t).push(s)
    const key = s < t ? s + '|' + t : t + '|' + s
    if (!edgeMap.has(key)) edgeMap.set(key, l)
  }

  const prev = new Map()
  const visited = new Set([sourceId])
  const queue = [sourceId]
  while (queue.length) {
    const cur = queue.shift()
    if (cur === targetId) break
    for (const nb of (adj.get(cur) || [])) {
      if (!visited.has(nb)) {
        visited.add(nb)
        prev.set(nb, cur)
        queue.push(nb)
      }
    }
  }

  if (!visited.has(targetId)) return { found: false, path: [], edges: [] }

  const path = []
  let cur = targetId
  while (cur) {
    path.unshift(cur)
    if (cur === sourceId) break
    cur = prev.get(cur)
  }
  const edges = []
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i]
    const b = path[i + 1]
    const key = a < b ? a + '|' + b : b + '|' + a
    edges.push({ a, b, link: edgeMap.get(key) || null })
  }
  return { found: true, path, edges }
}

function nodeById(id, nodes) {
  return (nodes || []).find(n => n.id === id) || null
}

function degreeOf(id, links) {
  let d = 0
  for (const l of links || []) {
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (s === id) d++
    if (t === id) d++
  }
  return d
}

/** 主题匹配：术语 + 标题包含，返回带摘要的相关节点 */
export function findRelated(text, nodes, links) {
  const terms = extractTerms(text || '')
  let matched = matchGraphNodes(terms, nodes)
  if (matched.length === 0) {
    const lower = (text || '').toLowerCase()
    matched = (nodes || [])
      .filter(n => n.validate?.status !== 'discarded'
        && (n.title || '')
        && lower.includes((n.title || '').toLowerCase()))
      .map(n => ({ node: n, matchType: 'title_contains', term: n.title }))
  }
  return matched.map(m => ({
    node: m.node,
    term: m.term,
    matchType: m.matchType,
    degree: degreeOf(m.node.id, links)
  }))
}

/**
 * 主入口：解析问题并作答。
 * @returns {{ type: 'relation'|'topic'|'none', ... }}
 */
export function answer(text, nodes, links) {
  const t = (text || '').trim()
  if (!t) return { type: 'none', message: '请输入你的问题' }

  const entities = findEntities(t, nodes)

  // 关系查询：识别到 >=2 个实体
  if (entities.length >= 2) {
    const a = entities[0]
    const b = entities[1]
    const path = findShortestPath(a.id, b.id, nodes, links)
    return { type: 'relation', a, b, path }
  }

  // 主题查询
  const related = findRelated(t, nodes, links)
  return { type: 'topic', query: t, related }
}

/** 生成关系查询的自然语言描述（供 UI 渲染） */
export function describePath(a, b, path, nodes) {
  if (!path.found) {
    return {
      summary: `未找到「${a.title}」与「${b.title}」之间的直接或间接关联，它们可能分属不同的知识簇。`,
      hops: []
    }
  }
  const hops = path.edges.map((e, i) => {
    const from = nodeById(e.a, nodes)
    const to = nodeById(e.b, nodes)
    const link = e.link || {}
    return {
      from: from ? from.title : e.a,
      to: to ? to.title : e.b,
      label: link.relation_label || link.relation_type || '关联',
      type: link.relation_type || 'related',
      evidence: link.relation_evidence || link.evidence || '',
      score: link.score || 0
    }
  })
  const summary = `「${a.title}」与「${b.title}」之间存在 ${hops.length} 跳关联路径`
  return { summary, hops }
}
