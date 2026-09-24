/**
 * mdParser.js
 * 知识深度层次识别与文件解析引擎
 *
 * 功能：
 *  1. 句子类型分类（knowledge / question / thought / example / meta）
 *  2. 知识点资格审核（话语类型+信息密度+领域确定性+置信度）
 *  3. 知识点深度分级（L1-L4）
 *  4. 文件名作为"问题入口"而非内容
 *  5. 思考/问题独立存储，不混入知识图谱
 */

import { RealtimeValidator } from './noteValidator'

// 全局校验器实例
const _validator = new RealtimeValidator()

// === 句子类型分类 ===
export const SENTENCE_TYPES = {
  knowledge: { code: 'knowledge', label: '知识点陈述', entersGraph: true },
  question:  { code: 'question',  label: '疑问/问题', entersGraph: false },
  thought:   { code: 'thought',   label: '思考/反思', entersGraph: false },
  example:   { code: 'example',   label: '示例/用例', entersGraph: false },
  meta:      { code: 'meta',      label: '元信息',    entersGraph: false }
}

// === 软件工程子领域映射（用于知识点资格审核的第3维：领域确定性）===
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

// 软件术语关键词（用于信息密度检测）
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
  'ssl', 'tls', 'https', 'oauth2', 'saml', 'openid', 'kerberos', 'ldap',
  'ide', 'vscode', 'intellij', 'eclipse', 'vim', 'emacs', '终端', 'shell', 'bash',
  'url', 'uri', 'html', 'css', 'dom', 'svg', 'canvas', 'webgl', 'wasm',
  '正则', 'regex', 'sql', 'orm', 'acid', 'base', 'cap', 'paxos', 'raft',
  'jwt', 'rpc', 'grpc', 'websocket', 'mqtt', 'amqp', 'kafka', 'rabbitmq',
  '微服务', '单体', 'soa', 'eda', 'cqrs', 'es', 'saga', 'bff', 'api网关'
])

/**
 * 知识点资格审核（阶段1：该不该成为节点）
 * 审核四个维度：话语类型、信息密度、领域确定性、置信度
 * @param {string} title - 知识点标题
 * @param {string} description - 知识点描述
 * @param {string} rawText - 原始文本
 * @param {Object} context - 上下文信息
 * @returns {{qualified: boolean, reason: string, status: string, confidence: number, domain: string}}
 */
export function qualifyKnowledgePoint(title, description = '', rawText = '', context = {}) {
  const combined = (title + ' ' + description + ' ' + rawText).trim()

  // === 维度1：话语类型 ===
  const classification = classifySentence(rawText || title, context)
  if (classification.type !== 'knowledge') {
    return { qualified: false, reason: 'discard_as_thought', status: 'rejected',
      detail: `话语类型为"${classification.type}"，非知识点陈述`, confidence: classification.confidence, domain: '' }
  }

  // === 维度2：信息密度 ===
  // 必须包含至少 2 个术语/关键词 + 表达完整含义（≥5个汉字）
  const chineseChars = (combined.match(/[\u4e00-\u9fff]/g) || []).length
  const englishWords = (combined.match(/[a-zA-Z]{2,}/g) || []).length
  const totalWords = chineseChars + englishWords
  if (totalWords < 5) {
    return { qualified: false, reason: 'discard_as_fragment', status: 'rejected',
      detail: `信息密度不足（仅${totalWords}个有效字符），无法表达完整含义`, confidence: 0.3, domain: '' }
  }

  // 统计术语数量
  const lowerText = combined.toLowerCase()
  let termCount = 0
  const foundTerms = []
  for (const term of SOFTWARE_TERMS) {
    if (lowerText.includes(term.toLowerCase())) {
      termCount++
      foundTerms.push(term)
      if (termCount >= 2) break
    }
  }
  if (termCount < 2 && totalWords < 15) {
    return { qualified: false, reason: 'discard_as_fragment', status: 'rejected',
      detail: `信息密度不足（仅${termCount}个术语），可能为碎片化内容`, confidence: 0.35, domain: '' }
  }

  // === 维度3：领域确定性 ===
  let bestDomain = ''
  let bestDomainScore = 0
  for (const [domain, keywords] of Object.entries(SOFTWARE_DOMAINS)) {
    let score = 0
    for (const kw of keywords) {
      if (lowerText.includes(kw)) score++
    }
    if (score > bestDomainScore) {
      bestDomainScore = score
      bestDomain = domain
    }
  }
  if (bestDomainScore === 0) {
    // 无法明确归属 → 标记为未分类，不进入主图谱
    return { qualified: false, reason: 'mark_as_unclassified', status: 'pending',
      detail: '无法明确归属到任何软件工程子领域', confidence: 0.2, domain: '' }
  }

  // === 维度4：置信度阈值 ===
  const confidence = Math.min(0.95, 0.4 + bestDomainScore * 0.15 + termCount * 0.05 + (totalWords >= 20 ? 0.1 : 0))
  if (confidence < 0.6) {
    return { qualified: false, reason: 'mark_low_confidence', status: 'pending',
      detail: `置信度 ${confidence.toFixed(2)} < 0.6，进入待定池`, confidence, domain: bestDomain }
  }

  // === 维度5：知识校验（笔记校验引擎）===
  const validationIssues = _validator.validateSentence(rawText || title, context)
  const hasErrors = validationIssues.some(i => i.severity === 'error')
  const hasWarnings = validationIssues.some(i => i.severity === 'warning')

  return {
    qualified: true,
    reason: hasErrors ? 'with_validation_errors' : (hasWarnings ? 'with_validation_warnings' : ''),
    status: 'qualified',
    detail: `通过审核：话语类型=知识陈述，术语数=${termCount}，领域=${bestDomain}，置信度=${confidence.toFixed(2)}`,
    confidence,
    domain: bestDomain,
    validationIssues: validationIssues.length > 0 ? validationIssues : undefined,
    hasErrors,
    hasWarnings
  }
}

// === 知识深度层级 ===
export const KNOWLEDGE_LEVELS = {
  L1: { level: 1, label: '元概念',   desc: '最抽象的顶层概念', examples: ['AI', '编程', '算法', '软件工程'], shape: 'hexagon', color: '#1a3a5c', borderWidth: 3 },
  L2: { level: 2, label: '核心理论', desc: '理论框架、核心原理', examples: ['机器学习', '数据结构', '操作系统', '计算机网络'], shape: 'rounded', color: '#2a5a9c', borderWidth: 2 },
  L3: { level: 3, label: '具体技术', desc: '可落地实现的具体技术', examples: ['神经网络', '哈希表', 'TCP协议', '虚拟内存'], shape: 'circle', color: '#3a7acc', borderWidth: 1.5 },
  L4: { level: 4, label: '实现/工具', desc: '具体代码、框架、工具', examples: ['PyTorch', 'HashMap', 'Redis', 'Docker'], shape: 'diamond', color: '#4a9a6c', borderWidth: 1 }
}

// L1 元概念关键词（强信号）
const L1_PATTERNS = [
  /^AI$/i, /^人工智能$/i, /^编程$/i, /^算法$/i, /^软件工程$/i,
  /^计算机科学$/i, /^数学$/i, /^物理学$/i, /^语言学$/i, /^哲学$/i,
  /^操作系统$/i, /^计算机网络$/i, /^数据库$/i, /^编译原理$/i,
  /^机器学习$/i, /^深度学习$/i, /^自然语言处理$/i, /^计算机视觉$/i,
  /^分布式系统$/i, /^云计算$/i, /^网络安全$/i, /^密码学$/i,
  /^前端开发$/i, /^后端开发$/i, /^移动开发$/i, /^嵌入式开发$/i
]

// L2 核心理论关键词
const L2_PATTERNS = [
  /^(数据结构|算法设计|面向对象|函数式编程|并发编程|设计模式)$/i,
  /^(线性代数|概率论|统计学|微积分|离散数学|图论)$/i,
  /^(编译原理|操作系统|计算机网络|计算机组成|数据库系统)$/i,
  /^(机器学习|深度学习|强化学习|迁移学习|联邦学习)$/i,
  /^(软件架构|微服务|领域驱动设计|测试驱动开发)$/i,
  /^(密码学|网络协议|分布式理论|CAP理论|一致性算法)$/i,
  /^(内存管理|进程调度|文件系统|I\/O模型|虚拟化)$/i
]

// L4 实现/工具关键词
const L4_PATTERNS = [
  /^(PyTorch|TensorFlow|Keras|Scikit-learn|Pandas|NumPy|Matplotlib|Jupyter)$/i,
  /^(React|Vue|Angular|Svelte|Next\.js|Nuxt|Vite|Webpack|Babel|ESLint)$/i,
  /^(Spring|Django|Flask|Express|FastAPI|Gin|Koa|Rails|Laravel)$/i,
  /^(Docker|Kubernetes|Jenkins|GitLab CI|GitHub Actions|Terraform|Ansible)$/i,
  /^(MySQL|PostgreSQL|MongoDB|Redis|Elasticsearch|Cassandra|Neo4j|SQLite)$/i,
  /^(HashMap|ArrayList|LinkedList|TreeMap|ConcurrentHashMap|BloomFilter)$/i,
  /^(Nginx|Apache|HAProxy|Envoy|Traefik|Caddy)$/i,
  /^(Git|SVN|Mercurial|Figma|Postman|Swagger|GraphQL|gRPC|Thrift)$/i
]

/**
 * 句子类型分类
 * @param {string} sentence - 原始句子
 * @param {Object} context - 上下文信息（可选）
 * @returns {{type: string, confidence: number}}
 */
export function classifySentence(sentence, context = {}) {
  if (!sentence || !sentence.trim()) return { type: 'meta', confidence: 1 }

  const s = sentence.trim()

  // 1. 元信息检测：纯标题、时间戳、作者等
  if (/^[#]{1,4}\s/.test(s) || /^\d{4}[-/]\d{2}[-/]\d{2}/.test(s) ||
      /^作者[：:]/.test(s) || /^创建时间[：:]/.test(s) || /^更新时间[：:]/.test(s)) {
    return { type: 'meta', confidence: 0.95 }
  }

  // 2. 疑问词检测
  if (/为什么|怎么[做样]|如何|是否|能不能|可以吗|对吗|是什么|什么意思|啥意思|咋/.test(s)) {
    return { type: 'question', confidence: 0.9 }
  }

  // 3. 疑问句结尾检测
  if (/[？?]$/.test(s) || /吗[？?]?$/.test(s) || /呢[？?]?$/.test(s)) {
    return { type: 'question', confidence: 0.85 }
  }

  // 4. 主观思考检测
  if (/我觉得|我认为|感觉|可能|也许|大概|似乎|好像|不知道|不懂|搞不懂|不明白|不太清楚|不清楚/.test(s)) {
    return { type: 'thought', confidence: 0.75 }
  }
  if (/我想|我猜|我怀疑|我困惑|我迷茫|我不确定/.test(s)) {
    return { type: 'thought', confidence: 0.7 }
  }

  // 5. 示例/用例检测
  if (/例如|比如|举个例子|举例|示例如下|案例如下|如下所示|如下例|eg\.|e\.g\./.test(s)) {
    return { type: 'example', confidence: 0.8 }
  }

  // 6. 默认：知识点陈述
  return { type: 'knowledge', confidence: 0.6 }
}

/**
 * 判断知识点的深度层级
 * @param {string} title - 知识点标题
 * @param {string} description - 知识点描述
 * @param {Array} entities - 实体列表
 * @returns {{level: number, label: string, confidence: number}}
 */
export function classifyLevel(title, description = '', entities = []) {
  const combined = title + ' ' + description + ' ' + (entities || []).join(' ')

  // 检查 L1 元概念
  for (const pattern of L1_PATTERNS) {
    if (pattern.test(title)) {
      return { level: 1, label: 'L1: 元概念', confidence: 0.85 }
    }
  }

  // 检查 L2 核心理论
  for (const pattern of L2_PATTERNS) {
    if (pattern.test(title)) {
      return { level: 2, label: 'L2: 核心理论', confidence: 0.8 }
    }
  }

  // 检查 L4 实现/工具
  for (const pattern of L4_PATTERNS) {
    if (pattern.test(title)) {
      return { level: 4, label: 'L4: 实现/工具', confidence: 0.85 }
    }
  }

  // 基于标题长度和描述深度推断
  const titleWords = title.split(/[\s,，、]+/).filter(Boolean)
  const descLen = (description || '').length

  // 短标题 + 长描述 → 可能是 L3（具体技术）
  if (titleWords.length <= 3 && descLen > 100) {
    return { level: 3, label: 'L3: 具体技术', confidence: 0.5 }
  }

  // 短标题 + 短描述 → 可能是 L1 或 L2（抽象概念）
  if (titleWords.length <= 2 && descLen <= 100) {
    // 检查是否包含实现词汇
    if (/实现|使用|调用|配置|安装|部署|运行|编译|执行|代码|函数|类|接口|API|库|框架|工具/.test(combined)) {
      return { level: 3, label: 'L3: 具体技术', confidence: 0.4 }
    }
    return { level: 2, label: 'L2: 核心理论', confidence: 0.4 }
  }

  // 默认：L3 具体技术
  return { level: 3, label: 'L3: 具体技术', confidence: 0.35 }
}

/**
 * 从文件名提取问题上下文
 * 文件名反映的是用户关注的问题域，而非文件内的知识内容
 * @param {string} fileName - 文件名
 * @returns {{isQuestion: boolean, questionText: string, tags: string[], domain: string}}
 */
export function extractFileNameContext(fileName) {
  if (!fileName) return { isQuestion: false, questionText: '', tags: [], domain: '' }

  const name = fileName.replace(/\.(md|txt|markdown)$/i, '').trim()

  // 检测文件名是否包含问题
  const isQuestion = /[？?]/.test(name) || /为什么|怎么|如何|是否|什么/.test(name)
  const questionText = isQuestion ? name : ''

  // 提取标签（文件名中的关键词）
  const tags = name.split(/[_\-\s,，、]+/).filter(t => t.length >= 2 && !/^[0-9]+$/.test(t))

  // 推断领域
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

/**
 * 完整的 Markdown 解析器
 * 解析文件内容，区分知识点、问题、思考、示例
 * @param {string} content - 文件正文内容
 * @param {string} fileName - 文件名（仅用于元数据上下文，不参与内容解析）
 * @returns {Object} { knowledgeNodes, questions, thoughts, examples, fileContext }
 */
export function parseMarkdown(content, fileName) {
  const fileContext = extractFileNameContext(fileName)

  const results = {
    knowledgeNodes: [],
    pendingNodes: [],   // 待定池：低置信度或未分类的知识点
    rejectedNodes: [],  // 被拒绝的知识点（碎片/思考等）
    questions: [],
    thoughts: [],
    examples: [],
    fileContext
  }

  if (!content || !content.trim()) return results

  const lines = content.split('\n')
  let currentTitle = null
  let currentBuffer = []
  let currentSectionType = 'knowledge' // 当前段落的句子类型

  /**
   * 将缓冲区内容落盘为一个知识点或条目
   */
  function flush() {
    const text = currentBuffer.join('\n').trim()
    if (!text) {
      currentBuffer = []
      return
    }

    const classification = classifySentence(text, { fileName })
    const title = currentTitle || text.slice(0, 40).replace(/\n/g, ' ')
    const desc = text.slice(0, 800)

    switch (classification.type) {
      case 'knowledge': {
        const level = classifyLevel(title, desc, [])
        const qualification = qualifyKnowledgePoint(title, desc, text, { fileName })
        const nodeData = {
          title,
          description: desc,
          rawText: text,
          type: 'markdown_section',
          level: level.level,
          levelLabel: level.label,
          sentenceType: classification.type,
          _domain: qualification.domain,
          _quality: qualification
        }
        if (qualification.qualified) {
          results.knowledgeNodes.push(nodeData)
        } else if (qualification.status === 'pending') {
          results.pendingNodes.push(nodeData)
        } else {
          results.rejectedNodes.push(nodeData)
        }
        break
      }
      case 'question':
        results.questions.push({
          title,
          description: desc,
          rawText: text,
          type: 'question',
          fileContext
        })
        break
      case 'thought':
        results.thoughts.push({
          title,
          description: desc,
          rawText: text,
          type: 'thought',
          fileContext
        })
        break
      case 'example':
        results.examples.push({
          title,
          description: desc,
          rawText: text,
          type: 'example',
          fileContext
        })
        break
      case 'meta':
        // 元信息不存储
        break
    }

    currentBuffer = []
    currentTitle = null
  }

  for (const line of lines) {
    // 检测 markdown 标题
    if (/^#{1,4}\s+/.test(line)) {
      flush()
      currentTitle = line.replace(/^#{1,4}\s+/, '').trim()
      // 标题本身也要分类
      const titleClass = classifySentence(currentTitle, { fileName })
      if (titleClass.type !== 'knowledge' && titleClass.type !== 'meta') {
        // 如果标题是问题或思考，整个段落可能是同类型
        currentSectionType = titleClass.type
      } else {
        currentSectionType = 'knowledge'
      }
      continue
    }

    // 检测列表项
    if (/^[-*+]\s+/.test(line)) {
      flush()
      currentTitle = line.replace(/^[-*+]\s+/, '').trim()
      const itemClass = classifySentence(currentTitle, { fileName })
      currentSectionType = itemClass.type !== 'meta' ? itemClass.type : 'knowledge'
      continue
    }

    currentBuffer.push(line)

    // 缓冲区达到一定大小时，按空行分块
    if (currentBuffer.length >= 15 || (line.trim() === '' && currentBuffer.length > 3)) {
      // 检查是否是一个完整的段落
      const bufText = currentBuffer.join('\n')
      if (/\n\s*\n/.test(bufText.slice(-100))) {
        flush()
      }
    }
  }

  // 处理最后一段
  flush()

  // 兜底：如果没解析出任何内容，且文件有内容，将整篇作为泛知识节点
  if (results.knowledgeNodes.length === 0 && results.questions.length === 0 &&
      results.thoughts.length === 0 && content.trim()) {
    const title = fileName || '未命名文档'
    const desc = content.trim().slice(0, 800)
    const level = classifyLevel(title, desc, [])
    results.knowledgeNodes.push({
      title,
      description: desc,
      rawText: content.trim(),
      type: 'markdown_section',
      level: level.level,
      levelLabel: level.label,
      sentenceType: 'knowledge'
    })
  }

  return results
}

/**
 * 兼容旧接口：仅提取知识点（保持向后兼容）
 * @param {string} content - 文件内容
 * @param {string} fileName - 文件名
 * @returns {Array} 知识点数组
 */
export function parseKpsFromMarkdown(content, fileName) {
  const parsed = parseMarkdown(content, fileName)
  return parsed.knowledgeNodes.map((kp, idx) => ({
    id: 'kp_' + idx + '_' + Math.random().toString(36).slice(2, 6) + '_' + Date.now().toString(36),
    title: kp.title,
    description: kp.description,
    rawText: kp.rawText,
    type: kp.type || 'markdown_section',
    level: kp.level || 3,
    levelLabel: kp.levelLabel || 'L3: 具体技术',
    _domain: kp._domain || '',
    keywords: [],
    entities: []
  }))
}

/**
 * 获取知识层级定义
 */
export function getLevelInfo(level) {
  return KNOWLEDGE_LEVELS['L' + level] || KNOWLEDGE_LEVELS.L3
}

/**
 * 获取层级对应的节点形状
 */
export function getLevelShape(level) {
  const info = KNOWLEDGE_LEVELS['L' + level]
  return info ? info.shape : 'circle'
}

/**
 * 获取层级对应的颜色
 */
export function getLevelColor(level) {
  const info = KNOWLEDGE_LEVELS['L' + level]
  return info ? info.color : '#3a7acc'
}

/**
 * 获取层级对应的边框宽度
 */
export function getLevelBorderWidth(level) {
  const info = KNOWLEDGE_LEVELS['L' + level]
  return info ? info.borderWidth : 1.5
}

const mdParser = {
  parseMarkdown, parseKpsFromMarkdown,
  classifySentence, classifyLevel, qualifyKnowledgePoint, extractFileNameContext,
  SENTENCE_TYPES, KNOWLEDGE_LEVELS,
  getLevelInfo, getLevelShape, getLevelColor, getLevelBorderWidth
}
export default mdParser