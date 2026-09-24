/**
 * corpusMatcher.js 加载 software_kg.md 构建本体
 */
import softwareKgRaw from '../domain_corpus/software_kg.md?raw'

let _entities = null
let _aliasMap = null
let _relationPairs = null

function parseKg(md) {
  const lines = md.split('\n')
  const entities = new Map(); const aliasMap = new Map(); let cur = null
  const push = () => {
    if (!cur || !cur.name) return
    const key = cur.name.toLowerCase().trim()
    entities.set(key, { name: cur.name, aliases: cur.aliases || [], related: cur.related || [], bridge_sentence: cur.bridge_sentence || '', domain: cur.domain || '' })
    for (const a of cur.aliases) { const aKey = String(a).toLowerCase().trim(); if (aKey && !aliasMap.has(aKey)) aliasMap.set(aKey, key) }
    if (!aliasMap.has(key)) aliasMap.set(key, key)
    cur = null
  }
  for (let raw of lines) {
    const line = raw.trim()
    if (line.startsWith('## ')) { push(); cur = { name: line.substring(3).trim(), related: [], aliases: [], bridge_sentence: '', domain: '' } }
    else if (cur && line.startsWith('- related_entities:')) { cur.related = line.replace(/^-\s*related_entities:\s*\[?/, '').replace(/\]?$/, '').split(',').map(s => s.trim()).filter(Boolean) }
    else if (cur && line.startsWith('- bridge_sentence:')) cur.bridge_sentence = line.replace(/^-\s*bridge_sentence:\s*/, '')
    else if (cur && line.startsWith('- domain:')) cur.domain = line.replace(/^-\s*domain:\s*/, '')
    else if (cur && line.startsWith('- aliases:')) cur.aliases = line.replace(/^-\s*aliases:\s*\[?/, '').replace(/\]?$/, '').split(',').map(s => s.trim()).filter(Boolean)
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
      const a = k < rk ? k : rk; const b = k < rk ? rk : k
      pairs.set(a + '|' + b, { a, b, bridge: v.bridge_sentence, source_entity: v.name })
    }
  }
  return pairs
}

function ensureLoaded() {
  if (_entities) return
  const { entities, aliasMap } = parseKg(softwareKgRaw)
  _entities = entities; _aliasMap = aliasMap
  _relationPairs = buildRelations(entities, aliasMap)
  console.info('[corpusMatcher] ontology loaded: entities=' + _entities.size + ', relations=' + _relationPairs.size)
}

export function findEntitiesInText(text) {
  ensureLoaded()
  if (!text) return []
  const lower = text.toLowerCase(); const found = new Set()
  for (const [alias, key] of _aliasMap) { if (alias.length < 2) continue; if (lower.includes(alias)) found.add(key) }
  return [...found]
}

export function corpusMatch(aText, bText, aEntities = null, bEntities = null) {
  ensureLoaded()
  const eA = aEntities || findEntitiesInText(aText); const eB = bEntities || findEntitiesInText(bText)
  if (eA.length === 0 || eB.length === 0) return { score: 0, evidence: null, bridge_sentence: '', matched_entities: [] }
  let bridge = null; let maxHops = 0; let matched = []
  for (const ea of eA) {
    for (const eb of eB) {
      if (ea === eb) {
        const rec = _entities.get(ea); matched.push(ea)
        if (rec && rec.bridge_sentence) { bridge = { type: 'direct_same', a: ea, b: eb, sentence: rec.bridge_sentence, hops: 0, source_entity: rec.name }; maxHops = Math.max(maxHops, 1) }
        continue
      }
      const a = ea < eb ? ea : eb; const b = ea < eb ? eb : ea
      const rel = _relationPairs.get(a + '|' + b)
      if (rel) { matched.push(ea + '↔' + eb); if (!bridge || rel.hops > maxHops) { bridge = { type: 'related', a: ea, b: eb, sentence: rel.bridge, source_entity: rel.source_entity, hops: 1 }; maxHops = 1 } }
    }
  }
  if (maxHops === 0) {
    const neighborsA = new Set()
    for (const ea of eA) { const rec = _entities.get(ea); if (rec) for (const r of rec.related) { const rk = _aliasMap.get(String(r).toLowerCase().trim()) || String(r).toLowerCase().trim(); if (rk) neighborsA.add(rk) } }
    for (const eb of eB) { if (neighborsA.has(eb)) { matched.push('hop2:' + eb); if (!bridge) { const rec = _entities.get(eb); bridge = { type: 'two_hop', a: eA.join(','), b: eb, sentence: rec ? rec.bridge_sentence : '', source_entity: rec ? rec.name : '', hops: 2 }; maxHops = 2 } } }
  }
  const baseScore = maxHops > 0 ? 0.4 : 0
  const hopBonus = maxHops === 0 ? 0 : (maxHops === 1 ? 0.2 : 0.1)
  return { score: Math.min(1, baseScore + hopBonus), evidence: bridge, bridge_sentence: bridge ? bridge.sentence : '', matched_entities: matched.slice(0, 8) }
}

export function getOntologySnapshot() {
  ensureLoaded()
  return { entityCount: _entities.size, relationCount: _relationPairs.size, entities: [..._entities.values()] }
}

export function getEntityByName(name) {
  ensureLoaded()
  return _entities.get(String(name).toLowerCase().trim()) || null
}

export function getCrossDomainBridge(a, b) {
  ensureLoaded()
  const aText = (a.description || '') + ' ' + (a.entities || []).join(' ') + ' ' + (a.title || '')
  const bText = (b.description || '') + ' ' + (b.entities || []).join(' ') + ' ' + (b.title || '')
  const eA = findEntitiesInText(aText); const eB = findEntitiesInText(bText)
  if (eA.length === 0 || eB.length === 0) return { hasBridge: false, bridgeSentence: '', sourceEntity: '', domains: [] }
  const domainsA = new Set(); const domainsB = new Set()
  for (const ek of eA) { const ent = _entities.get(ek); if (ent?.domain) domainsA.add(ent.domain) }
  for (const ek of eB) { const ent = _entities.get(ek); if (ent?.domain) domainsB.add(ent.domain) }
  const isCrossDomain = (a._domain || '') !== (b._domain || '') || (domainsA.size > 0 && domainsB.size > 0 && ![...domainsA].some(d => domainsB.has(d)))
  let bridgeFound = null
  for (const ea of eA) {
    for (const eb of eB) {
      if (ea === eb) { const rec = _entities.get(ea); if (rec) bridgeFound = { bridgeSentence: rec.bridge_sentence || `${rec.name} 是跨领域通用概念`, sourceEntity: rec.name, domains: [rec.domain || ''] }; continue }
      const a = ea < eb ? ea : eb; const b = ea < eb ? eb : ea
      const rel = _relationPairs.get(a + '|' + b)
      if (rel) { const recA = _entities.get(ea); const recB = _entities.get(eb); bridgeFound = { bridgeSentence: rel.bridge || `${recA?.name || ea} 与 ${recB?.name || eb} 存在知识库桥接`, sourceEntity: rel.source_entity || '', domains: [recA?.domain || '', recB?.domain || ''].filter(Boolean) } }
    }
  }
  if (bridgeFound) return { hasBridge: true, bridgeSentence: bridgeFound.bridgeSentence, sourceEntity: bridgeFound.sourceEntity, domains: bridgeFound.domains }
  return { hasBridge: false, bridgeSentence: '', sourceEntity: '', domains: [...new Set([...domainsA, ...domainsB])] }
}

const corpusMatcher = { corpusMatch, findEntitiesInText, getOntologySnapshot, getEntityByName, getCrossDomainBridge, ensureLoaded }
export default corpusMatcher
