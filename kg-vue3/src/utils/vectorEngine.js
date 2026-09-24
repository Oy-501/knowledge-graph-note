/**
 * vectorEngine.js
 * Transformers.js 前端本地嵌入封装（CDN 全局加载）：
 *  1) 加载 all-mpnet-base-v2 模型（768 维，首次约 420MB，浏览器缓存）
 *  2) 文本 → 768 维向量（mean pooling + L2 normalize）
 *  3) 余弦相似度（已归一化即点积）
 *  4) 三级降级：transformers.js → TF-IDF 100 维 → 字符 n-gram 哈希
 *  5) 文本清洗 + 关键词 Jaccard 计算工具
 *  6) 10 秒超时自动降级
 *
 * 关键：transformers.js 通过 index.html 中的 CDN script 标签全局加载，
 * 避免静态 import 在 Vite 模块加载阶段触发 onnxruntime-web registerBackend 失败。
 */
const MODEL_NAME = 'Xenova/all-mpnet-base-v2'
const DIM = 768 // all-mpnet-base-v2 输出维度
const TFIDF_DIM = 100 // TF-IDF 降级维度
const LOAD_TIMEOUT_MS = 10000 // 10 秒超时

let _pipeline = null
let _loading = false
let _loadError = null
let _mode = 'pending' // 'pending' | 'transformers' | 'fallback-tfidf' | 'fallback-ngram'
let _tfidfVocab = null // TF-IDF 词汇表缓存

/**
 * 获取全局 transformers 对象
 * 优先使用 window.Transformers（CDN 加载）
 */
async function getTransformers() {
  if (typeof window !== 'undefined') {
    if (window.Transformers) return window.Transformers
    if (window.transformers) return window.transformers
  }
  // 等待 CDN 加载完成（最多 5 秒）
  if (typeof window !== 'undefined') {
    const start = Date.now()
    while (Date.now() - start < 5000) {
      if (window.Transformers) return window.Transformers
      if (window.transformers) return window.transformers
      await new Promise(r => setTimeout(r, 200))
    }
  }
  // 动态 import 兜底
  try {
    return await import('@xenova/transformers')
  } catch (e) {
    console.warn('[vectorEngine] dynamic import also failed:', e)
    return null
  }
}

export function isAvailable() {
  return _mode === 'transformers' && _pipeline
}

export async function ensureLoaded() {
  if (_mode === 'transformers' && _pipeline) return _pipeline
  if (_mode === 'fallback-tfidf' || _mode === 'fallback-ngram') return null
  if (_loading) {
    while (_loading) await new Promise(r => setTimeout(r, 150))
    return _pipeline
  }
  _loading = true
  try {
    const T = await getTransformers()
    if (!T || !T.pipeline) {
      throw new Error('Transformers.js global not available (CDN blocked?)')
    }
    try {
      T.env.allowLocalModels = false
      T.env.useBrowserCache = true
    } catch (e) { /* ignore */ }

    // 带超时的模型加载
    const loadPromise = T.pipeline('feature-extraction', MODEL_NAME, {
      quantized: true,
      progress_callback: (info) => {
        if (info && info.status === 'failed') {
          console.warn('[vectorEngine] model download failed', info)
        }
      }
    })
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('模型加载超时（' + LOAD_TIMEOUT_MS / 1000 + 's）')), LOAD_TIMEOUT_MS)
    )
    _pipeline = await Promise.race([loadPromise, timeoutPromise])
    _mode = 'transformers'
    console.info('[vectorEngine] transformers.js pipeline ready (dim=' + DIM + ', model=' + MODEL_NAME + ')')
  } catch (e) {
    console.error('[vectorEngine] transformers.js unavailable, fallback to TF-IDF. Reason:', e)
    _loadError = String(e && e.message || e)
    // 尝试 TF-IDF 降级
    try {
      await buildTfidfVocab()
      _mode = 'fallback-tfidf'
      console.info('[vectorEngine] TF-IDF fallback mode active (dim=' + TFIDF_DIM + ')')
    } catch (e2) {
      console.error('[vectorEngine] TF-IDF fallback also failed, using n-gram. Reason:', e2)
      _mode = 'fallback-ngram'
    }
    _pipeline = null
  } finally {
    _loading = false
  }
  return _pipeline
}

/* ========== TF-IDF 降级向量化 ========== */

/**
 * 构建 TF-IDF 词汇表（取高频词前 TFIDF_DIM 个）
 */
async function buildTfidfVocab() {
  // 预置软件术语高频词表（作为兜底词汇）
  const presetTerms = [
    'java', 'jvm', 'gc', '内存', '线程', '锁', '并发', 'spring', 'docker', 'kubernetes',
    'redis', 'kafka', 'mysql', '索引', '事务', 'http', 'tcp', 'dns', '负载均衡', '微服务',
    'api', 'restful', 'json', 'xml', 'python', 'javascript', 'typescript', 'react', 'vue',
    '算法', '数据结构', '排序', '哈希', '二叉树', '图', '递归', '动态规划', '贪心', '分治',
    '操作系统', 'linux', '内核', '进程', '虚拟内存', '缓存', '数据库', 'sql', 'nosql',
    'mongodb', '设计模式', '单例', '工厂', '观察者', '代理', '装饰器', '策略', '责任链',
    '面向对象', '封装', '继承', '多态', '接口', '抽象类', '依赖注入', '控制反转', 'aop',
    'ci', 'cd', 'devops', 'git', '容器', '编排', '服务发现', '配置中心', '鉴权', 'jwt',
    'oauth', 'session', 'cookie', 'https', 'ssl', 'tls', '加密', '签名', '证书',
    'ai', '机器学习', '深度学习', '神经网络', 'transformer', 'attention', 'embedding',
    'agent', 'llm', '大模型', '推理', '训练', '微调', 'prompt', 'rag', '向量数据库',
    '前端', '后端', '全栈', 'rest', 'graphql', 'websocket', 'grpc', '消息队列',
    '分布式', '一致性', 'cap', 'base', 'acid', 'paxos', 'raft', '选举', '复制',
    '监控', '日志', '告警', 'prometheus', 'grafana', 'elk', '链路追踪', '熔断', '降级'
  ]
  _tfidfVocab = presetTerms
  return _tfidfVocab
}

/**
 * TF-IDF 向量化：100 维
 * 对输入文本分词，计算每个词在预设词汇表中的 TF-IDF 权重
 */
function tfidfVector(text) {
  if (!_tfidfVocab) {
    _tfidfVocab = [
      'java', 'jvm', 'gc', '内存', '线程', '锁', '并发', 'spring', 'docker', 'kubernetes',
      'redis', 'kafka', 'mysql', '索引', '事务', 'http', 'tcp', 'dns', '负载均衡', '微服务',
      'api', 'restful', 'json', 'python', 'javascript', 'react', 'vue', '算法', '数据结构',
      '排序', '哈希', '二叉树', '图', '递归', '动态规划', '贪心', '操作系统', 'linux', '内核',
      '进程', '虚拟内存', '缓存', '数据库', 'sql', 'nosql', '设计模式', '单例', '工厂', '观察者',
      '代理', '装饰器', '策略', '面向对象', '封装', '继承', '多态', '接口', '抽象类', '依赖注入',
      '控制反转', 'aop', 'ci', 'cd', 'devops', 'git', '容器', '编排', '服务发现', '配置中心',
      '鉴权', 'jwt', 'oauth', 'session', 'cookie', 'https', 'ssl', 'tls', '加密', '签名',
      'ai', '机器学习', '深度学习', '神经网络', 'transformer', 'attention', 'embedding',
      'agent', 'llm', '大模型', '推理', '训练', '微调', 'prompt', 'rag', '向量数据库',
      '前端', '后端', '全栈', 'rest', 'graphql', 'websocket', 'grpc', '消息队列',
      '分布式', '一致性', 'cap', 'base', 'acid', '监控', '日志', '告警', 'prometheus'
    ]
  }
  const vec = new Float32Array(TFIDF_DIM)
  const cleaned = cleanText(text || '').toLowerCase()
  // 对每个词汇表项计算词频
  for (let i = 0; i < _tfidfVocab.length; i++) {
    const term = _tfidfVocab[i]
    // 统计 term 出现次数
    let count = 0
    let idx = cleaned.indexOf(term)
    while (idx !== -1) {
      count++
      idx = cleaned.indexOf(term, idx + term.length)
    }
    // 简单 TF: log(1 + count)
    if (count > 0) {
      vec[i] = Math.log(1 + count)
    }
  }
  // IDF 简化：高频词降权
  const totalDocs = Math.max(1, _tfidfVocab.length)
  for (let i = 0; i < _tfidfVocab.length; i++) {
    if (vec[i] > 0) {
      const idf = Math.log(totalDocs / (i + 1)) // 词汇表按频率排序，后面的词更稀有
      vec[i] *= Math.max(0.5, Math.min(3, idf))
    }
  }
  return l2Normalize(vec)
}

/* ========== n-gram 降级向量化（最终兜底） ========== */

function tokenizeNgram(text) {
  const cleaned = cleanText(text).toLowerCase()
  const out = []
  const words = cleaned.match(/[a-z][a-z0-9_-]{1,32}/g) || []
  for (let i = 0; i < words.length; i++) {
    out.push(words[i])
    if (i < words.length - 1) out.push(words[i] + '_' + words[i + 1])
  }
  const cjk = cleaned.match(/[\u4e00-\u9fa5]+/g) || []
  for (const seg of cjk) {
    for (let i = 0; i < seg.length - 1; i++) {
      out.push(seg.substring(i, i + 2))
    }
  }
  return out
}

function ngramVector(text) {
  const vec = new Float32Array(DIM)
  const tokens = tokenizeNgram(text)
  if (tokens.length === 0) return vec
  for (const tk of tokens) {
    let h = 0
    for (let i = 0; i < tk.length; i++) {
      h = (h * 16777619 ^ tk.charCodeAt(i)) >>> 0
    }
    const idx = h % DIM
    const sign = ((h >> 16) & 1) ? 1 : -1
    vec[idx] += sign
  }
  return l2Normalize(vec)
}

/* ========== 核心 API ========== */

function meanPool(output, length) {
  const out = new Float32Array(DIM)
  for (let i = 0; i < length; i++) {
    for (let j = 0; j < DIM; j++) {
      out[j] += output[i * DIM + j]
    }
  }
  for (let j = 0; j < DIM; j++) out[j] /= length || 1
  return out
}

function l2Normalize(vec) {
  let norm = 0
  for (let i = 0; i < vec.length; i++) norm += vec[i] * vec[i]
  norm = Math.sqrt(norm) || 1e-9
  for (let i = 0; i < vec.length; i++) vec[i] = vec[i] / norm
  return vec
}

/**
 * 文本转向量
 * @param {string} text
 * @returns {Promise<Float32Array|null>}
 */
export async function embed(text) {
  await ensureLoaded()
  const cleaned = cleanText(text || '')
  if (isAvailable()) {
    try {
      const out = await _pipeline(cleaned, { pooling: 'mean', normalize: true })
      const data = out.data || out.tolist?.()[0] || out
      const f32 = data instanceof Float32Array ? data : new Float32Array(data)
      // 确保维度正确
      if (f32.length === DIM) return f32
      // 如果维度不匹配，裁剪或填充
      if (f32.length > DIM) return f32.slice(0, DIM)
      const padded = new Float32Array(DIM)
      padded.set(f32)
      return padded
    } catch (e) {
      console.warn('[vectorEngine] embed via transformers failed, fallback:', e)
    }
  }
  if (_mode === 'fallback-tfidf') {
    return tfidfVector(cleaned)
  }
  return ngramVector(cleaned)
}

/**
 * 批量文本转向量（按顺序 await，避免内存峰值）
 */
export async function embedBatch(texts, onProgress) {
  const out = new Array(texts.length)
  for (let i = 0; i < texts.length; i++) {
    out[i] = await embed(texts[i])
    onProgress && onProgress(i + 1)
  }
  return out
}

export function cosine(a, b) {
  if (!a || !b || a.length !== b.length) return 0
  let dot = 0, na = 0, nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  na = Math.sqrt(na) || 1e-9
  nb = Math.sqrt(nb) || 1e-9
  return dot / (na * nb)
}

/* ========== 文本处理工具 ========== */

export function cleanText(s) {
  if (!s) return ''
  return String(s)
    .replace(/^\uFEFF/, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+$/gm, '')
    .trim()
}

const STOPWORDS = new Set([
  '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'of', 'in', 'on', 'at', 'and', 'or', 'to', 'for', 'with', 'as', 'by', 'this', 'that', 'it', 'from', 'but', 'not', 'they', 'we', 'you', 'i'
])

export function extractKeywords(text) {
  if (!text) return []
  const cleaned = cleanText(text).toLowerCase()
  const tokens = cleaned.match(/[a-z][a-z0-9_-]{1,32}|[\u4e00-\u9fa5]{2,8}/g) || []
  const map = new Map()
  for (const t of tokens) {
    if (STOPWORDS.has(t)) continue
    if (t.length < 2) continue
    map.set(t, (map.get(t) || 0) + 1)
  }
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 16)
    .map(([k]) => k)
}

export function jaccard(setA, setB) {
  if (!setA || !setB || setA.length === 0 || setB.length === 0) return 0
  const sa = new Set(setA), sb = new Set(setB)
  let inter = 0
  for (const x of sa) if (sb.has(x)) inter++
  const union = sa.size + sb.size - inter
  return union === 0 ? 0 : inter / union
}

export function tfidfWeight(setA, setB) {
  return jaccard(setA, setB)
}

export function getEngineInfo() {
  return {
    mode: _mode,
    dim: _mode === 'fallback-tfidf' ? TFIDF_DIM : DIM,
    model: MODEL_NAME,
    error: _loadError,
    fallbackType: _mode === 'fallback-tfidf' ? 'TF-IDF (100维)' : (_mode === 'fallback-ngram' ? 'n-gram 哈希' : null)
  }
}

const vectorEngine = {
  embed, embedBatch, cosine,
  cleanText, extractKeywords, jaccard, tfidfWeight,
  ensureLoaded, isAvailable, getEngineInfo
}
export default vectorEngine