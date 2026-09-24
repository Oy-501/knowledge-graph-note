/**
 * recommender.js 智能连接推荐
 */
import { extractTerms } from '@/utils/noteParser'

export function recommendConnections(content, title, nodes, linkedIds, limit = 3) {
  if ((!content && !title) || !nodes?.length) return []
  const linked = new Set(linkedIds || [])
  const candidates = nodes.filter(n => n.validate?.status !== 'discarded' && !linked.has(n.id))
  if (!candidates.length) return []
  const topics = new Set()
  for (const t of extractTerms(content || '')) { const term = t.term.toLowerCase(); if (term.length >= 2) topics.add(term) }
  if (title) {
    const tl = title.toLowerCase(); topics.add(tl)
    for (const w of title.match(/[a-zA-Z]+/g) || []) if (w.length > 2) topics.add(w.toLowerCase())
  }
  const scored = []
  for (const node of candidates) {
    const hay = ((node.title || '') + ' ' + (node.keywords || []).join(' ') + ' ' + (node.entities || []).join(' ') + ' ' + (node.description || '')).toLowerCase()
    let score = 0; const hits = []
    for (const topic of topics) { if (!topic || topic.length < 2) continue; if (hay.includes(topic)) { score += topic.length >= 4 ? 2 : 1; hits.push(topic) } }
    if (score > 0) scored.push({ node, score, hits })
  }
  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, limit).map(s => ({ node: s.node, score: s.score, reason: [...new Set(s.hits)].slice(0, 2).join('、') }))
}
