/**
 * relationClassifier.js 关系类型分类器
 */
export const RELATION_TYPES = {
  prerequisite: { code: 'prerequisite', label: '前置知识', color: '#6dd48a', icon: '➡️', symbol: '→', lineStyle: 'solid' },
  implementation: { code: 'implementation', label: '实现关系', color: '#7eb0ff', icon: '⬇️', symbol: '▷', lineStyle: 'dashed' },
  theory: { code: 'theory', label: '理论基础', color: '#a78bfa', icon: '🔗', symbol: '⊃', lineStyle: 'dotted' },
  comparison: { code: 'comparison', label: '对比关系', color: '#f5b462', icon: '↔️', symbol: '↔', lineStyle: 'double' },
  application: { code: 'application', label: '应用场景', color: '#4ec9b0', icon: '📍', symbol: '▸', lineStyle: 'dotted' },
  extension: { code: 'extension', label: '扩展延伸', color: '#c586c0', icon: '↗️', symbol: '↗', lineStyle: 'dashed' },
  contradiction: { code: 'contradiction', label: '矛盾/争议', color: '#f87086', icon: '⛔', symbol: '✕', lineStyle: 'red-block' },
  evolution: { code: 'evolution', label: '演进关系', color: '#569cd6', icon: '➜', symbol: '➜', lineStyle: 'dashed' },
  equivalent: { code: 'equivalent', label: '等价知识点', color: '#c8a2c8', icon: '≡', symbol: '≡', lineStyle: 'solid' },
  bridged: { code: 'bridged', label: '知识库桥接', color: '#7cb8a0', icon: '🌉', symbol: '⌒', lineStyle: 'dotted' },
  related: { code: 'related', label: '弱关联', color: '#8a93b0', icon: '~', symbol: '~', lineStyle: 'solid' }
}

const VERB_TO_RELATION = {
  '先学': 'prerequisite', '基础': 'prerequisite', '前提': 'prerequisite', '必要条件': 'prerequisite', '预备知识': 'prerequisite', '前置': 'prerequisite', '需要先': 'prerequisite', '必须先': 'prerequisite', '在...之前': 'prerequisite', 'prerequisite': 'prerequisite', 'foundation': 'prerequisite', 'fundamental': 'prerequisite', 'required': 'prerequisite',
  '实现': 'implementation', '实例化': 'implementation', '具体化': 'implementation', '实现为': 'implementation', '具体实现': 'implementation', '用...实现': 'implementation', 'implement': 'implementation', 'instantiate': 'implementation', 'realize': 'implementation', 'concrete': 'implementation',
  '基于': 'theory', '依据': 'theory', '根据': 'theory', '理论': 'theory', '支撑': 'theory', '原理': 'theory', '建立在': 'theory', '推导': 'theory', '源于': 'theory', 'based on': 'theory', 'theoretical': 'theory', 'foundation of': 'theory',
  '相比': 'comparison', '对比': 'comparison', '不同': 'comparison', '区别': 'comparison', '相同': 'comparison', '类似': 'comparison', '差异': 'comparison', '相较于': 'comparison', '与...不同': 'comparison', 'compare': 'comparison', 'versus': 'comparison', 'vs': 'comparison', 'difference': 'comparison', 'similar': 'comparison',
  '应用于': 'application', '用于': 'application', '场景': 'application', '案例': 'application', '实践中': 'application', '实际应用': 'application', '在...中使用': 'application', '应用在': 'application', 'apply': 'application', 'use case': 'application', 'scenario': 'application',
  '扩展': 'extension', '延伸': 'extension', '升级': 'extension', '改进': 'extension', '变体': 'extension', '衍生': 'extension', '增强版': 'extension', '在此基础上': 'extension', 'extend': 'extension', 'enhance': 'extension', 'variant': 'extension',
  '矛盾': 'contradiction', '冲突': 'contradiction', '争议': 'contradiction', '相反': 'contradiction', '对立': 'contradiction', '不兼容': 'contradiction', 'contradict': 'contradiction', 'conflict': 'contradiction', 'incompatible': 'contradiction', 'oppose': 'contradiction',
  '演进': 'evolution', '替代': 'evolution', '取代': 'evolution', '演变': 'evolution', '发展': 'evolution', '进化': 'evolution', '迭代': 'evolution', '下一代': 'evolution', 'evolve': 'evolution', 'replace': 'evolution', 'successor': 'evolution',
  '包含': 'theory', '包括': 'theory', '涵盖': 'theory', '属于': 'related', '是': 'related', '分为': 'related', '组成': 'related', '构成': 'related', '是一种': 'related', '的一类': 'related', '的一种': 'related', 'contain': 'related', 'include': 'related', 'consist': 'related', 'is a': 'related', 'is an': 'related', 'type of': 'related', 'kind of': 'related',
  '依赖': 'prerequisite', '依靠': 'prerequisite', '调用': 'implementation', '需要': 'prerequisite', '使用': 'implementation', '借助': 'implementation', '利用': 'implementation', '通过': 'implementation', 'depends': 'prerequisite', 'rely': 'prerequisite', 'require': 'prerequisite', 'use': 'implementation', 'call': 'implementation', 'invoke': 'implementation', '例如': 'implementation', '比如': 'implementation',
  '类比': 'comparison', '如同': 'comparison', '像': 'comparison', '相似': 'comparison', '对应': 'comparison', 'analog': 'comparison', 'like': 'comparison', 'correspond': 'comparison', 'resemble': 'comparison',
  '即': 'related', '也就是': 'related', '又称': 'related', '也叫': 'related', '等同于': 'related', '等价': 'related', '同义': 'related', 'also known as': 'related', 'aka': 'related', 'equivalent': 'related', 'alias': 'related'
}

function analyzeVerbRelation(sentence, entityA, entityB) {
  if (!sentence || !entityA || !entityB) return null
  const lower = sentence.toLowerCase(); const aLower = (entityA || '').toLowerCase(); const bLower = (entityB || '').toLowerCase()
  const aInSentence = lower.includes(aLower) || (entityA.length >= 3 && lower.includes(entityA.slice(0, 3)))
  const bInSentence = lower.includes(bLower) || (entityB.length >= 3 && lower.includes(entityB.slice(0, 3)))
  if (!aInSentence && !bInSentence) return null
  let bestMatch = null; let bestLen = 0
  for (const [verb, relType] of Object.entries(VERB_TO_RELATION)) {
    const idx = lower.indexOf(verb.toLowerCase())
    if (idx !== -1 && verb.length > bestLen) { bestMatch = { type: relType, verb, confidence: Math.min(1, verb.length / 5) }; bestLen = verb.length }
  }
  return bestMatch
}

function analyzeCooccurrence(rawTextA, rawTextB, entityA, entityB) {
  if (!rawTextA || !rawTextB) return null
  const sentencesA = (rawTextA || '').split(/[。！？\n.;!?]+/); const sentencesB = (rawTextB || '').split(/[。！？\n.;!?]+/)
  const aLower = (entityA || '').toLowerCase(); const bLower = (entityB || '').toLowerCase()
  for (const sent of sentencesA) {
    const lower = sent.toLowerCase()
    if ((lower.includes(bLower) || lower.includes(entityB.slice(0, 4))) && lower.length > 10) {
      const result = analyzeVerbRelation(sent, entityA, entityB)
      if (result) return { type: result.type, evidence: sent.trim().slice(0, 200), confidence: result.confidence * 0.8 }
      return { type: 'related', evidence: sent.trim().slice(0, 200), confidence: 0.3 }
    }
  }
  for (const sent of sentencesB) {
    const lower = sent.toLowerCase()
    if ((lower.includes(aLower) || lower.includes(entityA.slice(0, 4))) && lower.length > 10) {
      const result = analyzeVerbRelation(sent, entityB, entityA)
      if (result) return { type: result.type, evidence: sent.trim().slice(0, 200), confidence: result.confidence * 0.8 }
      return { type: 'related', evidence: sent.trim().slice(0, 200), confidence: 0.3 }
    }
  }
  return null
}

function inferFromLevel(levelA, levelB, domainA, domainB) {
  const diff = levelA - levelB
  if (diff > 0) return { type: 'theory', reason: `基于知识层级推断：${levelA}层→${levelB}层（理论→实现）`, confidence: 0.45 }
  if (diff < 0) return { type: 'implementation', reason: `基于知识层级推断：${levelB}层→${levelA}层（理论→实现）`, confidence: 0.45 }
  if (diff === 0 && domainA && domainB && domainA === domainB) return { type: 'comparison', reason: `同层级同领域，推断为对比关系`, confidence: 0.4 }
  if (diff === 0) return { type: 'comparison', reason: `同层级节点，推断为对比关系`, confidence: 0.35 }
  return null
}

export function classifyRelation(a, b, scoreResult, corpusBridge) {
  const entityA = a.title || ''; const entityB = b.title || ''
  const simVector = scoreResult?.breakdown?.sim_vector || 0; const simText = scoreResult?.breakdown?.sim_text || 0
  const levelA = a.level || 3; const levelB = b.level || 3
  if (corpusBridge && corpusBridge.sentence) {
    const verbResult = analyzeVerbRelation(corpusBridge.sentence, entityA, entityB)
    if (verbResult) return makeResult(verbResult.type, verbResult.verb ? `知识库桥接句谓语"${verbResult.verb}"判定` : '知识库桥接句谓语判定', corpusBridge.sentence, verbResult.confidence, 'corpus_verb')
    if (corpusBridge.type === 'direct_same') return makeResult('related', '知识库中为同一实体', corpusBridge.sentence, 0.85, 'corpus_direct')
    return makeResult('related', '知识库桥接关联', corpusBridge.sentence, 0.5, 'corpus_bridge')
  }
  const cooccurResult = analyzeCooccurrence(a.rawText, b.rawText, entityA, entityB)
  if (cooccurResult) return makeResult(cooccurResult.type, '用户笔记共现句式分析', cooccurResult.evidence, cooccurResult.confidence, 'cooccurrence')
  const levelResult = inferFromLevel(levelA, levelB, a._domain, b._domain)
  if (levelResult && levelResult.confidence >= 0.35) return makeResult(levelResult.type, levelResult.reason, '', levelResult.confidence, 'level_inference')
  if (simVector > 0.92 && simText < 0.15) return makeResult('related', `语义向量相似度 ${(simVector * 100).toFixed(1)}% 但文本重合度仅 ${(simText * 100).toFixed(1)}%，判定为同义表达`, '', 0.9, 'semantic_synonym')
  if (simVector > 0.7) return makeResult('related', '语义高度相似但无法判定具体关系类型', '', 0.6, 'semantic_fallback')
  if (simText > 0.3) return makeResult('related', '关键词重合度较高', '', 0.4, 'keyword_fallback')
  if (scoreResult?.sources?.includes('corpus_bridge')) return makeResult('related', '知识库推理关联', scoreResult?.evidence || '', 0.35, 'corpus_fallback')
  return makeResult('related', '综合弱关联', '', 0.2, 'default_fallback')
}

function makeResult(type, reason, evidence, confidence, method) {
  const rt = RELATION_TYPES[type] || RELATION_TYPES.related
  return { type: rt.code, label: rt.label, color: rt.color, icon: rt.icon, symbol: rt.symbol, lineStyle: rt.lineStyle, reason, evidence: evidence ? evidence.slice(0, 300) : '', confidence: Math.round(confidence * 1000) / 1000, method }
}

export function getRelationColor(type) { return (RELATION_TYPES[type] || RELATION_TYPES.related).color }
export function getRelationLabel(type) { return (RELATION_TYPES[type] || RELATION_TYPES.related).label }
export function getRelationIcon(type) { return (RELATION_TYPES[type] || RELATION_TYPES.related).icon }
export function getRelationLineStyle(type) { return (RELATION_TYPES[type] || RELATION_TYPES.related).lineStyle }
export function getAllRelationTypes() { return Object.values(RELATION_TYPES) }

export function getEvidenceStrength(a, b, scoreResult, corpusBridge) {
  const simVector = scoreResult?.breakdown?.sim_vector || 0; const simText = scoreResult?.breakdown?.sim_text || 0; const simCorpus = scoreResult?.breakdown?.sim_corpus || 0
  if (corpusBridge && (corpusBridge.type === 'direct_same' || corpusBridge.sentence)) return { level: 'strong', label: '强证据', color: '#6dd48a', icon: '🟢' }
  if (simCorpus > 0.4) return { level: 'strong', label: '强证据', color: '#6dd48a', icon: '🟢' }
  const overlapKw = (scoreResult?.overlap_keywords || []).length; const overlapEnt = (scoreResult?.overlap_entities || []).length
  if (overlapKw >= 5 || overlapEnt >= 3) return { level: 'strong', label: '强证据', color: '#6dd48a', icon: '🟢' }
  if (simVector > 0.8) return { level: 'medium', label: '中证据', color: '#f5b462', icon: '🟡' }
  if (overlapKw >= 3 || overlapEnt >= 2) return { level: 'medium', label: '中证据', color: '#f5b462', icon: '🟡' }
  if (a.fileId && b.fileId && a.fileId === b.fileId && simVector > 0.6) return { level: 'medium', label: '中证据', color: '#f5b462', icon: '🟡' }
  if (simVector > 0.6) return { level: 'weak', label: '弱证据', color: '#f5a623', icon: '🟠' }
  if (simText > 0.2) return { level: 'weak', label: '弱证据', color: '#f5a623', icon: '🟠' }
  if (overlapKw >= 1 || overlapEnt >= 1) return { level: 'weak', label: '弱证据', color: '#f5a623', icon: '🟠' }
  return { level: 'none', label: '无证据', color: '#f87086', icon: '🔴' }
}

const relationClassifier = { classifyRelation, RELATION_TYPES, getEvidenceStrength, getRelationColor, getRelationLabel, getRelationIcon, getRelationLineStyle, getAllRelationTypes }
export default relationClassifier
