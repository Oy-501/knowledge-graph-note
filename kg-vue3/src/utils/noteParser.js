/**
 * noteParser.js
 * 笔记内容实时解析器：术语提取、知识点匹配、关系推断
 *
 * 核心功能：
 *  1. 从 Markdown 文本中实时提取术语/概念
 *  2. 与现有图谱节点进行匹配
 *  3. 检测文本中的关系表述
 */

// 常见软件工程术语（用于轻量级匹配，避免每次都调向量引擎）
const COMMON_TERMS = [
  'JVM', 'JDK', 'JRE', 'Java', 'Python', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'C++', 'C#',
  'Spring', 'Spring Boot', 'MyBatis', 'Hibernate', 'Django', 'Flask', 'React', 'Vue', 'Angular',
  'Docker', 'Kubernetes', 'K8s', 'Nginx', 'Apache', 'Tomcat', 'Jenkins', 'GitLab', 'GitHub',
  'Redis', 'MySQL', 'PostgreSQL', 'MongoDB', 'Elasticsearch', 'RabbitMQ', 'Kafka',
  'HTTP', 'HTTPS', 'TCP', 'UDP', 'IP', 'DNS', 'REST', 'GraphQL', 'WebSocket', 'gRPC',
  'OOP', 'AOP', 'IOC', 'DI', 'MVC', 'MVVM', '微服务', '分布式', '高并发', '高可用',
  '堆内存', '栈内存', '方法区', '元空间', '垃圾回收', 'GC', 'Full GC', 'Minor GC',
  '类加载', '字节码', '编译', '解释', 'JIT', 'AOT',
  '进程', '线程', '协程', '锁', '死锁', '并发', '并行', '异步', '同步',
  '算法', '数据结构', '哈希表', '链表', '二叉树', '图', '排序', '搜索',
  '设计模式', '单例', '工厂', '观察者', '策略', '代理',
  'AI', '机器学习', '深度学习', '神经网络', 'NLP', 'Transformer', 'Agent', '智能体',
  '操作系统', 'Linux', '内核', '调度', '内存管理', '文件系统',
  '数据库', '索引', '事务', 'ACID', '持久化', '缓存', '读写分离', '分库分表',
  'API', 'SDK', 'CLI', 'CI/CD', 'DevOps', '敏捷', 'Scrum', '瀑布',
  '前端', '后端', '全栈', '架构', '微内核', '插件化', '模块化',
  '安全', '加密', '认证', '授权', 'OAuth', 'JWT', 'HTTPS', 'SSL/TLS'
]

// 关系关键词
const RELATION_KEYWORDS = {
  '包含': { type: 'contains', icon: '⊂', label: '包含' },
  '属于': { type: 'belongs_to', icon: '∈', label: '属于' },
  '依赖': { type: 'depends', icon: '→', icon: '→', label: '依赖' },
  '需要': { type: 'depends', icon: '→', label: '依赖' },
  '基于': { type: 'based_on', icon: '⇢', label: '基于' },
  '实现': { type: 'implements', icon: '⇒', label: '实现' },
  '对比': { type: 'comparison', icon: '⇔', label: '对比' },
  '不同于': { type: 'comparison', icon: '⇔', label: '对比' },
  '类似': { type: 'similar', icon: '≈', label: '类似' },
  '替代': { type: 'replaces', icon: '↻', label: '替代' },
  '调用': { type: 'calls', icon: '→', label: '调用' },
  '构成': { type: 'composes', icon: '⊆', label: '构成' },
  '组成': { type: 'composes', icon: '⊆', label: '组成' },
  '扩展': { type: 'extends', icon: '↗', label: '扩展' },
  '继承': { type: 'extends', icon: '↗', label: '继承' }
}

/**
 * 从文本中提取术语
 * @param {string} text - 输入文本
 * @returns {Array<{term: string, position: number, length: number}>}
 */
export function extractTerms(text) {
  const terms = []
  const lowerText = text.toLowerCase()

  for (const term of COMMON_TERMS) {
    const lowerTerm = term.toLowerCase()
    let pos = 0
    while ((pos = lowerText.indexOf(lowerTerm, pos)) !== -1) {
      // 确保是完整词边界
      const before = pos > 0 ? lowerText[pos - 1] : ' '
      const after = pos + lowerTerm.length < lowerText.length ? lowerText[pos + lowerTerm.length] : ' '
      if (/\W/.test(before) && /\W/.test(after)) {
        terms.push({ term, position: pos, length: term.length })
      }
      pos += lowerTerm.length
    }
  }

  // 去重并按位置排序
  const seen = new Set()
  return terms
    .filter(t => {
      const k = `${t.term}:${t.position}`
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
    .sort((a, b) => a.position - b.position)
}

/**
 * 匹配图谱中的已有节点
 * @param {Array} terms - 提取的术语列表
 * @param {Array} graphNodes - 图谱中的节点列表
 * @returns {Array} 匹配到的节点列表
 */
export function matchGraphNodes(terms, graphNodes) {
  if (!terms.length || !graphNodes.length) return []

  const matched = []
  const matchedIds = new Set()

  for (const { term } of terms) {
    const lowerTerm = term.toLowerCase()
    for (const node of graphNodes) {
      if (node.validate?.status === 'discarded') continue
      if (matchedIds.has(node.id)) continue

      const nodeText = (node.title + ' ' + (node.description || '')).toLowerCase()
      const nodeKeywords = (node.keywords || []).map(k => k.toLowerCase())
      const nodeEntities = (node.entities || []).map(e => e.toLowerCase())

      // 精确匹配标题
      if (node.title && node.title.toLowerCase() === lowerTerm) {
        matched.push({ node, matchType: 'exact_title', term })
        matchedIds.add(node.id)
        continue
      }

      // 标题包含
      if (node.title && node.title.toLowerCase().includes(lowerTerm)) {
        matched.push({ node, matchType: 'title_contains', term })
        matchedIds.add(node.id)
        continue
      }

      // 关键词/实体匹配
      if (nodeKeywords.includes(lowerTerm) || nodeEntities.includes(lowerTerm)) {
        matched.push({ node, matchType: 'keyword_match', term })
        matchedIds.add(node.id)
        continue
      }

      // 描述包含
      if (nodeText.includes(lowerTerm) && lowerTerm.length > 3) {
        matched.push({ node, matchType: 'description_contains', term })
        matchedIds.add(node.id)
      }
    }
  }

  return matched
}

/**
 * 提取文本中的关系表述
 * @param {string} text - 输入文本
 * @returns {Array<{source: string, target: string, relation: object, evidence: string}>}
 */
export function extractRelations(text) {
  const relations = []
  const terms = extractTerms(text)

  if (terms.length < 2) return relations

  const lowerText = text.toLowerCase()

  for (const [keyword, relInfo] of Object.entries(RELATION_KEYWORDS)) {
    const pos = lowerText.indexOf(keyword)
    if (pos === -1) continue

    // 在关键词前后找术语
    const beforeTerms = terms.filter(t => t.position + t.length <= pos)
    const afterTerms = terms.filter(t => t.position >= pos + keyword.length)

    if (beforeTerms.length > 0 && afterTerms.length > 0) {
      const source = beforeTerms[beforeTerms.length - 1].term
      const target = afterTerms[0].term

      // 提取证据原文（关键词前后各20字）
      const evidenceStart = Math.max(0, pos - 30)
      const evidenceEnd = Math.min(text.length, pos + keyword.length + 30)
      const evidence = text.slice(evidenceStart, evidenceEnd).trim()

      relations.push({
        source,
        target,
        relation: relInfo,
        evidence
      })
    }
  }

  return relations
}

/**
 * 解析 Markdown 内容，提取摘要
 * @param {string} content - Markdown 内容
 * @returns {{summary: string, headings: Array, paragraphCount: number}}
 */
export function parseMarkdownSummary(content) {
  if (!content) return { summary: '', headings: [], paragraphCount: 0 }

  const lines = content.split('\n')
  const headings = []
  let paragraphCount = 0

  for (const line of lines) {
    const trimmed = line.trim()
    if (/^#{1,4}\s+/.test(trimmed)) {
      headings.push(trimmed.replace(/^#+\s+/, ''))
    } else if (trimmed.length > 10) {
      paragraphCount++
    }
  }

  const summary = headings.length > 0 ? headings.join(' · ') : content.slice(0, 100)

  return { summary, headings, paragraphCount }
}

/**
 * 提取文本中的标签
 * @param {string} content
 * @returns {Array<string>}
 */
export function extractTags(content) {
  if (!content) return []
  const tags = []
  const tagRegex = /#[\u4e00-\u9fa5\w]+/g
  let match
  while ((match = tagRegex.exec(content)) !== null) {
    const tag = match[0].replace(/^#/, '').trim()
    if (tag.length > 1 && tag.length < 30 && !tags.includes(tag)) {
      tags.push(tag)
    }
  }
  return tags
}