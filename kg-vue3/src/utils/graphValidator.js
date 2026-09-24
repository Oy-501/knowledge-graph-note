/**
 * graphValidator.js 孤儿收养机制 + 图谱合法性校验
 */
import { cosine } from './vectorEngine'
import { getCrossDomainBridge } from './corpusMatcher'

export function computeDegree(node, links) {
  let d = 0
  for (const l of links) { if (l.source === node.id || l.target === node.id || (l.source && l.source.id === node.id) || (l.target && l.target.id === node.id)) d++ }
  return d
}

export function pageRank(nodes, links, opts = {}) {
  const damping = opts.damping ?? 0.85; const iterations = opts.iterations ?? 30; const N = nodes.length
  if (N === 0) return new Map()
  const outLinks = new Map(); const inLinks = new Map()
  for (const n of nodes) { outLinks.set(n.id, new Set()); inLinks.set(n.id, new Set()) }
  for (const l of links) { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; if (outLinks.has(s) && inLinks.has(t)) { outLinks.get(s).add(t); inLinks.get(t).add(s) } }
  let pr = new Map()
  for (const n of nodes) pr.set(n.id, 1 / N)
  for (let it = 0; it < iterations; it++) {
    const next = new Map(); let dangling = 0
    for (const n of nodes) if (outLinks.get(n.id).size === 0) dangling += pr.get(n.id)
    for (const n of nodes) {
      let sum = 0
      for (const inId of inLinks.get(n.id)) { const outDeg = outLinks.get(inId).size; if (outDeg > 0) sum += pr.get(inId) / outDeg }
      sum += dangling / N
      next.set(n.id, (1 - damping) / N + damping * sum)
    }
    pr = next
  }
  return pr
}

export function detectOrphans(nodes, links) {
  const orphanSet = new Set(); const degreeMap = new Map()
  for (const n of nodes) degreeMap.set(n.id, 0)
  for (const l of links) { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; if (degreeMap.has(s)) degreeMap.set(s, degreeMap.get(s) + 1); if (degreeMap.has(t)) degreeMap.set(t, degreeMap.get(t) + 1) }
  for (const n of nodes) { if (n.validate?.status === 'discarded') continue; if (degreeMap.get(n.id) === 0) orphanSet.add(n.id) }
  return { orphans: orphanSet, degreeMap }
}

function qualifyAdoption(orphanNode, candidates) {
  const quality = orphanNode._quality
  if (quality && !quality.qualified) return { qualified: false, reason: `知识点"${orphanNode.title}"未通过资格审核（${quality.reason}），不进行收养`, bestCandidate: null, bestScore: 0, bestType: '' }
  if (candidates.length === 0) return { qualified: false, reason: `"${orphanNode.title}"无候选节点可收养`, bestCandidate: null, bestScore: 0, bestType: '' }
  const orphanDomain = orphanNode._domain || ''; const orphanLevel = orphanNode.level || 3
  const sameDomainCandidates = candidates.filter(c => { const cDomain = c._domain || ''; if (!orphanDomain || !cDomain) return true; return cDomain === orphanDomain })
  if (sameDomainCandidates.length === 0 && orphanDomain) return { qualified: false, reason: `"${orphanNode.title}"（领域：${orphanDomain}）在当前分组内无同领域节点可收养`, bestCandidate: null, bestScore: 0, bestType: '' }
  const pool = sameDomainCandidates.length > 0 ? sameDomainCandidates : candidates
  const sameLevel = pool.filter(n => (n.level || 3) === orphanLevel)
  const upperLevel = pool.filter(n => (n.level || 3) === orphanLevel - 1)
  const lowerLevel = pool.filter(n => (n.level || 3) === orphanLevel + 1)
  let best = null; let bestScore = -1; let bestType = ''
  for (const c of sameLevel) { const bridge = getCrossDomainBridge(orphanNode, c); const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3; const score = sim * 0.6 + (bridge.hasBridge ? 0.4 : 0); if (score > bestScore) { bestScore = score; best = c; bestType = 'same_level' } }
  if (!best && upperLevel.length > 0) { for (const c of upperLevel) { const bridge = getCrossDomainBridge(orphanNode, c); const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3; const score = sim * 0.5 + (bridge.hasBridge ? 0.5 : 0); if (score > bestScore) { bestScore = score; best = c; bestType = 'upper_level' } } }
  if (!best && lowerLevel.length > 0) { for (const c of lowerLevel) { const bridge = getCrossDomainBridge(orphanNode, c); const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3; const score = sim * 0.5 + (bridge.hasBridge ? 0.5 : 0); if (score > bestScore) { bestScore = score; best = c; bestType = 'lower_level' } } }
  if (best && bestScore < 0.5) return { qualified: false, reason: `"${orphanNode.title}"与最佳候选"${best.title}"收养置信度 ${bestScore.toFixed(2)} < 0.5，不进行收养`, bestCandidate: null, bestScore: 0, bestType: '' }
  if (best) return { qualified: true, reason: '', bestCandidate: best, bestScore, bestType }
  return { qualified: false, reason: `"${orphanNode.title}"无合适收养节点`, bestCandidate: null, bestScore: 0, bestType: '' }
}

export function ensureNoOrphans(nodes, links) {
  if (nodes.length === 0) return { newLinks: [], adopted: 0, orphanCount: 0, warnings: [] }
  const activeNodes = nodes.filter(n => n.validate?.status !== 'discarded')
  const baseLinks = links.filter(l => !l.semantic_bridge)
  const { orphans, degreeMap } = detectOrphans(activeNodes, baseLinks)
  if (orphans.size === 0) return { newLinks: [], adopted: 0, orphanCount: 0, warnings: [] }
  const nodeMap = new Map(nodes.map(n => [n.id, n])); const newLinks = []; const warnings = []
  for (const oid of orphans) {
    const orphanNode = nodeMap.get(oid)
    if (!orphanNode) continue
    const blackList = new Set(orphanNode.isolateBlackList || [])
    const orphanLevel = orphanNode.level || 3
    const candidates = activeNodes.filter(n => { if (n.id === oid) return false; if (orphans.has(n.id)) return false; if (blackList.has(n.id)) return false; if (n.isolateBlackList?.includes(oid)) return false; return true })
    if (candidates.length === 0) { warnings.push(`"${orphanNode.title}"：当前分组内无可桥接节点（所有候选节点均在隔离黑名单中），请检查隔离设置`); continue }
    const adoption = qualifyAdoption(orphanNode, candidates)
    if (!adoption.qualified) { warnings.push(adoption.reason); continue }
    if (adoption.bestCandidate) newLinks.push(buildBridge(oid, adoption.bestCandidate.id, adoption.bestScore, adoption.bestType, orphanLevel, adoption.bestCandidate.level || 3))
  }
  return { newLinks, adopted: newLinks.length, orphanCount: orphans.size, warnings }
}

function buildBridge(source, target, score = 0, bridgeType = 'semantic', sourceLevel = 3, targetLevel = 3) {
  const evidenceMap = { same_level: '同层级节点桥接（相似知识点关联）', upper_level: '上层理论支撑（理论基础关联）', lower_level: '下层实现示例（实现关系关联）', fallback: '跨层级兜底桥接' }
  return { id: 'sb_' + source + '_' + target, source, target, weight: 0.3, score: 0.3, semantic_bridge: true, source_type: 'semantic_bridge', sources: ['semantic_bridge'], breakdown: { sim_text: 0, sim_vector: Math.max(0.3, score), sim_corpus: 0, sim_topology: 0 }, overlap_keywords: [], overlap_entities: [], evidence: evidenceMap[bridgeType] || '孤儿节点自动收养桥接', bridge_type: bridgeType, source_level: sourceLevel, target_level: targetLevel }
}

export function validateGraph(nodes, links) {
  const discardedIds = new Set(nodes.filter(n => n.validate?.status === 'discarded').map(n => n.id))
  const activeNodes = nodes.filter(n => n.validate?.status !== 'discarded')
  const seen = new Set(); const cleanedLinks = []; let selfLoopRemoved = 0; let dupRemoved = 0
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target
    if (discardedIds.has(s) || discardedIds.has(t)) continue
    if (s === t) { selfLoopRemoved++; continue }
    const k = s < t ? s + '|' + t : t + '|' + s
    if (seen.has(k)) { dupRemoved++; continue }
    seen.add(k); cleanedLinks.push(l)
  }
  const { newLinks, adopted, orphanCount, warnings } = ensureNoOrphans(activeNodes, cleanedLinks)
  const finalLinks = cleanedLinks.concat(newLinks)
  return { links: finalLinks, stats: { selfLoopRemoved, dupRemoved, orphanCount, adopted, finalLinkCount: finalLinks.length }, warnings }
}

const graphValidator = { computeDegree, pageRank, detectOrphans, ensureNoOrphans, validateGraph }
export default graphValidator
