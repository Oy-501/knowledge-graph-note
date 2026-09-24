/**
 * graphValidator.js
 * 1) detectOrphans：检测 Degree=0 孤立节点
 * 2) pageRank：计算节点中心度，Top5
 * 3) ensureNoOrphans：孤儿收养机制 - 自动选取 Top5 中心度节点中语义相似度最高的，生成灰色虚线桥接连线
 *    固定语义桥接分 w2=0.3，标记 link.semantic_bridge=true
 */

import { cosine } from './vectorEngine'
import { getCrossDomainBridge } from './corpusMatcher'

/**
 * 计算节点度数
 */
export function computeDegree(node, links) {
  let d = 0
  for (const l of links) {
    if (l.source === node.id || l.target === node.id ||
        (l.source && l.source.id === node.id) ||
        (l.target && l.target.id === node.id)) d++
  }
  return d
}

/**
 * PageRank 算法
 * @param {Array} nodes
 * @param {Array} links
 * @param {{damping?:number, iterations?:number}} opts
 */
export function pageRank(nodes, links, opts = {}) {
  const damping = opts.damping ?? 0.85
  const iterations = opts.iterations ?? 30
  const N = nodes.length
  if (N === 0) return new Map()

  // 构建邻接
  const outLinks = new Map() // id -> Set<id>
  const inLinks = new Map()
  for (const n of nodes) {
    outLinks.set(n.id, new Set())
    inLinks.set(n.id, new Set())
  }
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (outLinks.has(s) && inLinks.has(t)) {
      outLinks.get(s).add(t)
      inLinks.get(t).add(s)
    }
  }
  let pr = new Map()
  for (const n of nodes) pr.set(n.id, 1 / N)
  for (let it = 0; it < iterations; it++) {
    const next = new Map()
    let dangling = 0
    for (const n of nodes) {
      if (outLinks.get(n.id).size === 0) dangling += pr.get(n.id)
    }
    for (const n of nodes) {
      let sum = 0
      for (const inId of inLinks.get(n.id)) {
        const outDeg = outLinks.get(inId).size
        if (outDeg > 0) sum += pr.get(inId) / outDeg
      }
      // 加入 dangling 节点的均匀分布
      sum += dangling / N
      next.set(n.id, (1 - damping) / N + damping * sum)
    }
    pr = next
  }
  return pr
}

/**
 * 检测孤立节点（degree === 0）
 * 跳过 validate.status === 'discarded' 的节点
 */
export function detectOrphans(nodes, links) {
  const orphanSet = new Set()
  const degreeMap = new Map()
  for (const n of nodes) degreeMap.set(n.id, 0)
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (degreeMap.has(s)) degreeMap.set(s, degreeMap.get(s) + 1)
    if (degreeMap.has(t)) degreeMap.set(t, degreeMap.get(t) + 1)
  }
  for (const n of nodes) {
    // 跳过已丢弃的节点
    if (n.validate?.status === 'discarded') continue
    if (degreeMap.get(n.id) === 0) orphanSet.add(n.id)
  }
  return { orphans: orphanSet, degreeMap }
}

/**
 * 孤儿收养资格审查（阶段3：该不该救）
 * 孤儿节点只有满足以下条件才会被收养：
 *   1. 孤儿节点本身必须通过知识点资格审核（stage1 通过）
 *   2. 当前分组内至少有一个同领域节点
 *   3. 优先找同层级，其次上下层级
 *   4. 与收养目标在知识库中有桥接句
 *   5. 收养连线置信度 ≥ 0.5
 * 不满足以上任一条件 → 不生成收养连线，仅在 UI 中提示
 *
 * @param {Object} orphanNode - 孤儿节点
 * @param {Array} candidates - 候选收养节点
 * @returns {{qualified: boolean, reason: string, bestCandidate: Object|null, bestScore: number, bestType: string}}
 */
function qualifyAdoption(orphanNode, candidates) {
  // 条件1：孤儿节点必须通过知识点资格审核
  const quality = orphanNode._quality
  if (quality && !quality.qualified) {
    return { qualified: false, reason: `知识点"${orphanNode.title}"未通过资格审核（${quality.reason}），不进行收养`,
      bestCandidate: null, bestScore: 0, bestType: '' }
  }

  if (candidates.length === 0) {
    return { qualified: false, reason: `"${orphanNode.title}"无候选节点可收养`,
      bestCandidate: null, bestScore: 0, bestType: '' }
  }

  const orphanDomain = orphanNode._domain || ''
  const orphanLevel = orphanNode.level || 3

  // 条件2：过滤同领域候选节点
  const sameDomainCandidates = candidates.filter(c => {
    const cDomain = c._domain || ''
    if (!orphanDomain || !cDomain) return true // 如果一方无领域信息，不排除
    return cDomain === orphanDomain
  })

  if (sameDomainCandidates.length === 0 && orphanDomain) {
    return { qualified: false, reason: `"${orphanNode.title}"（领域：${orphanDomain}）在当前分组内无同领域节点可收养`,
      bestCandidate: null, bestScore: 0, bestType: '' }
  }

  const pool = sameDomainCandidates.length > 0 ? sameDomainCandidates : candidates

  // 按层级分组
  const sameLevel = pool.filter(n => (n.level || 3) === orphanLevel)
  const upperLevel = pool.filter(n => (n.level || 3) === orphanLevel - 1)
  const lowerLevel = pool.filter(n => (n.level || 3) === orphanLevel + 1)

  let best = null
  let bestScore = -1
  let bestType = ''

  // 优先级1: 同层级 + 知识库桥接
  for (const c of sameLevel) {
    const bridge = getCrossDomainBridge(orphanNode, c)
    const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3
    // 综合得分 = 语义相似度 * 0.6 + 桥接 * 0.4
    const score = sim * 0.6 + (bridge.hasBridge ? 0.4 : 0)
    if (score > bestScore) { bestScore = score; best = c; bestType = 'same_level' }
  }

  // 优先级2: 上一层 + 知识库桥接
  if (!best && upperLevel.length > 0) {
    for (const c of upperLevel) {
      const bridge = getCrossDomainBridge(orphanNode, c)
      const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3
      const score = sim * 0.5 + (bridge.hasBridge ? 0.5 : 0)
      if (score > bestScore) { bestScore = score; best = c; bestType = 'upper_level' }
    }
  }

  // 优先级3: 下一层 + 知识库桥接
  if (!best && lowerLevel.length > 0) {
    for (const c of lowerLevel) {
      const bridge = getCrossDomainBridge(orphanNode, c)
      const sim = orphanNode.vector && c.vector ? cosine(orphanNode.vector, c.vector) : 0.3
      const score = sim * 0.5 + (bridge.hasBridge ? 0.5 : 0)
      if (score > bestScore) { bestScore = score; best = c; bestType = 'lower_level' }
    }
  }

  // 条件5：置信度 ≥ 0.5
  if (best && bestScore < 0.5) {
    return { qualified: false, reason: `"${orphanNode.title}"与最佳候选"${best.title}"收养置信度 ${bestScore.toFixed(2)} < 0.5，不进行收养`,
      bestCandidate: null, bestScore: 0, bestType: '' }
  }

  if (best) {
    return { qualified: true, reason: '',
      bestCandidate: best, bestScore, bestType }
  }

  return { qualified: false, reason: `"${orphanNode.title}"无合适收养节点`,
    bestCandidate: null, bestScore: 0, bestType: '' }
}

/**
 * 孤儿收养机制（升级版：资格审核 + 同领域 + 同层级 + 知识桥接 + 置信度）
 * 给每个孤立节点按层级优先级匹配桥接节点：
 *  1. 通过资格审核
 *  2. 找同领域节点
 *  3. 优先找同层级节点（comparison）
 *  4. 其次找上一层（theory，理论支撑）
 *  5. 最后找下一层（implementation，实现示例）
 *  6. 需要知识库桥接
 *  7. 置信度 ≥ 0.5
 *  8. 以上均不满足 → 记录警告，不生成收养连线
 *
 * @param {Array} nodes 全部节点
 * @param {Array} links 全部连线
 * @returns {{newLinks:Array, adopted:number, orphanCount:number, warnings:string[]}}
 */
export function ensureNoOrphans(nodes, links) {
  if (nodes.length === 0) return { newLinks: [], adopted: 0, orphanCount: 0, warnings: [] }

  // 过滤掉已丢弃的节点
  const activeNodes = nodes.filter(n => n.validate?.status !== 'discarded')

  // 第一步：剔除已是 semantic_bridge 的孤儿收养连线，避免堆叠
  const baseLinks = links.filter(l => !l.semantic_bridge)

  const { orphans, degreeMap } = detectOrphans(activeNodes, baseLinks)
  if (orphans.size === 0) {
    return { newLinks: [], adopted: 0, orphanCount: 0, warnings: [] }
  }

  const nodeMap = new Map(nodes.map(n => [n.id, n]))
  const newLinks = []
  const warnings = []

  for (const oid of orphans) {
    const orphanNode = nodeMap.get(oid)
    if (!orphanNode) continue

    const blackList = new Set(orphanNode.isolateBlackList || [])
    const orphanLevel = orphanNode.level || 3

    // 过滤掉黑名单和已丢弃的候选节点
    const candidates = activeNodes.filter(n => {
      if (n.id === oid) return false
      if (orphans.has(n.id)) return false
      if (blackList.has(n.id)) return false
      if (n.isolateBlackList?.includes(oid)) return false
      return true
    })

    if (candidates.length === 0) {
      warnings.push(`"${orphanNode.title}"：当前分组内无可桥接节点（所有候选节点均在隔离黑名单中），请检查隔离设置`)
      continue
    }

    // 阶段3：孤儿收养资格审查
    const adoption = qualifyAdoption(orphanNode, candidates)
    if (!adoption.qualified) {
      warnings.push(adoption.reason)
      continue
    }

    if (adoption.bestCandidate) {
      newLinks.push(buildBridge(oid, adoption.bestCandidate.id, adoption.bestScore, adoption.bestType, orphanLevel, adoption.bestCandidate.level || 3))
    }
  }

  return { newLinks, adopted: newLinks.length, orphanCount: orphans.size, warnings }
}

function buildBridge(source, target, score = 0, bridgeType = 'semantic', sourceLevel = 3, targetLevel = 3) {
  const evidenceMap = {
    same_level: '同层级节点桥接（相似知识点关联）',
    upper_level: '上层理论支撑（理论基础关联）',
    lower_level: '下层实现示例（实现关系关联）',
    fallback: '跨层级兜底桥接'
  }

  return {
    id: 'sb_' + source + '_' + target,
    source,
    target,
    weight: 0.3,
    score: 0.3,
    semantic_bridge: true,
    source_type: 'semantic_bridge',
    sources: ['semantic_bridge'],
    breakdown: {
      sim_text: 0,
      sim_vector: Math.max(0.3, score),
      sim_corpus: 0,
      sim_topology: 0
    },
    overlap_keywords: [],
    overlap_entities: [],
    evidence: evidenceMap[bridgeType] || '孤儿节点自动收养桥接',
    bridge_type: bridgeType,
    source_level: sourceLevel,
    target_level: targetLevel
  }
}

/**
 * 图谱合法性校验
 * 1) 无自环
 * 2) 无重复边
 * 3) 无孤立节点（跳过 discarded 节点，若存在，调 ensureNoOrphans 自动收养）
 */
export function validateGraph(nodes, links) {
  // 过滤掉已丢弃节点的连线
  const discardedIds = new Set(nodes.filter(n => n.validate?.status === 'discarded').map(n => n.id))
  const activeNodes = nodes.filter(n => n.validate?.status !== 'discarded')

  const seen = new Set()
  const cleanedLinks = []
  let selfLoopRemoved = 0
  let dupRemoved = 0
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    // 跳过涉及已丢弃节点的连线
    if (discardedIds.has(s) || discardedIds.has(t)) continue
    if (s === t) {
      selfLoopRemoved++
      continue
    }
    const k = s < t ? s + '|' + t : t + '|' + s
    if (seen.has(k)) {
      dupRemoved++
      continue
    }
    seen.add(k)
    cleanedLinks.push(l)
  }
  const { newLinks, adopted, orphanCount, warnings } = ensureNoOrphans(activeNodes, cleanedLinks)
  const finalLinks = cleanedLinks.concat(newLinks)
  return {
    links: finalLinks,
    stats: {
      selfLoopRemoved, dupRemoved, orphanCount, adopted, finalLinkCount: finalLinks.length
    },
    warnings
  }
}

const graphValidator = {
  computeDegree, pageRank, detectOrphans, ensureNoOrphans, validateGraph
}
export default graphValidator
