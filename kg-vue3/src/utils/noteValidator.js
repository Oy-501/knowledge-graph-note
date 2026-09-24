/**
 * noteValidator.js v2 知识校验统一内核
 */
import { getOntologySnapshot, findEntitiesInText, getEntityByName } from './corpusMatcher'

export const SEVERITIES = {
  critical: { code: 'critical', label: '严重', weight: 4, icon: '⛔', color: '#ff3b30', desc: '与知识库明确相悖，建议修正后保存' },
  major: { code: 'major', label: '主要', weight: 3, icon: '🟠', color: '#ff8c1a', desc: '显著错误或易误导表述，建议修正' },
  minor: { code: 'minor', label: '次要', weight: 2, icon: '🟡', color: '#d99a00', desc: '措辞/规范/精确度建议' },
  info: { code: 'info', label: '提示', weight: 1, icon: '🔵', color: '#2f8fe0', desc: '信息性提示，可忽略' }
}
export const SEVERITY_ORDER = ['critical', 'major', 'minor', 'info']
const _sevWeight = s => SEVERITIES[s] ? SEVERITIES[s].weight : 0

const LEGACY_SEVERITY_MAP = { error: 'critical', high: 'critical', warning: 'major', medium: 'major', low: 'minor', info: 'info' }
export function normalizeSeverity(s) { return LEGACY_SEVERITY_MAP[s] || (SEVERITIES[s] ? s : 'major') }

export const ERROR_TYPES = {
  factual_error: { code: 'factual_error', label: '事实错误', severity: 'critical', icon: '⛔', description: '与知识库明确知识相悖' },
  logic_error: { code: 'logic_error', label: '逻辑矛盾', severity: 'critical', icon: '⛔', description: '推理链条断裂或自相矛盾' },
  relation_error: { code: 'relation_error', label: '关系错误', severity: 'major', icon: '🟠', description: '知识之间的关系类型/方向判断错误' },
  confusion: { code: 'confusion', label: '概念混淆', severity: 'major', icon: '🟠', description: '多个不同概念被混为一谈' },
  imprecision: { code: 'imprecision', label: '表述不精确', severity: 'minor', icon: '🟡', description: '描述模糊/碎片化，缺乏关键限定' },
  outdated: { code: 'outdated', label: '过时知识', severity: 'major', icon: '🟠', description: '已被新技术/新标准取代' },
  ambiguous: { code: 'ambiguous', label: '歧义术语', severity: 'minor', icon: '🟡', description: '同一术语有多个含义，未明确上下文' }
}

const TYPE_ALIAS = { invalid_fragment: 'imprecision', nonstandard_naming: 'ambiguous', fragment: 'imprecision', knowledge_error: 'factual_error', potential_confusion: 'confusion', conflict: 'logic_error' }
export function normalizeType(t) { return ERROR_TYPES[t] ? t : (TYPE_ALIAS[t] || 'factual_error') }

export const CREDIBILITY_LEVELS = {
  L0: { level: 0, label: '内置种子知识库', weight: 5, stars: '⭐⭐⭐⭐⭐', tag: '权威' },
  L1: { level: 1, label: '用户确认知识', weight: 4, stars: '⭐⭐⭐⭐', tag: '已验证' },
  L2: { level: 2, label: '高置信度推断', weight: 3, stars: '⭐⭐⭐', tag: '系统推断' },
  L3: { level: 3, label: '待确认知识', weight: 1, stars: '⭐', tag: '待验证' },
  L4: { level: 4, label: '无来源断言', weight: 0, stars: '☆', tag: '请补充来源' }
}

const KB_FACT_CHECKS = [
  { pattern: /java.*解释型|java.*解释执行.*语言|java.*纯解释/, correction: 'Java 是"编译为字节码 + JVM 解释执行"的混合型语言', evidence: '软件知识库 - 编程语言篇', severity: 'critical' },
  { pattern: /python.*编译型|python.*编译型语言/, correction: 'Python 是解释型语言（.pyc 只是字节码缓存，本质仍解释执行）', evidence: '软件知识库 - 编程语言篇', severity: 'critical' },
  { pattern: /(javascript|java).*脚本.*(编译|编译型)/, correction: 'JavaScript 是解释型/即时编译（JIT）语言，非传统编译型', evidence: '软件知识库 - 编程语言篇', severity: 'major' },
  { pattern: /http(?!s).*(?<!不)(?<!无)(?<!未)加密|http(?!s).*自带加密/, correction: 'HTTP 本身不加密，HTTPS 通过 TLS 层实现加密', evidence: '软件知识库 - 网络全链路篇', severity: 'critical' },
  { pattern: /js.*单线程.*不能并发|node.*单线程.*不能并发|javascript.*不能并发/, correction: 'JavaScript 是单线程事件循环，但异步 I/O + Worker Threads 可支持并发', evidence: '软件知识库 - 编程语言篇', severity: 'major' },
  { pattern: /sql.*不支持.*查询|sql.*不能.*复杂/, correction: 'SQL 支持复杂查询（JOIN、子查询、窗口函数、CTE 等）', evidence: '软件知识库 - 数据库篇', severity: 'major' },
  { pattern: /jvm.*内存.*只有.*堆|jvm.*内存.*只有.*栈/, correction: 'JVM 内存区域包括：堆、栈、方法区、程序计数器、本地方法栈', evidence: '软件知识库 - 编程语言篇', severity: 'critical' },
  { pattern: /栈.*存储.*堆|堆.*存储.*栈|gc.*回收.*栈|栈.*垃圾回收/, correction: '栈(Stack)与堆(Heap)是独立内存区域；GC 只作用于堆，栈由调用帧自动管理', evidence: '软件知识库 - 内存模型篇', severity: 'critical' },
  { pattern: /tcp.*无连接|udp.*面向连接/, correction: 'TCP 是面向连接的协议，UDP 是无连接协议', evidence: '软件知识库 - 网络传输篇', severity: 'critical' },
  { pattern: /索引.*减慢.*查询|索引.*降低.*查询.*速度/, correction: '索引通过 B+树等结构加速查询，但会增加写入开销', evidence: '软件知识库 - 数据库篇', severity: 'critical' }
]

const OUTDATED_TERMS = new Map([
  ['j2ee', { replacement: 'Jakarta EE', since: '2018', reason: 'J2EE 已更名为 Jakarta EE' }],
  ['j2se', { replacement: 'Java SE', since: '2006', reason: 'J2SE 已更名为 Java SE' }],
  ['j2me', { replacement: 'Java ME', since: '2006', reason: 'J2ME 已更名为 Java ME' }],
  ['applet', { replacement: 'WebAssembly', since: '2016', reason: 'Java Applet 已废弃' }],
  ['angularjs', { replacement: 'Angular (2+)', since: '2016', reason: 'AngularJS 1.x 已停止维护' }],
  ['python 2', { replacement: 'Python 3', since: '2020', reason: 'Python 2 已于 2020 年停止维护' }],
  ['ie浏览器', { replacement: 'Edge', since: '2022', reason: 'IE 浏览器已于 2022 年退役' }],
  ['svn', { replacement: 'Git', since: '2015', reason: 'SVN 已基本被 Git 取代' }]
])

const CONFUSION_PAIRS = [
  { a: 'javascript', b: 'java', reason: '两者为不同编程语言，仅名称相似，无直接关系' },
  { a: 'java', b: 'javascript', reason: '两者为不同编程语言，仅名称相似，无直接关系' },
  { a: 'c++', b: 'c', reason: 'C++ 是 C 的超集，但两者是不同的语言' },
  { a: 'html', b: 'css', reason: 'HTML 是结构标记语言，CSS 是样式语言，两者并列而非包含' },
  { a: '编译器', b: '解释器', reason: '编译器将源码整体转为机器码，解释器逐行执行，原理不同' },
  { a: '堆', b: '栈', reason: '堆和栈是两种不同的内存区域，彼此平行，不存在包含关系' },
  { a: 'tcp', b: 'udp', reason: 'TCP 和 UDP 是传输层两种并列协议，不可混用' },
  { a: 'http', b: 'https', reason: 'HTTPS 是 HTTP 的安全版本（+TLS），两者有本质区别' },
  { a: 'docker', b: '虚拟机', reason: 'Docker 是容器技术，虚拟机是完整 OS 虚拟化，原理不同' },
  { a: 'git', b: 'github', reason: 'Git 是版本控制系统，GitHub 是代码托管平台' },
  { a: 'sql', b: 'nosql', reason: 'SQL 是关系型查询语言，NoSQL 是非关系型数据库' },
  { a: '进程', b: '线程', reason: '进程是资源分配单位，线程是 CPU 调度单位，不可混用' },
  { a: '微服务', b: 'soa', reason: '微服务是 SOA 的一种实现风格，但两者有架构差异' }
]

const IMPRECISION_PATTERNS = [
  { pattern: /内存分为堆和栈/, msg: '请补充上下文，如"JVM内存分为堆和栈"', suggest: '补充"JVM"上下文' },
  { pattern: /gc会暂停|gc.*暂停/, msg: 'GC 暂停需区分：Minor GC（短暂暂停）vs Full GC（长时间暂停）', suggest: '补充 GC 类型上下文' },
  { pattern: /算法.*复杂度.*o\(1\)|算法.*复杂度.*o\(n\)/, msg: '请明确是"时间复杂度"还是"空间复杂度"', suggest: '补充复杂度类型' },
  { pattern: /所以.*就是.*全部|所以.*都是/, msg: '"全部/都"这类全称断言缺少限定条件', suggest: '补充例外或适用边界' }
]

const AMBIGUOUS_TERMS = [
  { term: 'spring', ctx: /编程|语言|框架|ioc|aop|依赖注入|bean|java/ },
  { term: 'python', ctx: /编程|语言|脚本|解释器|pip|代码/ },
  { term: 'ruby', ctx: /编程|语言|rails|gem|代码/ },
  { term: 'rust', ctx: /编程|语言|cargo|所有权|代码/ },
  { term: 'shell', ctx: /命令行|bash|脚本|terminal|代码/ },
  { term: 'c', ctx: /编程|语言|指针|编译|代码/ },
  { term: 'cookie', ctx: /http|浏览器|session|web|网页/ },
  { term: 'thread', ctx: /并发|多线程|进程|锁|代码/ },
  { term: 'pool', ctx: /连接池|线程池|资源|复用|代码/ }
]

function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') }

function locateTerm(text, term) {
  const lowerText = text.toLowerCase(); const t = term.toLowerCase()
  if (!t) return null
  if (/^[A-Za-z][A-Za-z0-9+._-]*$/.test(t)) {
    const re = new RegExp('(^|[^A-Za-z0-9_])' + escapeRegExp(t) + '($|[^A-Za-z0-9_])')
    const m = re.exec(lowerText)
    if (!m) return null
    return { start: m.index + m[1].length, end: m.index + m[1].length + t.length }
  }
  const idx = lowerText.indexOf(t)
  if (idx === -1) return null
  return { start: idx, end: idx + t.length }
}

function locatePair(text, a, b) {
  const ra = locateTerm(text, a); const rb = locateTerm(text, b)
  if (!ra || !rb) return null
  return ra.start <= rb.start ? ra : rb
}

const _RELATION_WORDS = /相关|包含|属于|依赖|一种|类似|一样|差不多|就是|等价|相当于|基于/
const _FUZZY_WORDS = /可能|大概|也许|或许|似乎|我觉得|我认为/

export class RealtimeValidator {
  constructor(knowledgeBase = null) { this.kb = knowledgeBase; this._ontologyCache = null }
  _getOntology() { if (!this._ontologyCache) this._ontologyCache = getOntologySnapshot(); return this._ontologyCache }
  _makeIssue(type, text, details) {
    const norm = normalizeType(type); const meta = ERROR_TYPES[norm]
    const range = details.range || { start: 0, end: (text || '').length }
    return { type: norm, severity: normalizeSeverity(details.severity || meta.severity), text, entity: details.entity ?? null, description: details.description || meta.description, correction: details.correction || '', evidence: details.evidence || '', source: details.source || 'realtime', matchStart: range.start, matchEnd: Math.max(range.start, range.end) }
  }
  validateSentence(sentence, context = {}) {
    const issues = []; const text = (sentence || '').trim()
    if (!text || text.length < 3) return issues
    const lowerText = text.toLowerCase()
    for (const check of KB_FACT_CHECKS) {
      const re = new RegExp(check.pattern.source, 'i'); const m = re.exec(lowerText)
      if (m) {
        const hitPos = m.index + Math.max(m[0].length, 1) - 1
        const win = lowerText.slice(Math.max(0, hitPos - 6), hitPos)
        if (!/[不无未非]/.test(win)) issues.push(this._makeIssue('factual_error', text, { severity: check.severity, description: '表述与知识库相悖', correction: check.correction, evidence: check.evidence, source: 'kb_fact_check', range: { start: m.index, end: m.index + Math.max(m[0].length, 1) } }))
      }
    }
    for (const [term, info] of OUTDATED_TERMS) {
      const r = locateTerm(lowerText, term)
      if (r) issues.push(this._makeIssue('outdated', text, { entity: term, description: `"${term}" 已被 "${info.replacement}" 取代（${info.since}）`, correction: `建议使用 "${info.replacement}" 替代 "${term}"`, evidence: info.reason, source: 'outdated_terms', range: r }))
    }
    for (const pair of CONFUSION_PAIRS) {
      const r = locatePair(text, pair.a, pair.b)
      if (r && _RELATION_WORDS.test(text)) issues.push(this._makeIssue('confusion', text, { entity: `${pair.a}/${pair.b}`, description: `"${pair.a}" 与 "${pair.b}" ${pair.reason}`, correction: `请区分 "${pair.a}" 与 "${pair.b}"，避免混为一谈`, evidence: '软件知识库 - 概念辨析', source: 'confusion_pairs', range: r }))
    }
    for (const amb of AMBIGUOUS_TERMS) {
      const r = locateTerm(text, amb.term)
      if (r && !amb.ctx.test(text)) issues.push(this._makeIssue('ambiguous', text, { entity: amb.term, description: `"${amb.term}" 存在歧义（技术术语 vs 日常用语），上下文未明确指向`, correction: `建议补充领域限定词，如 "${amb.term} 语言/框架/命令"`, evidence: '软件知识库 - 术语表', source: 'ambiguous_terms', range: r }))
    }
    for (const imp of IMPRECISION_PATTERNS) {
      const re = new RegExp(imp.pattern.source, 'i'); const m = re.exec(lowerText)
      if (m) issues.push(this._makeIssue('imprecision', text, { description: imp.msg, correction: imp.suggest, evidence: '表述规范 - 知识完整性', source: 'imprecision', range: { start: m.index, end: m.index + Math.max(m[0].length, 1) } }))
    }
    const cnChars = (text.match(/[\u4e00-\u9fff]/g) || []).length; const enWords = (text.match(/[a-zA-Z]{2,}/g) || []).length
    const totalUnits = cnChars + enWords
    if (totalUnits < 8 && !/^[a-zA-Z0-9_.\-\s]+$/.test(text)) issues.push(this._makeIssue('imprecision', text, { entity: null, description: `碎片化断言（有效信息约 ${totalUnits} 个字符/词），缺少上下文或来源`, correction: '补充更多上下文或出处后再保存', evidence: '内容完整性检测', source: 'fragment_check' }))
    const hasCertainty = /一定|绝对|肯定|必然|永远/.test(text)
    const hasHedge = /不一定|可能|也许|或许|未必/.test(text)
    if (hasCertainty && hasHedge) issues.push(this._makeIssue('logic_error', text, { entity: null, description: '句内同时出现绝对性断言与不确定性限定，存在逻辑矛盾', correction: '删除相互矛盾的限定词，只保留确定口径', evidence: '逻辑一致性检查', source: 'internal_consistency' }))
    const entitiesInText = findEntitiesInText(text)
    if (entitiesInText.length >= 2 && /与.*无关|和.*没有.*关系|不属于|不是.*的(一部分|分支)/.test(text)) issues.push(this._makeIssue('relation_error', text, { entity: entitiesInText.slice(0, 2).join('/'), description: '断言与知识库实体关系存疑：本体中相关实体被表述为无关', correction: '请核实实体间真实关系后再断言', evidence: '知识库桥接检测', source: 'relation_hint' }))
    return issues
  }
  validateParagraph(sentences, context = {}) {
    const allIssues = []
    for (let i = 0; i < sentences.length; i++) {
      const issues = this.validateSentence(sentences[i], { ...context, sentenceIndex: i })
      for (const issue of issues) { issue.sentenceIndex = i; issue.sentence = sentences[i] }
      allIssues.push(...issues)
    }
    return allIssues
  }
}

export function splitSentenceRanges(content) {
  const out = []; const text = content || ''
  if (!text.trim()) return out
  const re = /[^。！？!?\n]+[。！？!?]?|\n+/g
  let line = 0; let m
  while ((m = re.exec(text)) !== null) {
    const raw = m[0]; const chunkStart = m.index; const chunkEnd = m.index + raw.length
    if (!raw.trim()) { for (let i = chunkStart; i < chunkEnd; i++) if (text[i] === '\n') line++; continue }
    let s0 = chunkStart; let s1 = chunkEnd
    while (s0 < s1 && /\s/.test(text[s0])) s0++
    while (s1 > s0 && /\s/.test(text[s1 - 1])) s1--
    for (let i = 0; i < s0; i++) if (text[i] === '\n') line++
    out.push({ sentence: text.slice(s0, s1), start: s0, end: s1, line })
    for (let i = s0; i < s1; i++) if (text[i] === '\n') line++
  }
  return out
}

const _validatorSingleton = new RealtimeValidator()

export function validateText(content) {
  const issues = []; if (!content || !content.trim()) return issues
  const sentences = splitSentenceRanges(content)
  for (const { sentence, start, line } of sentences) {
    if (sentence.length < 3) continue
    const found = _validatorSingleton.validateSentence(sentence)
    for (const issue of found) issues.push({ type: issue.type, severity: issue.severity, text: sentence, entity: issue.entity, description: issue.description, correction: issue.correction, evidence: issue.evidence, source: issue.source, start: start + (issue.matchStart || 0), end: start + (issue.matchEnd || sentence.length), line })
  }
  return issues
}

export async function preSaveValidation(assertions, existingNodes = [], options = {}) {
  const validator = new RealtimeValidator(); const errors = []; const warnings = []
  for (const assertion of assertions) {
    const text = typeof assertion === 'string' ? assertion : (assertion.text || assertion.title || '')
    const issues = validator.validateSentence(text)
    for (const issue of issues) { if (issue.severity === 'critical' || issue.severity === 'major') errors.push({ ...issue, assertion: text }); else warnings.push({ ...issue, assertion: text }) }
    if (existingNodes && existingNodes.length > 0) {
      const lowerText = text.toLowerCase()
      for (const node of existingNodes) {
        if (!node || node.validate?.status === 'discarded') continue
        const nodeText = (node.title + ' ' + (node.description || '')).toLowerCase()
        const conflicts = checkConflict(lowerText, nodeText, text, node.title)
        for (const c of conflicts) errors.push({ type: 'logic_error', severity: 'major', text, assertion: text, description: `与已有知识点"${node.title}"存在潜在矛盾`, correction: c.suggestion, evidence: c.reason, source: 'existing_knowledge', conflictWith: node.id })
      }
    }
  }
  if (assertions.length > 1) {
    const internalConflicts = _checkInternalConsistency(assertions)
    for (const c of internalConflicts) errors.push({ type: 'logic_error', severity: 'critical', text: c.text, description: `笔记内部存在矛盾：与"${c.conflictingText}"不一致`, correction: c.suggestion, evidence: '逻辑一致性检查', source: 'internal_consistency' })
  }
  const errorCount = errors.length; const warningCount = warnings.length; const total = Math.max(assertions.length, 1)
  const pass = errorCount === 0; const canForceSave = !errors.some(e => e.severity === 'critical')
  const deduction = errors.reduce((s, e) => s + (e.severity === 'critical' ? 1 : 0.6), 0) + warnings.reduce((s, e) => s + (e.severity === 'minor' ? 0.25 : 0.05), 0)
  const accuracy = Math.max(0, Math.min(100, Math.round((1 - deduction / total) * 100)))
  return { pass, errors, warnings, canForceSave, summary: { total: assertions.length, passed: Math.max(0, assertions.length - errorCount - warningCount), errors: errorCount, warnings: warningCount, accuracy, checkedAt: Date.now() } }
}

export function checkConflict(text1, text2, original1, original2) {
  const conflicts = []
  const opposites = [
    { a: '是', b: '不是' }, { a: '包含', b: '不包含' }, { a: '可以', b: '不能' }, { a: '支持', b: '不支持' }, { a: '编译', b: '解释' }, { a: '编译型', b: '解释型' }, { a: '单线程', b: '多线程' }, { a: '单线程', b: '并发' }, { a: '堆', b: '栈' }, { a: '同步', b: '异步' }, { a: '阻塞', b: '非阻塞' }
  ]
  for (const opp of opposites) {
    if ((text1.includes(opp.a) && text2.includes(opp.b)) || (text1.includes(opp.b) && text2.includes(opp.a))) conflicts.push({ text: original1, conflictingText: original2, suggestion: `"${original1}" 与 "${original2}" 表述矛盾，请核实`, reason: `一个说"${opp.a}"，另一个说"${opp.b}"` })
  }
  return conflicts
}

function _checkInternalConsistency(assertions) {
  const conflicts = []; const texts = assertions.map(a => typeof a === 'string' ? a : (a.text || a.title || ''))
  for (let i = 0; i < texts.length; i++) { for (let j = i + 1; j < texts.length; j++) { const c = checkConflict(texts[i].toLowerCase(), texts[j].toLowerCase(), texts[i], texts[j]); conflicts.push(...c) } }
  return conflicts
}

export async function deepValidation(allNodes, options = {}) {
  const report = { generatedAt: Date.now(), totalNodesChecked: allNodes.length, issuesFound: { cross_note_conflicts: 0, outdated_knowledge: 0, invalid_relations: 0, redundant_content: 0 }, recommendations: [] }
  if (allNodes.length < 2) return report
  const nodeMap = new Map()
  for (const node of allNodes) {
    if (node.validate?.status === 'discarded') continue
    const key = (node.title || '').toLowerCase()
    if (!nodeMap.has(key)) nodeMap.set(key, [])
    nodeMap.get(key).push(node)
  }
  for (const [, nodes] of nodeMap) {
    if (nodes.length < 2) continue
    for (let i = 0; i < nodes.length; i++) { for (let j = i + 1; j < nodes.length; j++) {
      const textA = (nodes[i].description || nodes[i].title || '').toLowerCase(); const textB = (nodes[j].description || nodes[j].title || '').toLowerCase()
      const conflicts = checkConflict(textA, textB, nodes[i].title, nodes[j].title)
      for (const c of conflicts) { report.issuesFound.cross_note_conflicts++; report.recommendations.push({ type: 'cross_note_conflict', description: c.reason, suggestion: c.suggestion, nodeA: nodes[i].id, nodeB: nodes[j].id, severity: 'critical' }) }
    } }
  }
  for (const node of allNodes) {
    const text = (node.title + ' ' + (node.description || '')).toLowerCase()
    for (const [term, info] of OUTDATED_TERMS) { if (locateTerm(text, term)) { report.issuesFound.outdated_knowledge++; report.recommendations.push({ type: 'outdated_knowledge', nodeId: node.id, description: `"${node.title}" 中使用过时术语"${term}"`, suggestion: `建议更新为 "${info.replacement}"（${info.since}）`, evidence: info.reason, severity: 'major' }) } }
  }
  for (let i = 0; i < allNodes.length; i++) { for (let j = i + 1; j < allNodes.length; j++) {
    if (allNodes[i].validate?.status === 'discarded' || allNodes[j].validate?.status === 'discarded') continue
    const textA = (allNodes[i].title + ' ' + (allNodes[i].description || '')).toLowerCase(); const textB = (allNodes[j].title + ' ' + (allNodes[j].description || '')).toLowerCase()
    const overlap = textOverlap(textA, textB)
    if (overlap > 0.85) { report.issuesFound.redundant_content++; report.recommendations.push({ type: 'redundant_content', nodeA: allNodes[i].id, nodeB: allNodes[j].id, description: `"${allNodes[i].title}" 与 "${allNodes[j].title}" 高度相似（${Math.round(overlap * 100)}%）`, suggestion: '建议合并或区分两者内容', severity: 'minor' }) }
  } }
  return report
}

export function textOverlap(a, b) {
  if (!a || !b) return 0
  const wordsA = new Set(a.split(/\s+/).filter(w => w.length > 1)); const wordsB = new Set(b.split(/\s+/).filter(w => w.length > 1))
  if (wordsA.size === 0 || wordsB.size === 0) return 0
  let intersection = 0
  for (const w of wordsA) if (wordsB.has(w)) intersection++
  return intersection / Math.min(wordsA.size, wordsB.size)
}

export function getNodeValidationStatus(node) {
  if (!node || node.status === 'discarded') return { status: 'discarded', color: '#888', label: '已丢弃', accuracyScore: 0 }
  const report = node.validationReport
  if (!report) return { status: 'pending', color: '#8a93b0', label: '待校验', accuracyScore: 0 }
  const total = report.totalAssertions || report.total || 1
  const passed = report.passedAssertions != null ? report.passedAssertions : (report.summary ? report.summary.total - report.summary.errors : null)
  const errs = report.errors || []
  const accuracy = Math.round((total > 0 ? (passed != null ? passed : total - errs.length) / total : 1) * 100)
  const worst = errs.reduce((w, e) => Math.max(w, _sevWeight(normalizeSeverity(e.severity))), 0)
  if (worst >= 4) return { status: 'error', color: '#e84c4c', label: '存在严重错误', accuracyScore: accuracy }
  if (worst === 3) return { status: 'warning', color: '#ff8c1a', label: '存在主要问题', accuracyScore: accuracy }
  if (worst >= 2) return { status: 'warning', color: '#e8a020', label: '需优化', accuracyScore: accuracy }
  if (accuracy >= 100) return { status: 'passed', color: '#4caf50', label: '已验证', accuracyScore: 100 }
  if (accuracy >= 60) return { status: 'warning', color: '#e8a020', label: '待审查', accuracyScore: accuracy }
  return { status: 'warning', color: '#e8a020', label: '需修正', accuracyScore: accuracy }
}

export function getCredibility(node) {
  if (!node) return CREDIBILITY_LEVELS.L4
  if (node._corpusNode) return CREDIBILITY_LEVELS.L0
  if (node.verified) return CREDIBILITY_LEVELS.L1
  if (node.confidence >= 0.85) return CREDIBILITY_LEVELS.L2
  if (node.confidence >= 0.6) return CREDIBILITY_LEVELS.L3
  return CREDIBILITY_LEVELS.L4
}
