/**
 * corpusMatcher.js
 * 加载 /src/domain_corpus/software_kg.md，在内存构建本体：
 *  - entities: Map<name_lower, {name, aliases, related, bridge_sentence, domain}>
 *  - relations: Map<key_a|key_b, true>  (双向桥接)
 * 提供 corpusMatch(a_text, b_text) -> {score, evidence, bridge_sentence, matched_entities[]}
 */

import softwareKgRaw from '../domain_corpus/software_kg.md?raw'

let _entities = null
let _aliasMap = null
let _relationPairs = null

function parseKg(md) {
  const lines = md.split('\n')
  const entities = new Map()
  const aliasMap = new Map()
  let cur = null
  const push = () => {
    if (!cur || !cur.name) return
      const key = cur.name.toLowerCase().trim()
      const rec = {
        name: cur.name,
        aliases: cur.aliases || [],
        related: cur.related || [],
        bridge_sentence: cur.bridge_sentence || '',
        domain: cur.domain || ''
      }
      entities.set(key, rec)
      // 别名映射
      for (const a of rec.aliases) {
        const aKey = String(a).toLowerCase().trim()
        if (aKey && !aliasMap.has(aKey)) aliasMap.set(aKey, key)
      }
      if (!aliasMap.has(key)) aliasMap.set(key, key)
      cur = null
  }
  for (let raw of lines) {
    const line = raw.trim()
    if (line.startsWith('## ')) {
      push()
      cur = { name: line.substring(3).trim(), related: [], aliases: [], bridge_sentence: '', domain: '' }
    } else if (cur && line.startsWith('- related_entities:')) {
      const arr = line.replace(/^-\s*related_entities:\s*\[?/, '').replace(/\]?$/, '').split(',').map(s => s.trim()).filter(Boolean)
      cur.related = arr
    } else if (cur && line.startsWith('- bridge_sentence:')) {
      cur.bridge_sentence = line.replace(/^-\s*bridge_sentence:\s*/, '')
    } else if (cur && line.startsWith('- domain:')) {
      cur.domain = line.replace(/^-\s*domain:\s*/, '')
    } else if (cur && line.startsWith('- aliases:')) {
      cur.aliases = line.replace(/^-\s*aliases:\s*\[?/, '').replace(/\]?$/, '').split(',').map(s => s.trim()).filter(Boolean)
    }
  }
  push()
  return { entities, aliasMap }
}

function buildRelations(entities, aliasMap) {
  const pairs = new Map()
  for (const [k, v] of entities) {
    for (const r of v.related) {
      const rk = (aliasMap.get(String(r).toLowerCase().trim()) || String(r).toLowerCase().trim())
      if (!rk) continue
      const a = k < rk ? k : rk
      const b = k < rk ? rk : k
      const key = a + '|' + b
      pairs.set(key, { a, b, bridge: v.bridge_sentence, source_entity: v.name })
    }
  }
  return pairs
}

function ensureLoaded() {
  if (_entities) return
  const { entities, aliasMap } = parseKg(softwareKgRaw)
  _entities = entities
  _aliasMap = aliasMap
  _relationPairs = buildRelations(entities, aliasMap)
  console.info('[corpusMatcher] ontology loaded: entities=' + _entities.size + ', relations=' + _relationPairs.size)
}

/**
 * 在文本中匹配本体的实体名/别名
 * @param {string} text
 * @returns {string[]} 实体 key 数组
 */
export function findEntitiesInText(text) {
  ensureLoaded()
  if (!text) return []
  const lower = text.toLowerCase()
  const found = new Set()
  for (const [alias, key] of _aliasMap) {
    if (alias.length < 2) continue
    if (lower.includes(alias)) {
      found.add(key)
    }
  }
  return [...found]
}

/**
 * 计算两段文本通过知识库桥接的得分
 * 固定规则：若文本 A 与文本 B 各自命中本体实体，且命中实体之间存在本体桥接，叠加 0.4 基础分
 * @returns {{score:number, evidence:object, bridge_sentence?:string, matched_entities:string[]}}
 */
export function corpusMatch(aText, bText, aEntities = null, bEntities = null) {
  ensureLoaded()
  const eA = aEntities || findEntitiesInText(aText)
  const eB = bEntities || findEntitiesInText(bText)
  if (eA.length === 0 || eB.length === 0) {
    return { score: 0, evidence: null, bridge_sentence: '', matched_entities: [] }
  }
  let bridge = null
  let maxHops = 0
  let matched = []
  for (const ea of eA) {
    for (const eb of eB) {
      if (ea === eb) {
        // 直接同一实体：强桥接
        const rec = _entities.get(ea)
        matched.push(ea)
        if (rec && rec.bridge_sentence) {
          bridge = { type: 'direct_same', a: ea, b: eb, sentence: rec.bridge_sentence, hops: 0, source_entity: rec.name }
          maxHops = Math.max(maxHops, 1)
        }
        continue
      }
      const a = ea < eb ? ea : eb
      const b = ea < eb ? eb : ea
      const rel = _relationPairs.get(a + '|' + b)
      if (rel) {
        matched.push(ea + '↔' + eb)
        if (!bridge || rel.hops > maxHops) {
          bridge = { type: 'related', a: ea, b: eb, sentence: rel.bridge, source_entity: rel.source_entity, hops: 1 }
          maxHops = 1
        }
      }
    }
  }
  if (maxHops === 0) {
    // 尝试二跳桥接：A 的邻居与 B 的邻居有交集
    const neighborsA = new Set()
    for (const ea of eA) {
      const rec = _entities.get(ea)
      if (rec) for (const r of rec.related) {
        const rk = _aliasMap.get(String(r).toLowerCase().trim()) || String(r).toLowerCase().trim()
        if (rk) neighborsA.add(rk)
      }
    }
    for (const eb of eB) {
      if (neighborsA.has(eb)) {
        matched.push('hop2:' + eb)
        if (!bridge) {
          const rec = _entities.get(eb)
          bridge = { type: 'two_hop', a: eA.join(','), b: eb, sentence: rec ? rec.bridge_sentence : '', source_entity: rec ? rec.name : '', hops: 2 }
          maxHops = 2
        }
      }
    }
  }

  // 固定 0.4 基础分 + hops 加权
  const baseScore = maxHops > 0 ? 0.4 : 0
  const hopBonus = maxHops === 0 ? 0 : (maxHops === 1 ? 0.2 : 0.1)
  const score = baseScore + hopBonus
  return {
    score: Math.min(1, score),
    evidence: bridge,
    bridge_sentence: bridge ? bridge.sentence : '',
    matched_entities: matched.slice(0, 8)
  }
}

export function getOntologySnapshot() {
  ensureLoaded()
  return {
    entityCount: _entities.size,
    relationCount: _relationPairs.size,
    entities: [..._entities.values()]
  }
}

export function getEntityByName(name) {
  ensureLoaded()
  const key = String(name).toLowerCase().trim()
  return _entities.get(key) || null
}

/**
 * 跨领域桥接判断
 * 检查两个节点是否在知识库中存在跨领域桥接关系
 * @param {Object} a - 节点A
 * @param {Object} b - 节点B
 * @returns {{hasBridge: boolean, bridgeSentence: string, sourceEntity: string, domains: string[]}}
 */
export function getCrossDomainBridge(a, b) {
  ensureLoaded()

  const aText = (a.description || '') + ' ' + (a.entities || []).join(' ') + ' ' + (a.title || '')
  const bText = (b.description || '') + ' ' + (b.entities || []).join(' ') + ' ' + (b.title || '')

  const eA = findEntitiesInText(aText)
  const eB = findEntitiesInText(bText)

  if (eA.length === 0 || eB.length === 0) {
    return { hasBridge: false, bridgeSentence: '', sourceEntity: '', domains: [] }
  }

  const aDomain = a._domain || ''
  const bDomain = b._domain || ''

  // 获取A和B各自命中实体的领域
  const domainsA = new Set()
  const domainsB = new Set()
  for (const ek of eA) {
    const ent = _entities.get(ek)
    if (ent?.domain) domainsA.add(ent.domain)
  }
  for (const ek of eB) {
    const ent = _entities.get(ek)
    if (ent?.domain) domainsB.add(ent.domain)
  }

  // 同领域 → 不是跨领域
  const isCrossDomain = aDomain !== bDomain ||
    (domainsA.size > 0 && domainsB.size > 0 &&
     ![...domainsA].some(d => domainsB.has(d)))

  // 检查知识库中是否有桥接
  let bridgeFound = null
  for (const ea of eA) {
    for (const eb of eB) {
      if (ea === eb) {
        // 同一实体跨领域出现
        const rec = _entities.get(ea)
        if (rec) {
          bridgeFound = {
            bridgeSentence: rec.bridge_sentence || `${rec.name} 是跨领域通用概念`,
            sourceEntity: rec.name,
            domains: [rec.domain || '']
          }
        }
        continue
      }
      const a = ea < eb ? ea : eb
      const b = ea < eb ? eb : ea
      const rel = _relationPairs.get(a + '|' + b)
      if (rel) {
        const recA = _entities.get(ea)
        const recB = _entities.get(eb)
        bridgeFound = {
          bridgeSentence: rel.bridge || `${recA?.name || ea} 与 ${recB?.name || eb} 存在知识库桥接`,
          sourceEntity: rel.source_entity || '',
          domains: [recA?.domain || '', recB?.domain || ''].filter(Boolean)
        }
      }
    }
  }

  if (bridgeFound) {
    return {
      hasBridge: true,
      bridgeSentence: bridgeFound.bridgeSentence,
      sourceEntity: bridgeFound.sourceEntity,
      domains: bridgeFound.domains
    }
  }

  return {
    hasBridge: false,
    bridgeSentence: '',
    sourceEntity: '',
    domains: [...new Set([...domainsA, ...domainsB])]
  }
}

const corpusMatcher = {
  corpusMatch, findEntitiesInText, getOntologySnapshot, getEntityByName,
  getCrossDomainBridge, ensureLoaded
}
export default corpusMatcher
