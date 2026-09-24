/**
 * knowledgeValidator.js 知识点智能校验引擎
 */
import { cosine, jaccard } from './vectorEngine'
import { findEntitiesInText, getEntityByName, getOntologySnapshot } from './corpusMatcher'

export const ISSUE_TYPES = {
  invalid_fragment: { code: 'invalid_fragment', label: '无效碎片', severity: 'high', description: '知识点过短或无实际语义' },
  duplicate_synonym: { code: 'duplicate_synonym', label: '同义重复', severity: 'high', description: '两个节点为同一概念的不同表述' },
  ambiguous: { code: 'ambiguous', label: '歧义概念', severity: 'medium', description: '同一名词在不同上下文中指向不同实体' },
  nonstandard_naming: { code: 'nonstandard_naming', label: '命名不规范', severity: 'low', description: '实体名称未匹配知识库标准术语' },
  knowledge_error: { code: 'knowledge_error', label: '知识错误', severity: 'high', description: '与知识库中明确表述冲突' }
}

const NOISE_WORDS = new Set(['的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '他', '她', '它', '们', '这个', '那个', '然后', '所以', '但是', '因为', '可以', '应该', '如果', '已经', '还是', '只是', '就是', '的话', '什么', '怎么', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'of', 'in', 'on', 'at', 'and', 'or', 'to', 'for', 'with', 'as', 'by', 'this', 'that', 'it', 'from', 'but', 'not', 'they', 'we', 'you', 'i', 'he', 'she', 'has', 'have', 'had'])

const AMBIGUOUS_TERMS = new Map([
  ['spring', { meanings: [{ domain: 'software', label: 'Spring Framework（Java企业应用框架）', context: ['java', '框架', 'ioc', 'aop', '依赖注入', 'bean'] }, { domain: 'general', label: '春季（季节）', context: ['季节', '天气', '春天', '开花'] }], default_software: true }],
  ['python', { meanings: [{ domain: 'software', label: 'Python（编程语言）', context: ['编程', '语言', '脚本', '解释器', 'pip'] }, { domain: 'general', label: '蟒蛇（动物）', context: ['蛇', '爬行动物', '蟒'] }], default_software: true }],
  ['ruby', { meanings: [{ domain: 'software', label: 'Ruby（编程语言）', context: ['编程', '语言', 'rails', 'gem'] }, { domain: 'general', label: '红宝石（宝石）', context: ['宝石', '珠宝', '红色'] }], default_software: true }],
  ['go', { meanings: [{ domain: 'software', label: 'Go（编程语言）', context: ['编程', '语言', 'golang', 'goroutine'] }, { domain: 'general', label: '围棋/行走', context: ['围棋', '运动', '行走'] }], default_software: true }],
  ['rust', { meanings: [{ domain: 'software', label: 'Rust（系统编程语言）', context: ['编程', '语言', 'cargo', '所有权', 'borrow'] }, { domain: 'general', label: '铁锈（腐蚀产物）', context: ['铁锈', '腐蚀', '氧化'] }], default_software: true }],
  ['c', { meanings: [{ domain: 'software', label: 'C语言（编程语言）', context: ['编程', '语言', '指针', '编译'] }, { domain: 'general', label: '字母C/维生素C', context: ['字母', '维生素'] }], default_software: true }],
  ['shell', { meanings: [{ domain: 'software', label: 'Shell（命令行解释器）', context: ['命令行', 'bash', '脚本', 'terminal'] }, { domain: 'general', label: '贝壳（外壳）', context: ['贝壳', '外壳', '蛋壳'] }], default_software: true }],
  ['cookie', { meanings: [{ domain: 'software', label: 'Cookie（HTTP状态管理）', context: ['http', '浏览器', 'session', 'web'] }, { domain: 'general', label: '饼干（食物）', context: ['饼干', '食物', '甜点'] }], default_software: false }],
  ['thread', { meanings: [{ domain: 'software', label: '线程（并发执行单元）', context: ['并发', '多线程', '进程', '锁'] }, { domain: 'general', label: '线（物理线）', context: ['针线', '线头', '缝纫'] }], default_software: true }],
  ['pool', { meanings: [{ domain: 'software', label: '资源池（连接池/线程池）', context: ['连接池', '线程池', '资源', '复用'] }, { domain: 'general', label: '水池/游泳池', context: ['水池', '游泳', '池塘'] }], default_software: false }]
])

const ERROR_PATTERNS = [
  { pattern: /栈.*存储.*堆|堆.*存储.*栈/, correct: '栈(Stack)与堆(Heap)是独立的内存区域，分别用于存储局部变量和动态分配的对象', topic: '内存模型' },
  { pattern: /栈.*大.*堆|堆.*大.*栈|栈.*比.*堆.*大|堆.*比.*栈.*大/, correct: '堆通常比栈大得多，栈大小一般受限于线程栈大小（默认1MB），堆可达物理内存上限', topic: '内存模型' },
  { pattern: /GC.*回收.*栈|栈.*GC|栈.*垃圾回收/, correct: 'GC（垃圾回收）仅作用于堆内存，栈内存通过函数调用栈帧自动管理', topic: '内存管理' },
  { pattern: /tcp.*无连接|udp.*连接/, correct: 'TCP是面向连接的协议，UDP是无连接的协议', topic: '网络协议' },
  { pattern: /http.*加密.*不.*加密|https.*不.*加密/, correct: 'HTTP是明文协议，HTTPS通过TLS/SSL层实现加密传输', topic: '网络协议' },
  { pattern: /关系.*数据库.*不.*事务|nosql.*事务.*不.*支持/, correct: '关系型数据库支持ACID事务，部分NoSQL数据库（如MongoDB 4.0+）也支持多文档事务', topic: '数据库' },
  { pattern: /索引.*减慢.*查询|索引.*降低.*查询.*速度/, correct: '索引通过B+树等数据结构加速查询，但会增加写入开销', topic: '数据库' }
]

export function createValidator(nodes, links, options = {}) {
  const { autoAcceptLow = false, onProgress = null } = options
  return {
    nodes, links, autoAcceptLow, onProgress,
    async validateAll() {
      const report = { total: this.nodes.length, issues: [], stats: { invalid_fragment: 0, duplicate_synonym: 0, ambiguous: 0, nonstandard_naming: 0, knowledge_error: 0 }, merged: 0, discarded: 0, autoFixed: 0, timestamp: Date.now() }
      this._reportProgress(1, 5)
      for (const node of this.nodes) { const issue = this._checkInvalidFragment(node); if (issue) { this._addIssue(node, issue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(issue); node.validate.status = 'pending' } }
      this._reportProgress(2, 5)
      const dupIssues = await this._checkDuplicates()
      for (const { nodeA, nodeB, issue } of dupIssues) {
        this._addIssue(nodeA, issue, report); this._addIssue(nodeB, { ...issue, reason: `与「${nodeA.title}」同义重复` }, report)
        nodeA.validate = nodeA.validate || this._initValidate(); nodeB.validate = nodeB.validate || this._initValidate()
        nodeA.validate.issues.push(issue); nodeB.validate.issues.push({ ...issue, suggestion: `建议合并到「${nodeA.title}」`, duplicateOf: nodeA.id })
        nodeA.validate.status = 'pending'; nodeB.validate.status = 'pending'
      }
      this._reportProgress(3, 5)
      for (const node of this.nodes) { const issue = this._checkAmbiguous(node); if (issue) { this._addIssue(node, issue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(issue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' } }
      this._reportProgress(4, 5)
      for (const node of this.nodes) {
        if (node.validate?.status === 'discarded') continue
        const issue = this._checkNonstandardNaming(node)
        if (issue) { if (this.autoAcceptLow) { this._applyAutoFix(node, issue); report.autoFixed++; continue } this._addIssue(node, issue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(issue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' }
      }
      this._reportProgress(5, 5)
      for (const node of this.nodes) {
        if (node.validate?.status === 'discarded') continue
        const issue = this._checkKnowledgeError(node)
        if (issue) { this._addIssue(node, issue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(issue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' }
      }
      return report
    },
    async validateNewNodes(newNodes) {
      const oldNodes = this.nodes.filter(n => !newNodes.includes(n))
      const report = { total: newNodes.length, issues: [], stats: { invalid_fragment: 0, duplicate_synonym: 0, ambiguous: 0, nonstandard_naming: 0, knowledge_error: 0 }, merged: 0, discarded: 0, autoFixed: 0, timestamp: Date.now() }
      for (const node of newNodes) { const issue = this._checkInvalidFragment(node); if (issue) { this._addIssue(node, issue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(issue); node.validate.status = 'pending' } }
      const dupIssues = await this._checkDuplicatesNewVsAll(newNodes, this.nodes)
      for (const { nodeA, nodeB, issue } of dupIssues) {
        this._addIssue(nodeA, issue, report); this._addIssue(nodeB, { ...issue, reason: `与「${nodeA.title}」同义重复` }, report)
        nodeA.validate = nodeA.validate || this._initValidate(); nodeB.validate = nodeB.validate || this._initValidate()
        nodeA.validate.issues.push(issue); nodeB.validate.issues.push({ ...issue, suggestion: `建议合并到「${nodeA.title}」`, duplicateOf: nodeA.id })
        nodeA.validate.status = 'pending'; nodeB.validate.status = 'pending'
      }
      for (const node of newNodes) {
        const ambIssue = this._checkAmbiguous(node)
        if (ambIssue) { this._addIssue(node, ambIssue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(ambIssue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' }
        const namingIssue = this._checkNonstandardNaming(node)
        if (namingIssue) { if (this.autoAcceptLow) { this._applyAutoFix(node, namingIssue); report.autoFixed++; continue } this._addIssue(node, namingIssue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(namingIssue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' }
        const errIssue = this._checkKnowledgeError(node)
        if (errIssue) { this._addIssue(node, errIssue, report); node.validate = node.validate || this._initValidate(); node.validate.issues.push(errIssue); if (node.validate.status !== 'discarded') node.validate.status = 'pending' }
      }
      return report
    },
    _initValidate() { return { status: 'confirmed', issues: [], aiFix: null, manualEdit: null, confirmedAt: null } },
    _checkInvalidFragment(node) {
      const title = (node.title || '').trim(); const desc = (node.description || '').trim(); const combined = title + ' ' + desc
      const chineseChars = (title.match(/[\u4e00-\u9fa5]/g) || []).length; const alphaChars = (title.match(/[a-zA-Z]/g) || []).length
      const totalMeaningful = chineseChars + alphaChars
      if (totalMeaningful < 3 && combined.length < 20) return { type: 'invalid_fragment', severity: 'high', reason: '该片段不包含有效知识信息，可能是标点符号或语气词残留。', suggestion: '建议丢弃该节点', evidence: `标题: "${title}" (有效字符数: ${totalMeaningful})`, aiFix: 'discard' }
      const words = title.toLowerCase().split(/[\s,，。；;、]+/).filter(Boolean)
      const noiseCount = words.filter(w => NOISE_WORDS.has(w) || w.length <= 1).length
      if (words.length > 0 && noiseCount >= words.length && totalMeaningful < 5) return { type: 'invalid_fragment', severity: 'high', reason: '该片段仅包含停用词和语气词，不包含有效知识信息。', suggestion: '建议丢弃该节点', evidence: `标题: "${title}"`, aiFix: 'discard' }
      return null
    },
    async _checkDuplicates() {
      const issues = []; const validNodes = this.nodes.filter(n => { if (!n.vector) return false; if (n.validate?.status === 'discarded') return false; return true })
      const seen = new Set()
      for (let i = 0; i < validNodes.length; i++) { for (let j = i + 1; j < validNodes.length; j++) {
        const a = validNodes[i]; const b = validNodes[j]
        const key = a.id < b.id ? a.id + '|' + b.id : b.id + '|' + a.id
        if (seen.has(key)) continue
        seen.add(key)
        const simVector = cosine(a.vector, b.vector); const simText = jaccard(a.keywords || [], b.keywords || [])
        if (simVector > 0.92 && simText < 0.3) {
          const aWeight = (a.keywords?.length || 0) + (a._deg || 0); const bWeight = (b.keywords?.length || 0) + (b._deg || 0)
          const primary = aWeight >= bWeight ? a : b; const secondary = aWeight >= bWeight ? b : a
          issues.push({ nodeA: primary, nodeB: secondary, issue: { type: 'duplicate_synonym', severity: 'high', reason: `「${primary.title}」与「${secondary.title}」为同一概念的不同表述（语义相似度 ${(simVector * 100).toFixed(1)}%，文本重合度 ${(simText * 100).toFixed(1)}%），建议合并。`, suggestion: `合并到「${primary.title}」`, evidence: `语义向量相似度: ${(simVector * 100).toFixed(1)}% | 关键词重合度: ${(simText * 100).toFixed(1)}%`, aiFix: 'merge', mergeTarget: primary.id, mergeSource: secondary.id, simVector, simText } })
        }
      } }
      return issues
    },
    async _checkDuplicatesNewVsAll(newNodes, allNodes) {
      const issues = []; const validOld = allNodes.filter(n => { if (!n.vector) return false; if (n.validate?.status === 'discarded') return false; return true })
      for (const a of newNodes) {
        if (!a.vector) continue
        for (const b of validOld) {
          if (a.id === b.id) continue
          const simVector = cosine(a.vector, b.vector); const simText = jaccard(a.keywords || [], b.keywords || [])
          if (simVector > 0.92 && simText < 0.3) {
            const aWeight = (a.keywords?.length || 0) + (a._deg || 0); const bWeight = (b.keywords?.length || 0) + (b._deg || 0)
            const primary = aWeight >= bWeight ? a : b; const secondary = aWeight >= bWeight ? b : a
            issues.push({ nodeA: primary, nodeB: secondary, issue: { type: 'duplicate_synonym', severity: 'high', reason: `「${primary.title}」与「${secondary.title}」为同一概念的不同表述，建议合并。`, suggestion: `合并到「${primary.title}」`, evidence: `语义向量相似度: ${(simVector * 100).toFixed(1)}% | 关键词重合度: ${(simText * 100).toFixed(1)}%`, aiFix: 'merge', mergeTarget: primary.id, mergeSource: secondary.id, simVector, simText } })
          }
        }
      }
      return issues
    },
    _checkAmbiguous(node) {
      const title = (node.title || '').toLowerCase().trim(); const desc = (node.description || '').toLowerCase(); const combined = title + ' ' + desc
      const ambEntry = AMBIGUOUS_TERMS.get(title)
      if (!ambEntry) return null
      const softwareContext = ambEntry.meanings.find(m => m.domain === 'software'); const generalContext = ambEntry.meanings.find(m => m.domain === 'general')
      if (!softwareContext || !generalContext) return null
      const hasSoftwareContext = softwareContext.context.some(kw => combined.includes(kw)); const hasGeneralContext = generalContext.context.some(kw => combined.includes(kw))
      if (hasSoftwareContext && !hasGeneralContext) return null
      if (!hasSoftwareContext || hasGeneralContext) return { type: 'ambiguous', severity: 'medium', reason: `「${node.title}」在软件领域通常指 ${softwareContext.label}，但当前上下文${hasGeneralContext ? '存在其他领域含义' : '缺乏明确指向'}，存在歧义。`, suggestion: `建议将名称标准化为「${softwareContext.label}」以消除歧义`, evidence: `原文: "${node.description?.slice(0, 100)}"`, aiFix: softwareContext.label.split('（')[0].trim() }
      return null
    },
    _checkNonstandardNaming(node) {
      const title = (node.title || '').trim(); const desc = (node.description || '').trim()
      const entity = getEntityByName(title)
      if (entity) return null
      const namingMap = new Map([
        ['垃圾回收', { standard: 'Garbage Collection (GC)', reason: '软件工程标准术语' }], ['垃圾收集', { standard: 'Garbage Collection (GC)', reason: '软件工程标准术语' }], ['垃圾回收器', { standard: 'Garbage Collector (GC)', reason: '软件工程标准术语' }], ['内存泄漏', { standard: 'Memory Leak', reason: '软件工程标准术语' }], ['内存溢出', { standard: 'Out of Memory (OOM)', reason: '软件工程标准术语' }], ['死锁', { standard: 'Deadlock', reason: '软件工程标准术语' }], ['活锁', { standard: 'Livelock', reason: '软件工程标准术语' }], ['竞态', { standard: 'Race Condition', reason: '并发编程标准术语' }], ['原子操作', { standard: 'Atomic Operation', reason: '并发编程标准术语' }], ['互斥锁', { standard: 'Mutex', reason: '并发编程标准术语' }], ['读写锁', { standard: 'Read-Write Lock', reason: '并发编程标准术语' }], ['自旋锁', { standard: 'Spinlock', reason: '并发编程标准术语' }], ['信号量', { standard: 'Semaphore', reason: '并发编程标准术语' }], ['回调函数', { standard: 'Callback', reason: '软件工程标准术语' }], ['闭包', { standard: 'Closure', reason: '软件工程标准术语' }], ['高阶函数', { standard: 'Higher-Order Function', reason: '函数式编程标准术语' }], ['柯里化', { standard: 'Currying', reason: '函数式编程标准术语' }], ['依赖注入', { standard: 'Dependency Injection (DI)', reason: '设计模式标准术语' }], ['控制反转', { standard: 'Inversion of Control (IoC)', reason: '设计模式标准术语' }], ['面向切面', { standard: 'Aspect-Oriented Programming (AOP)', reason: '软件工程标准术语' }], ['负载均衡', { standard: 'Load Balancing', reason: '分布式系统标准术语' }], ['服务发现', { standard: 'Service Discovery', reason: '微服务标准术语' }], ['熔断器', { standard: 'Circuit Breaker', reason: '微服务标准术语' }], ['API网关', { standard: 'API Gateway', reason: '微服务标准术语' }], ['消息队列', { standard: 'Message Queue (MQ)', reason: '分布式系统标准术语' }], ['发布订阅', { standard: 'Publish-Subscribe (Pub/Sub)', reason: '消息模式标准术语' }], ['对象关系映射', { standard: 'Object-Relational Mapping (ORM)', reason: '数据库标准术语' }], ['持续集成', { standard: 'Continuous Integration (CI)', reason: 'DevOps标准术语' }], ['持续部署', { standard: 'Continuous Deployment (CD)', reason: 'DevOps标准术语' }], ['容器化', { standard: 'Containerization', reason: 'DevOps标准术语' }], ['虚拟化', { standard: 'Virtualization', reason: '基础设施标准术语' }]
      ])
      const mapping = namingMap.get(title)
      if (mapping) return { type: 'nonstandard_naming', severity: 'low', reason: `「${title}」在${mapping.reason}中标准表达为「${mapping.standard}」，建议标准化。`, suggestion: `标准化为「${mapping.standard}」`, evidence: `当前名称: "${title}" → 标准术语: "${mapping.standard}"`, aiFix: mapping.standard }
      const { entities } = getOntologySnapshot()
      for (const e of entities) {
        if (!e.aliases) continue
        for (const alias of e.aliases) { if (alias.toLowerCase().trim() === title.toLowerCase().trim()) return { type: 'nonstandard_naming', severity: 'low', reason: `「${title}」是「${e.name}」的别名，建议使用标准名称。`, suggestion: `标准化为「${e.name}」`, evidence: `知识库记录: "${title}" 为 "${e.name}" 的别名`, aiFix: e.name } }
      }
      return null
    },
    _checkKnowledgeError(node) {
      const desc = (node.description || '').trim(); const rawText = (node.rawText || '').trim(); const combined = desc + ' ' + rawText
      for (const ep of ERROR_PATTERNS) {
        if (ep.pattern.test(combined)) {
          const match = combined.match(ep.pattern)
          return { type: 'knowledge_error', severity: 'high', reason: `该表述"${match[0]}"与${ep.topic}常识相悖。${ep.correct}`, suggestion: `修改为: "${ep.correct}"`, evidence: `匹配原文: "${match[0]}"`, aiFix: ep.correct }
        }
      }
      return null
    },
    _applyAutoFix(node, issue) {
      if (issue.type === 'nonstandard_naming' && issue.aiFix) {
        node.title = issue.aiFix
        node.validate = node.validate || this._initValidate()
        node.validate.status = 'auto_fixed'; node.validate.aiFix = issue.aiFix; node.validate.confirmedAt = Date.now()
        node.validate.issues = (node.validate.issues || []).filter(i => i.type !== 'nonstandard_naming')
      }
    },
    _addIssue(node, issue, report) { report.issues.push({ nodeId: node.id, nodeTitle: node.title, ...issue }); if (report.stats[issue.type] !== undefined) report.stats[issue.type]++ },
    _reportProgress(step, total) { if (this.onProgress) this.onProgress(step, total) }
  }
}

export async function validateNodes(nodes, links, options = {}) { const validator = createValidator(nodes, links, options); return validator.validateAll() }
export async function validateNewNodes(nodes, newNodes, links, options = {}) { const validator = createValidator(nodes, links, options); return validator.validateNewNodes(newNodes) }

export function getPendingIssueCount(nodes) {
  let count = 0
  for (const n of nodes) { if (n.validate?.status === 'pending' && n.validate?.issues?.length) count += n.validate.issues.length }
  return count
}

export function getPendingIssues(nodes) {
  const severityOrder = { high: 0, medium: 1, low: 2 }; const all = []
  for (const n of nodes) {
    if (n.validate?.status !== 'pending' || !n.validate?.issues?.length) continue
    for (const issue of n.validate.issues) all.push({ nodeId: n.id, nodeTitle: n.title, node: n, ...issue })
  }
  return all.sort((a, b) => (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99))
}

export function acceptFix(node, issue, allNodes, allLinks) {
  const result = { action: 'none', node, mergedLinks: [] }
  if (issue.aiFix === 'discard') { node.validate.status = 'discarded'; node.validate.confirmedAt = Date.now(); result.action = 'discarded'; return result }
  if (issue.aiFix === 'merge' && issue.mergeTarget && issue.mergeSource) {
    const targetNode = allNodes.find(n => n.id === issue.mergeTarget); const sourceNode = allNodes.find(n => n.id === issue.mergeSource)
    if (targetNode && sourceNode) {
      targetNode.keywords = [...new Set([...(targetNode.keywords || []), ...(sourceNode.keywords || [])])]
      targetNode.entities = [...new Set([...(targetNode.entities || []), ...(sourceNode.entities || [])])]
      const transferredLinks = []
      for (const l of allLinks) {
        const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target
        let modified = false
        if (s === sourceNode.id) { l.source = targetNode.id; modified = true }
        if (t === sourceNode.id) { l.target = targetNode.id; modified = true }
        if (modified) { l.id = 'l_' + (typeof l.source === 'object' ? l.source.id : l.source) + '_' + (typeof l.target === 'object' ? l.target.id : l.target); transferredLinks.push(l) }
      }
      const cleaned = allLinks.filter(l => { const s = typeof l.source === 'object' ? l.source.id : l.source; const t = typeof l.target === 'object' ? l.target.id : l.target; return s !== t })
      sourceNode.validate = sourceNode.validate || { status: 'discarded', issues: [], aiFix: null, manualEdit: null, confirmedAt: null }
      sourceNode.validate.status = 'discarded'; sourceNode.validate.confirmedAt = Date.now()
      targetNode.validate = targetNode.validate || { status: 'confirmed', issues: [], aiFix: null, manualEdit: null, confirmedAt: null }
      targetNode.validate.status = 'confirmed'; targetNode.validate.confirmedAt = Date.now(); targetNode.validate.issues = (targetNode.validate.issues || []).filter(i => i.type !== 'duplicate_synonym')
      result.action = 'merged'; result.mergedLinks = transferredLinks
      return result
    }
  }
  if (issue.aiFix) {
    if (issue.type === 'nonstandard_naming' || issue.type === 'ambiguous') node.title = issue.aiFix
    node.validate.status = 'confirmed'; node.validate.aiFix = issue.aiFix; node.validate.confirmedAt = Date.now(); node.validate.issues = (node.validate.issues || []).filter(i => i !== issue)
    result.action = 'fixed'; return result
  }
  node.validate.status = 'confirmed'; node.validate.confirmedAt = Date.now(); node.validate.issues = (node.validate.issues || []).filter(i => i !== issue)
  result.action = 'confirmed'; return result
}

export function manualEditNode(node, newValue) {
  node.validate = node.validate || { status: 'confirmed', issues: [], aiFix: null, manualEdit: null, confirmedAt: null }
  node.validate.status = 'confirmed'; node.validate.manualEdit = newValue; node.validate.confirmedAt = Date.now(); node.title = newValue; node.validate.issues = []
}

export function discardNode(node) { node.validate = node.validate || { status: 'discarded', issues: [], aiFix: null, manualEdit: null, confirmedAt: null }; node.validate.status = 'discarded'; node.validate.confirmedAt = Date.now() }

export function restoreNode(node) { if (node.validate?.status === 'discarded') { node.validate.status = 'confirmed'; node.validate.confirmedAt = null; node.validate.issues = [] } }

export function skipIssue(node, issue) { node.validate = node.validate || { status: 'pending', issues: [], aiFix: null, manualEdit: null, confirmedAt: null } }

const knowledgeValidator = { createValidator, validateNodes, validateNewNodes, getPendingIssueCount, getPendingIssues, acceptFix, manualEditNode, discardNode, restoreNode, skipIssue, ISSUE_TYPES }
export default knowledgeValidator
