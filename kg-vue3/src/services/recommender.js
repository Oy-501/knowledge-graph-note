/**
 * recommender.js
 * 智能连接推荐：根据用户正在写的内容 + 笔记标题，推荐可关联的已有知识点。
 *
 * 轻量启发式（前端本地，无需向量引擎）：
 *  1) 从正文提取常见术语 + 标题分词，作为「正在写的话题」候选词
 *  2) 对每个未关联的知识点，统计其 title/keywords/entities/description 命中的候选词
 *  3) 按命中权重排序，取 top N 返回
 */
import { extractTerms } from '@/utils/noteParser'

/**
 * @param {string} content 笔记正文
 * @param {string} title 笔记标题
 * @param {Array} nodes graphStore.nodes
 * @param {Array} linkedIds 已关联节点 id
 * @param {number} limit 返回条数
 * @returns {Array<{node: object, reason: string, score: number}>}
 */
export function recommendConnections(content, title, nodes, linkedIds, limit = 3) {
  if ((!content && !title) || !nodes?.length) return []

  const linked = new Set(linkedIds || [])
  const candidates = nodes.filter(n => n.validate?.status !== 'discarded' && !linked.has(n.id))
  if (!candidates.length) return []

  // 1. 收集候选话题词
  const topics = new Set()
  for (const t of extractTerms(content || '')) {
    const term = t.term.toLowerCase()
    if (term.length >= 2) topics.add(term)
  }
  if (title) {
    const tl = title.toLowerCase()
    topics.add(tl)
    for (const w of title.match(/[a-zA-Z]+/g) || []) {
      if (w.length > 2) topics.add(w.toLowerCase())
    }
  }

  // 2. 打分
  const scored = []
  for (const node of candidates) {
    const hay = (
      (node.title || '')
      + ' ' + (node.keywords || []).join(' ')
      + ' ' + (node.entities || []).join(' ')
      + ' ' + (node.description || '')
    ).toLowerCase()

    let score = 0
    const hits = []
    for (const topic of topics) {
      if (!topic || topic.length < 2) continue
      if (hay.includes(topic)) {
        score += topic.length >= 4 ? 2 : 1
        hits.push(topic)
      }
    }
    if (score > 0) scored.push({ node, score, hits })
  }

  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, limit).map(s => ({
    node: s.node,
    score: s.score,
    reason: [...new Set(s.hits)].slice(0, 2).join('、')
  }))
}
