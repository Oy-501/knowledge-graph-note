/**
 * mdParser.js 知识深度层次识别与文件解析引擎
 */
import { RealtimeValidator } from './noteValidator'

const _validator = new RealtimeValidator()

export const SENTENCE_TYPES = {
  knowledge: { code: 'knowledge', label: '知识点陈述', entersGraph: true },
  question: { code: 'question', label: '疑问/问题', entersGraph: false },
  thought: { code: 'thought', label: '思考/反思', entersGraph: false },
  example: { code: 'example', label: '示例/用例', entersGraph: false },
  meta: { code: 'meta', label: '元信息', entersGraph: false }
}

const SOFTWARE_DOMAINS = {
  'AI': ['ai', '人工智能', '机器学习', '深度学习', '神经网络', 'nlp', '自然语言', '计算机视觉', 'cv', 'transformer', 'llm', '大模型', 'gpt', 'bert', 'agent', '智能体'],
  '编程语言': ['编程', '语言', 'java', 'python', 'c++', 'javascript', 'go', 'rust', 'typescript', 'kotlin', 'swift', '语法', '编译器', '解释器'],
  '数据结构与算法': ['数据结构', '算法', '哈希表', '链表', '二叉树', '排序', '搜索', '动态规划', '贪心', '图论', '复杂度', '时间复杂度'],
  '操作系统': ['操作系统', '进程', '线程', '内存管理', '文件系统', '调度', '死锁', '虚拟内存', '中断', 'io', '内核'],
  '计算机网络': ['网络', 'tcp', 'http', 'dns', '协议', '路由', 'ip', 'socket', 'websocket', '负载均衡', '代理', 'cdn'],
  '数据库': ['数据库', 'sql', 'mysql', 'redis', 'mongodb', '索引', '事务', '持久化', '缓存', '查询', '存储引擎', 'nosql'],
  '软件工程': ['软件工程', '设计模式', '架构', '微服务', 'ddd', '测试', 'ci/cd', 'devops', '敏捷', 'scrum', '重构', '代码质量'],
  '前端开发': ['前端', 'html', 'css', 'react', 'vue', 'angular', 'dom', '浏览器', '渲染', 'web', 'spa', '响应式'],
  '后端开发': ['后端', 'api', 'rest', 'graphql', 'rpc', 'spring', 'django', 'flask', 'express', 'fastapi', '认证', '授权'],
  '嵌入式': ['嵌入式', '单片机', 'arm', 'rtos', 'gpio', 'i2c', 'spi', 'uart', '固件', '硬件', '驱动', '裸机'],
  '安全': ['安全', '密码学', '加密', '认证', '漏洞', '渗透', '防火墙', 'https', 'ssl', 'tls', 'xss', 'csrf'],
  '云计算': ['云计算', 'docker', 'kubernetes', 'k8s', '容器', '编排', 'aws', 'azure', '虚拟机', 'serverless', 'paas', 'saas'],
  '写作': ['写作', '文章', '笔记', '日记', '随笔', '文档', '记录', '心得', '总结', '思考', '反思']
}

const SOFTWARE_TERMS = new Set([
  '算法', '数据结构', '编程', '代码', '函数', '类', '接口', '对象', '模块', '框架', '库',
  '数据库', '网络', '内存', '线程', '进程', '文件', '缓存', '索引', '协议', '服务',
  '编译', '解释', '执行', '部署', '调试', '测试', '优化', '重构', '设计', '架构',
  'ai', '机器学习', '深度学习', '神经网络', '模型', '训练', '推理', '向量', '嵌入',
  '前端', '后端', '服务器', '客户端', '请求', '响应', '路由', '中间件', '容器',
  '虚拟化', '分布式', '并发', '并行', '异步', '同步', '序列化', '持久化', '事务',
  'api', 'sdk', 'cli', 'gui', 'rest', 'graphql', 'rpc', 'http', 'tcp', 'udp', 'dns',
  'java', 'python', 'javascript', 'go', 'rust', 'c++', 'typescript', 'kotlin',
  'react', 'vue', 'angular', 'node', 'spring', 'django', 'flask', 'docker', 'kubernetes',
  'linux', 'git', 'mysql', 'redis', 'mongodb', 'postgresql', 'elasticsearch',
  'jvm', 'gc', 'oom', 'cpu', 'gpu', 'ram', 'ssd', 'hdd', 'io', 'os', 'kernel',
  'token', 'session', 'cookie', 'jwt', 'oauth', 'ssl', 'tls', 'https', 'ssh',
  'json', 'xml', 'yaml', 'csv', 'protobuf', 'avro', 'thrift',
  'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'pandas', 'numpy',
  'oop', 'fp', 'mvc', 'mvvm', 'solid', 'dry', 'kiss', 'tdd', 'bdd', 'ddd',
  'ci', 'cd', 'devops', 'gitops', 'mlops', 'aiops', 'finops',
  'hashmap', 'arraylist', 'linkedlist', 'trie', 'b-tree', 'lru', 'lfu',
  'ide', 'vscode', 'intellij', 'eclipse', 'vim', 'emacs', '终端', 'shell', 'bash',
  'url', 'uri', 'html', 'css', 'dom', 'svg', 'canvas', 'webgl', 'wasm',
  '正则', 'regex', 'sql', 'orm', 'acid', 'base', 'cap', 'paxos', 'raft',
  'jwt', 'rpc', 'grpc', 'websocket', 'mqtt', 'amqp', 'kafka', 'rabbitmq',
  '微服务', '单体', 'soa', 'eda', 'cqrs', 'es', 'saga', 'bff', 'api网关'
])

export function qualifyKnowledgePoint(title, description = '', rawText = '', context = {}) {
  const combined = (title + ' ' + description + ' ' + rawText).trim()
  const classification = classifySentence(rawText || title, context)
  if (classification.type !== 'knowledge') return { qualified: false, reason: 'discard_as_thought', status: 'rejected', detail: `话语类型为"${classification.type}"，非知识点陈述`, confidence: classification.confidence, domain: '' }
  const chineseChars = (combined.match(/[\u4e00-\u9fff]/g) || []).length
  const englishWords = (combined.match(/[a-zA-Z]{2,}/g) || []).length
  const totalWords = chineseChars + englishWords
  if (totalWords < 5) return { qualified: false, reason: 'discard_as_fragment', status: 'rejected', detail: `信息密度不足（仅${totalWords}个有效字符），无法表达完整含义`, confidence: 0.3, domain: '' }
  const lowerText = combined.toLowerCase(); let termCount = 0; const foundTerms = []
  for (const term of SOFTWARE_TERMS) { if (lowerText.includes(term.toLowerCase())) { termCount++; foundTerms.push(term); if (termCount >= 2) break } }
  if (termCount < 2 && totalWords < 15) return { qualified: false, reason: 'discard_as_fragment', status: 'rejected', detail: `信息密度不足（仅${termCount}个术语），可能为碎片化内容`, confidence: 0.35, domain: '' }
  let bestDomain = ''; let bestDomainScore = 0
  for (const [domain, keywords] of Object.entries(SOFTWARE_DOMAINS)) { let score = 0; for (const kw of keywords) { if (lowerText.includes(kw)) score++ }; if (score > bestDomainScore) { bestDomainScore = score; bestDomain = domain } }
  if (bestDomainScore === 0) return { qualified: false, reason: 'mark_as_unclassified', status: 'pending', detail: '无法明确归属到任何软件工程子领域', confidence: 0.2, domain: '' }
  const confidence = Math.min(0.95, 0.4 + bestDomainScore * 0.15 + termCount * 0.05 + (totalWords >= 20 ? 0.1 : 0))
  if (confidence < 0.6) return { qualified: false, reason: 'mark_low_confidence', status: 'pending', detail: `置信度 ${confidence.toFixed(2)} < 0.6，进入待定池`, confidence, domain: bestDomain }
  const validationIssues = _validator.validateSentence(rawText || title, context)
  const hasErrors = validationIssues.some(i => i.severity === 'error')
  const hasWarnings = validationIssues.some(i => i.severity === 'warning')
  return { qualified: true, reason: hasErrors ? 'with_validation_errors' : (hasWarnings ? 'with_validation_warnings' : ''), status: 'qualified', detail: `通过审核：话语类型=知识陈述，术语数=${termCount}，领域=${bestDomain}，置信度=${confidence.toFixed(2)}`, confidence, domain: bestDomain, validationIssues: validationIssues.length > 0 ? validationIssues : undefined, hasErrors, hasWarnings }
}

export const KNOWLEDGE_LEVELS = {
  L1: { level: 1, label: '元概念', desc: '最抽象的顶层概念', examples: ['AI', '编程', '算法', '软件工程'], shape: 'hexagon', color: '#1a3a5c', borderWidth: 3 },
  L2: { level: 2, label: '核心理论', desc: '理论框架、核心原理', examples: ['机器学习', '数据结构', '操作系统', '计算机网络'], shape: 'rounded', color: '#2a5a9c', borderWidth: 2 },
  L3: { level: 3, label: '具体技术', desc: '可落地实现的具体技术', examples: ['神经网络', '哈希表', 'TCP协议', '虚拟内存'], shape: 'circle', color: '#3a7acc', borderWidth: 1.5 },
  L4: { level: 4, label: '实现/工具', desc: '具体代码、框架、工具', examples: ['PyTorch', 'HashMap', 'Redis', 'Docker'], shape: 'diamond', color: '#4a9a6c', borderWidth: 1 }
}

const L1_PATTERNS = [/^AI$/i, /^人工智能$/i, /^编程$/i, /^算法$/i, /^软件工程$/i, /^计算机科学$/i, /^数学$/i, /^物理学$/i, /^语言学$/i, /^哲学$/i, /^操作系统$/i, /^计算机网络$/i, /^数据库$/i, /^编译原理$/i, /^机器学习$/i, /^深度学习$/i, /^自然语言处理$/i, /^计算机视觉$/i, /^分布式系统$/i, /^云计算$/i, /^网络安全$/i, /^密码学$/i, /^前端开发$/i, /^后端开发$/i, /^移动开发$/i, /^嵌入式开发$/i]
const L2_PATTERNS = [/^(数据结构|算法设计|面向对象|函数式编程|并发编程|设计模式)$/i, /^(线性代数|概率论|统计学|微积分|离散数学|图论)$/i, /^(编译原理|操作系统|计算机网络|计算机组成|数据库系统)$/i, /^(机器学习|深度学习|强化学习|迁移学习|联邦学习)$/i, /^(软件架构|微服务|领域驱动设计|测试驱动开发)$/i, /^(密码学|网络协议|分布式理论|CAP理论|一致性算法)$/i, /^(内存管理|进程调度|文件系统|I\/O模型|虚拟化)$/i]
const L4_PATTERNS = [/^(PyTorch|TensorFlow|Keras|Scikit-learn|Pandas|NumPy|Matplotlib|Jupyter)$/i, /^(React|Vue|Angular|Svelte|Next\.js|Nuxt|Vite|Webpack|Babel|ESLint)$/i, /^(Spring|Django|Flask|Express|FastAPI|Gin|Koa|Rails|Laravel)$/i, /^(Docker|Kubernetes|Jenkins|GitLab CI|GitHub Actions|Terraform|Ansible)$/i, /^(MySQL|PostgreSQL|MongoDB|Redis|Elasticsearch|Cassandra|Neo4j|SQLite)$/i, /^(HashMap|ArrayList|LinkedList|TreeMap|ConcurrentHashMap|BloomFilter)$/i, /^(Nginx|Apache|HAProxy|Envoy|Traefik|Caddy)$/i, /^(Git|SVN|Mercurial|Figma|Postman|Swagger|GraphQL|gRPC|Thrift)$/i]

export function classifySentence(sentence, context = {}) {
  if (!sentence || !sentence.trim()) return { type: 'meta', confidence: 1 }
  const s = sentence.trim()
  if (/^[#]{1,4}\s/.test(s) || /^\d{4}[-/]\d{2}[-/]\d{2}/.test(s) || /^作者[：:]/.test(s) || /^创建时间[：:]/.test(s) || /^更新时间[：:]/.test(s)) return { type: 'meta', confidence: 0.95 }
  if (/为什么|怎么[做样]|如何|是否|能不能|可以吗|对吗|是什么|什么意思|啥意思|咋/.test(s)) return { type: 'question', confidence: 0.9 }
  if (/[？?]$/.test(s) || /吗[？?]?$/.test(s) || /呢[？?]?$/.test(s)) return { type: 'question', confidence: 0.85 }
  if (/我觉得|我认为|感觉|可能|也许|大概|似乎|好像|不知道|不懂|搞不懂|不明白|不太清楚|不清楚/.test(s)) return { type: 'thought', confidence: 0.75 }
  if (/我想|我猜|我怀疑|我困惑|我迷茫|我不确定/.test(s)) return { type: 'thought', confidence: 0.7 }
  if (/例如|比如|举个例子|举例|示例如下|案例如下|如下所示|如下例|eg\.|e\.g\./.test(s)) return { type: 'example', confidence: 0.8 }
  return { type: 'knowledge', confidence: 0.6 }
}

export function classifyLevel(title, description = '', entities = []) {
  const combined = title + ' ' + description + ' ' + (entities || []).join(' ')
  for (const pattern of L1_PATTERNS) if (pattern.test(title)) return { level: 1, label: 'L1: 元概念', confidence: 0.85 }
  for (const pattern of L2_PATTERNS) if (pattern.test(title)) return { level: 2, label: 'L2: 核心理论', confidence: 0.8 }
  for (const pattern of L4_PATTERNS) if (pattern.test(title)) return { level: 4, label: 'L4: 实现/工具', confidence: 0.85 }
  const titleWords = title.split(/[\s,，、]+/).filter(Boolean)
  const descLen = (description || '').length
  if (titleWords.length <= 3 && descLen > 100) return { level: 3, label: 'L3: 具体技术', confidence: 0.5 }
  if (titleWords.length <= 2 && descLen <= 100) {
    if (/实现|使用|调用|配置|安装|部署|运行|编译|执行|代码|函数|类|接口|API|库|框架|工具/.test(combined)) return { level: 3, label: 'L3: 具体技术', confidence: 0.4 }
    return { level: 2, label: 'L2: 核心理论', confidence: 0.4 }
  }
  return { level: 3, label: 'L3: 具体技术', confidence: 0.35 }
}

export function extractFileNameContext(fileName) {
  if (!fileName) return { isQuestion: false, questionText: '', tags: [], domain: '' }
  const name = fileName.replace(/\.(md|txt|markdown)$/i, '').trim()
  const isQuestion = /[？?]/.test(name) || /为什么|怎么|如何|是否|什么/.test(name)
  const questionText = isQuestion ? name : ''
  const tags = name.split(/[_\-\s,，、]+/).filter(t => t.length >= 2 && !/^[0-9]+$/.test(t))
  let domain = ''
  if (/AI|人工智能|机器学习|深度学习|神经网络|NLP|CV|自然语言|计算机视觉/i.test(name)) domain = 'AI'
  else if (/编程|代码|开发|Java|Python|C\+\+|JavaScript|Go|Rust|前端|后端/i.test(name)) domain = '编程'
  else if (/算法|数据结构|设计模式|系统设计|架构/i.test(name)) domain = '计算机基础'
  else if (/网络|协议|TCP|HTTP|DNS|安全|密码/i.test(name)) domain = '网络与安全'
  else if (/数据库|SQL|MySQL|Redis|MongoDB|存储/i.test(name)) domain = '数据库'
  else if (/运维|DevOps|Docker|K8s|Linux|部署/i.test(name)) domain = '运维'
  else if (/写作|文章|笔记|日记|随笔/i.test(name)) domain = '写作'
  return { isQuestion, questionText, tags, domain }
}

export function parseMarkdown(content, fileName) {
  const fileContext = extractFileNameContext(fileName)
  const results = { knowledgeNodes: [], pendingNodes: [], rejectedNodes: [], questions: [], thoughts: [], examples: [], fileContext }
  if (!content || !content.trim()) return results
  const lines = content.split('\n'); let currentTitle = null; let currentBuffer = []; let currentSectionType = 'knowledge'
  function flush() {
    const text = currentBuffer.join('\n').trim()
    if (!text) { currentBuffer = []; return }
    const classification = classifySentence(text, { fileName })
    const title = currentTitle || text.slice(0, 40).replace(/\n/g, ' ')
    const desc = text.slice(0, 800)
    switch (classification.type) {
      case 'knowledge': {
        const level = classifyLevel(title, desc, [])
        const qualification = qualifyKnowledgePoint(title, desc, text, { fileName })
        const nodeData = { title, description: desc, rawText: text, type: 'markdown_section', level: level.level, levelLabel: level.label, sentenceType: classification.type, _domain: qualification.domain, _quality: qualification }
        if (qualification.qualified) results.knowledgeNodes.push(nodeData)
        else if (qualification.status === 'pending') results.pendingNodes.push(nodeData)
        else results.rejectedNodes.push(nodeData)
        break
      }
      case 'question': results.questions.push({ title, description: desc, rawText: text, type: 'question', fileContext }); break
      case 'thought': results.thoughts.push({ title, description: desc, rawText: text, type: 'thought', fileContext }); break
      case 'example': results.examples.push({ title, description: desc, rawText: text, type: 'example', fileContext }); break
      case 'meta': break
    }
    currentBuffer = []; currentTitle = null
  }
  for (const line of lines) {
    if (/^#{1,4}\s+/.test(line)) {
      flush(); currentTitle = line.replace(/^#{1,4}\s+/, '').trim()
      const titleClass = classifySentence(currentTitle, { fileName })
      currentSectionType = (titleClass.type !== 'knowledge' && titleClass.type !== 'meta') ? titleClass.type : 'knowledge'
      continue
    }
    if (/^[-*+]\s+/.test(line)) { flush(); currentTitle = line.replace(/^[-*+]\s+/, '').trim(); currentSectionType = classifySentence(currentTitle, { fileName }).type !== 'meta' ? classifySentence(currentTitle, { fileName }).type : 'knowledge'; continue }
    currentBuffer.push(line)
    if (currentBuffer.length >= 15 || (line.trim() === '' && currentBuffer.length > 3)) { const bufText = currentBuffer.join('\n'); if (/\n\s*\n/.test(bufText.slice(-100))) flush() }
  }
  flush()
  if (results.knowledgeNodes.length === 0 && results.questions.length === 0 && results.thoughts.length === 0 && content.trim()) {
    const title = fileName || '未命名文档'; const desc = content.trim().slice(0, 800); const level = classifyLevel(title, desc, [])
    results.knowledgeNodes.push({ title, description: desc, rawText: content.trim(), type: 'markdown_section', level: level.level, levelLabel: level.label, sentenceType: 'knowledge' })
  }
  return results
}

export function parseKpsFromMarkdown(content, fileName) {
  const parsed = parseMarkdown(content, fileName)
  return parsed.knowledgeNodes.map((kp, idx) => ({ id: 'kp_' + idx + '_' + Math.random().toString(36).slice(2, 6) + '_' + Date.now().toString(36), title: kp.title, description: kp.description, rawText: kp.rawText, type: kp.type || 'markdown_section', level: kp.level || 3, levelLabel: kp.levelLabel || 'L3: 具体技术', _domain: kp._domain || '', keywords: [], entities: [] }))
}

export function getLevelInfo(level) { return KNOWLEDGE_LEVELS['L' + level] || KNOWLEDGE_LEVELS.L3 }
export function getLevelShape(level) { const info = KNOWLEDGE_LEVELS['L' + level]; return info ? info.shape : 'circle' }
export function getLevelColor(level) { const info = KNOWLEDGE_LEVELS['L' + level]; return info ? info.color : '#3a7acc' }
export function getLevelBorderWidth(level) { const info = KNOWLEDGE_LEVELS['L' + level]; return info ? info.borderWidth : 1.5 }

const mdParser = { parseMarkdown, parseKpsFromMarkdown, classifySentence, classifyLevel, qualifyKnowledgePoint, extractFileNameContext, SENTENCE_TYPES, KNOWLEDGE_LEVELS, getLevelInfo, getLevelShape, getLevelColor, getLevelBorderWidth }
export default mdParser
