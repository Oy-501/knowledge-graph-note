/**
 * knowledgeConsistency.js
 * 知识一致性检查引擎
 *
 * 功能：
 *  - 跨笔记一致性：不同笔记中的同一知识点是否存在矛盾
 *  - 知识演进检查：某知识点是否有更新的版本/标准
 *  - 关联合理性：笔记与知识点的关联关系是否仍然合理
 *  - 引用有效性：笔记中引用的外部知识是否仍然有效
 *  - 知识冗余检查：是否有大量笔记重复描述同一知识点
 */

import { getOntologySnapshot, findEntitiesInText } from './corpusMatcher'
import { deepValidation, checkConflict, textOverlap } from './noteValidator'

// ==================== 一致性检查结果类型 ====================

export const CONSISTENCY_RESULT = {
  CONSISTENT: 'consistent',       // 一致
  POTENTIAL_CONFLICT: 'potential', // 潜在冲突
  CONFLICT: 'conflict',           // 明确冲突
  NEEDS_REVIEW: 'needs_review',   // 需要人工审查
  UNKNOWN: 'unknown'              // 无法判断
}

// ==================== 知识演进映射表 ====================

const KNOWLEDGE_EVOLUTION = [
  {
    old: 'Java EE',
    new: 'Jakarta EE',
    since: '2018',
    reason: 'Oracle 将 Java EE 移交 Eclipse 基金会后更名为 Jakarta EE'
  },
  {
    old: 'Java 8',
    new: 'Java 21 (LTS)',
    since: '2023',
    reason: 'Java 8 免费支持已结束，建议升级到 Java 17/21 LTS'
  },
  {
    old: 'Python 2',
    new: 'Python 3.12+',
    since: '2020',
    reason: 'Python 2 已于 2020 年停止维护'
  },
  {
    old: 'React class component',
    new: 'React hooks (functional component)',
    since: '2019',
    reason: 'React 推荐使用 hooks 替代 class component'
  },
  {
    old: 'Vue 2',
    new: 'Vue 3 (Composition API)',
    since: '2020',
    reason: 'Vue 3 引入 Composition API，Vue 2 于 2023 年底停止维护'
  },
  {
    old: 'Docker Swarm',
    new: 'Kubernetes',
    since: '2019',
    reason: 'Kubernetes 已成为容器编排的事实标准'
  },
  {
    old: 'REST API',
    new: 'GraphQL / gRPC',
    since: '2020',
    reason: '新兴 API 范式提供了更灵活的数据获取方式'
  },
  {
    old: 'jQuery',
    new: '原生 JS / React / Vue',
    since: '2018',
    reason: '现代框架已取代 jQuery 的大部分功能'
  },
  {
    old: 'MySQL 5.x',
    new: 'MySQL 8.0+',
    since: '2018',
    reason: 'MySQL 8.0 引入窗口函数、CTE 等重要特性'
  },
  {
    old: 'SSL',
    new: 'TLS',
    since: '2015',
    reason: 'SSL 已被 TLS 取代，应使用 TLS 1.2+'
  },
  {
    old: 'Ant Design 4',
    new: 'Ant Design 5',
    since: '2022',
    reason: 'Ant Design 5 引入 CSS-in-JS 主题系统'
  }
]

// ==================== 一致性检查引擎 ====================

export class ConsistencyChecker {
  constructor() {
    this._ontology = null
  }

  _getOntology() {
    if (!this._ontology) {
      this._ontology = getOntologySnapshot()
    }
    return this._ontology
  }

  /**
   * 跨笔记一致性检查
   * @param {Array} nodes - 所有知识节点
   * @returns {Object} 报告
   */
  checkCrossNotes(nodes) {
    const report = {
      conflicts: [],
      suggestions: [],
      timestamp: Date.now()
    }

    if (!nodes || nodes.length < 2) return report

    // 按 title 分组
    const byTitle = new Map()
    for (const node of nodes) {
      if (node.validate?.status === 'discarded') continue
      const key = (node.title || '').toLowerCase().trim()
      if (!key) continue
      if (!byTitle.has(key)) byTitle.set(key, [])
      byTitle.get(key).push(node)
    }

    // 检查每个分组内是否有矛盾
    for (const [key, group] of byTitle) {
      if (group.length < 2) continue
      for (let i = 0; i < group.length; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const result = this._compareNodes(group[i], group[j])
          if (result.status === CONSISTENCY_RESULT.CONFLICT
              || result.status === CONSISTENCY_RESULT.POTENTIAL_CONFLICT) {
            report.conflicts.push({
              nodeA: group[i].id,
              nodeB: group[j].id,
              title: group[i].title,
              status: result.status,
              reason: result.reason,
              suggestion: result.suggestion
            })
          }
        }
      }
    }

    return report
  }

  /**
   * 知识演进检查
   * @param {Array} nodes - 所有节点
   * @returns {Array} 过时知识列表
   */
  checkEvolution(nodes) {
    const outdated = []
    if (!nodes) return outdated

    for (const node of nodes) {
      if (node.validate?.status === 'discarded') continue
      const text = ((node.title || '') + ' ' + (node.description || '')).toLowerCase()

      for (const evo of KNOWLEDGE_EVOLUTION) {
        if (text.includes(evo.old.toLowerCase())) {
          // 检查是否已经提到了新版本
          if (!text.includes(evo.new.toLowerCase())) {
            outdated.push({
              nodeId: node.id,
              title: node.title,
              old: evo.old,
              replacement: evo.new,
              since: evo.since,
              reason: evo.reason
            })
          }
        }
      }
    }

    return outdated
  }

  /**
   * 知识冗余检查
   * @param {Array} nodes - 所有节点
   * @returns {Array} 冗余节点对
   */
  checkRedundancy(nodes) {
    const redundant = []
    if (!nodes || nodes.length < 2) return redundant

    for (let i = 0; i < nodes.length; i++) {
      if (nodes[i].validate?.status === 'discarded') continue
      for (let j = i + 1; j < nodes.length; j++) {
        if (nodes[j].validate?.status === 'discarded') continue
        const textA = ((nodes[i].title || '') + ' ' + (nodes[i].description || '')).toLowerCase()
        const textB = ((nodes[j].title || '') + ' ' + (nodes[j].description || '')).toLowerCase()
        const similarity = textOverlap(textA, textB)
        if (similarity > 0.8) {
          redundant.push({
            nodeA: nodes[i].id,
            nodeB: nodes[j].id,
            titleA: nodes[i].title,
            titleB: nodes[j].title,
            similarity: Math.round(similarity * 100),
            suggestion: similarity > 0.95
              ? '几乎完全相同，建议合并'
              : '高度相似，建议区分内容或合并'
          })
        }
      }
    }

    return redundant
  }

  /**
   * 关联合理性检查
   * @param {Array} links - 所有连线
   * @param {Array} nodes - 所有节点
   * @returns {Array} 可疑关联
   */
  checkRelationValidity(links, nodes) {
    const suspicious = []
    if (!links || !nodes) return suspicious

    const nodeMap = new Map()
    for (const n of nodes) nodeMap.set(n.id, n)

    for (const link of links) {
      const sId = typeof link.source === 'object' ? link.source.id : link.source
      const tId = typeof link.target === 'object' ? link.target.id : link.target
      const source = nodeMap.get(sId)
      const target = nodeMap.get(tId)
      if (!source || !target) continue

      // 检查层级差 > 2 的关系
      const levelDiff = Math.abs((source.level || 3) - (target.level || 3))
      if (levelDiff > 2 && link.relation_type !== 'related') {
        suspicious.push({
          linkId: link.id,
          source: source.title,
          target: target.title,
          reason: `层级差为 ${levelDiff}（${source.level}→${target.level}），关系可能不合理`,
          suggestion: '请确认是否存在明确的桥接句'
        })
      }

      // 检查证据强度为弱或无的关联
      if (link.evidence_level === 'weak' || link.evidence_level === 'none') {
        suspicious.push({
          linkId: link.id,
          source: source.title,
          target: target.title,
          reason: `证据强度为"${link.evidence_level}"，关联可能不可靠`,
          suggestion: '建议补充更多证据或移除该关联'
        })
      }
    }

    return suspicious
  }

  /**
   * 综合一致性报告
   */
  generateReport(nodes, links) {
    return {
      generatedAt: Date.now(),
      crossNotes: this.checkCrossNotes(nodes),
      evolution: this.checkEvolution(nodes),
      redundancy: this.checkRedundancy(nodes),
      relationValidity: this.checkRelationValidity(links, nodes),
      summary: {
        conflicts: this.checkCrossNotes(nodes).conflicts.length,
        outdated: this.checkEvolution(nodes).length,
        redundant: this.checkRedundancy(nodes).length,
        suspiciousRelations: this.checkRelationValidity(links, nodes).length
      }
    }
  }

  _compareNodes(a, b) {
    const textA = (a.description || a.title || '').toLowerCase()
    const textB = (b.description || b.title || '').toLowerCase()

    // 矛盾判定统一走 noteValidator 的 checkConflict（反义词表以 noteValidator 为准）
    const conflicts = checkConflict(textA, textB, a.title, b.title)
    if (!conflicts.length) {
      return { status: CONSISTENCY_RESULT.CONSISTENT, reason: '', suggestion: '' }
    }
    return {
      status: CONSISTENCY_RESULT.CONFLICT,
      reason: conflicts[0].reason,
      suggestion: `源文件A: ${a.fileId || '未知'}，源文件B: ${b.fileId || '未知'}，请核实正确表述`
    }
  }
}