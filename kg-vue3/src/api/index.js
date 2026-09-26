/**
 * API 服务层
 * 封装所有后端接口调用，替换前端本地计算逻辑
 */

import axios from 'axios'
import { reportClientError } from '@/utils/errorReporter'

// 默认与后端实际端口一致，且用 127.0.0.1 而非 localhost：
// 浏览器可能把 localhost 解析成 IPv6 ::1，而后端只绑 IPv4 回环 → 全部请求失败。
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8080/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000 // 推理可能较慢，放宽超时
})

// 幂等重试的默认开关：只重试 GET（无副作用），最多 1 次
const RETRY_MAX = 1
const RETRY_DELAY_MS = 600
// 这些路径即便失败也不重试、不上报（避免错误处理自身形成风暴）
const NO_RETRY_PATHS = ['/system/client-error']

/**
 * 统一的错误对象。
 * 保留 status / hint / requestId，让调用方能区分「网络断了」和「参数错了」，
 * 而不是所有失败都退化成一个无法判断的字符串。
 */
export class ApiError extends Error {
  constructor(message, { status = 0, hint = '', requestId = '', code = '', url = '' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.hint = hint
    this.requestId = requestId
    this.code = code
    this.url = url
    /** 面向用户的完整提示：原因 + 下一步怎么做 */
    this.fullMessage = hint ? `${message}（${hint}）` : message
  }
  get isNetwork() { return this.status === 0 }
  get isServerError() { return this.status >= 500 }
  get isGuard() { return this.status === 400 || this.status === 413 || this.status === 415 || this.status === 422 }
}

/** 把各种失败形态翻译成 ApiError */
function toApiError(err) {
  const cfgUrl = err.config?.url || ''
  const res = err.response
  const data = res?.data || {}

  // 后端统一错误体：{ ok:false, error:{ code, message, hint, request_id } }
  const backendErr = data.error || {}
  // 兼容老格式 { detail: "..." }，以及 422 的 fields 明细
  const detailText = typeof data.detail === 'string' ? data.detail : ''

  if (!res) {
    // 没有响应 → 网络层问题
    if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
      return new ApiError('请求超时', {
        status: 0, url: cfgUrl, code: 'timeout',
        hint: '数据量可能较大或后端正在重建关联；可稍后重试，或先减少筛选范围。'
      })
    }
    return new ApiError('无法连接后端服务', {
      status: 0, url: cfgUrl, code: 'unreachable',
      hint: '请确认后端已启动（启动服务.bat），且端口与前端 VITE_API_BASE 一致。'
    })
  }

  const message = backendErr.message || detailText || `请求失败（HTTP ${res.status}）`
  let hint = backendErr.hint || ''

  // 后端没给建议时，按状态码补一条通用但可执行的
  if (!hint) {
    if (res.status === 401 || res.status === 403) {
      hint = '管理口令不正确或已失效，请在「后台管理」重新输入。'
    } else if (res.status === 404) {
      hint = '目标不存在或已被删除，刷新列表后重试。'
    } else if (res.status === 413) {
      hint = '文件超出上限，请拆分后分批上传。'
    } else if (res.status === 422) {
      const fields = data.error?.detail?.fields
      if (Array.isArray(fields) && fields.length) {
        hint = '字段问题：' + fields.map(f => `${f.field} ${f.issue}`).join('；')
      } else {
        hint = '请求参数不合法，请检查输入内容。'
      }
    } else if (res.status >= 500) {
      hint = '服务端异常，现场已记录；可带 request_id 到「后台管理 → 操作审计」查看详情。'
    }
  }

  return new ApiError(message, {
    status: res.status,
    hint,
    requestId: backendErr.request_id || res.headers?.['x-request-id'] || '',
    code: backendErr.code || '',
    url: cfgUrl
  })
}

// 后台口令在本地的存储键（与 AdminView 共用同一个键）
export const ADMIN_TOKEN_KEY = 'kg-admin-token'

/** 读取本机保存的管理口令（没有则返回空串） */
function readAdminToken() {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

/**
 * 把管理口令写进请求头。
 *
 * 必须兼容 AxiosHeaders：axios v1 会把 config.headers 归一化成 AxiosHeaders 实例，
 * 此时**直接赋值普通属性不会生效**（不会进入最终发送的头）。
 * 重试路径复用的正是这种已被归一化的 config —— 之前就是因此导致
 * 「用户输了口令、请求却依然 401」。有 set() 就用 set()。
 */
function attachAdminToken(config, token) {
  if (!token) return
  const h = config.headers
  if (h && typeof h.set === 'function') {
    if (!h.has?.('X-Admin-Token')) h.set('X-Admin-Token', token)
  } else {
    config.headers = config.headers || {}
    if (!config.headers['X-Admin-Token']) config.headers['X-Admin-Token'] = token
  }
}

// 请求拦截器：注入 user_id + 管理口令
api.interceptors.request.use(config => {
  // 默认 user_id=1（单用户模式）
  if (!config.params) config.params = {}
  if (!config.params.user_id) config.params.user_id = 1

  // 自动携带管理口令：后端对写操作强制校验（零信任），
  // 若已在「后台管理」输入过则直接带上，用户无需关心。
  attachAdminToken(config, readAdminToken())
  return config
})

// 响应拦截器：统一错误处理 + 幂等重试
api.interceptors.response.use(
  res => res,
  async err => {
    const config = err.config || {}
    const url = config.url || ''
    const method = (config.method || 'get').toLowerCase()
    const apiError = toApiError(err)

    console.error('[API]', url, apiError.message, apiError.hint || '')

    // ---- 幂等重试：只对 GET，且只针对「可能是偶发」的失败 ----
    const retriable = method === 'get'
      && (apiError.isNetwork || apiError.isServerError)
      && !(config.__retried >= RETRY_MAX)
      && !NO_RETRY_PATHS.some(p => url.includes(p))

    if (retriable) {
      config.__retried = (config.__retried || 0) + 1
      await new Promise(r => setTimeout(r, RETRY_DELAY_MS * config.__retried))
      console.warn(`[API] 网络/服务端异常，自动重试第 ${config.__retried} 次：${url}`)
      try {
        return await api.request(config)
      } catch (again) {
        return Promise.reject(again instanceof ApiError ? again : toApiError(again))
      }
    }

    // 服务端异常上报（前端白屏/接口挂了都能在后台看到，不再只活在控制台）
    if (apiError.isServerError && !NO_RETRY_PATHS.some(p => url.includes(p))) {
      try {
        reportClientError({
          message: `接口 ${method.toUpperCase()} ${url} 返回 ${apiError.status}：${apiError.message}`,
          source: 'api',
          component: 'axios',
          info: `request_id=${apiError.requestId} code=${apiError.code}`
        })
      } catch { /* 静默 */ }
    }

    // ---- 写操作需要口令：提示输入一次并自动重试 ----
    // 后端对所有 POST/PUT/PATCH/DELETE 强制校验口令（零信任）。
    // 这里做一次友好引导，避免用户第一次上传时困惑 —— 口令只存在本地，
    // 之后所有写请求自动携带。
    if (apiError.status === 401 && apiError.code === 'write_requires_token'
        && !config.__authRetried && !_askingToken) {
      config.__authRetried = true
      const ok = await _promptAdminToken()
      if (ok) {
        // 显式把新口令写进这次重试的 config（不能只依赖拦截器：
        // 这里的 config 已经是归一化过的 AxiosHeaders 对象）
        attachAdminToken(config, readAdminToken())
        try {
          return await api.request(config)
        } catch (again) {
          return Promise.reject(again instanceof ApiError ? again : toApiError(again))
        }
      }
    }

    return Promise.reject(apiError)
  }
)

// 单飞标记：并发写请求同时 401 时，只弹一次口令输入框
let _askingToken = false

async function _promptAdminToken() {
  _askingToken = true
  try {
    const { ElMessageBox } = await import('element-plus')
    const { value } = await ElMessageBox.prompt(
      '写操作（上传 / 删除 / 重建）已受管理口令保护。\n请输入后台管理口令，本机记住后无需重复输入。',
      '需要管理口令',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputType: 'password',
        inputPlaceholder: '默认为 kg-admin，可在 backend/.env 修改',
        inputValidator: v => (v && v.trim() ? true : '口令不能为空'),
      }
    ).catch(() => ({ value: null }))

    if (!value) return false
    try {
      localStorage.setItem(ADMIN_TOKEN_KEY, value.trim())
    } catch { /* 隐私模式等场景下存不了，本次仍继续尝试 */ }
    // 密钥变更后要重建 api 实例上的默认头
    api.defaults.headers.common['X-Admin-Token'] = value.trim()
    const { ElMessage } = await import('element-plus')
    ElMessage.success('口令已记住，正在重试')
    return true
  } catch {
    return false
  } finally {
    _askingToken = false
  }
}

// ==================== 文件 API ====================
export const fileAPI = {
  /** 上传文件到后端解析 */
  async upload(file) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/files/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return res.data
  },

  /** 删除文件及关联数据 */
  async delete(fileId) {
    const res = await api.delete(`/files/${fileId}`)
    return res.data
  },

  /** 获取文件列表 */
  async list() {
    const res = await api.get('/files')
    return res.data
  },

  /** 获取文件的所有节点 */
  async getNodes(fileId) {
    const res = await api.get(`/files/${fileId}/nodes`)
    return res.data
  },

  /**
   * 本地文件夹笔记同步（模块1：本地为源 + 双写）。
   * 按 source_path 幂等：首建后更新，内容变化自动清旧节点重解析。
   */
  async syncLocal({ sourcePath, name, content }) {
    const res = await api.post('/files/sync', {
      user_id: 1,
      source_path: sourcePath,
      name: name || '未命名笔记',
      content: content || ''
    })
    return res.data
  },

  /** 上传/解析上限（前端做前置校验，与后端同源，避免大文件把服务打挂） */
  async limits() {
    const res = await api.get('/files/limits')
    return res.data
  },

  /** 更新文件元数据（本地重命名后同步 name / source_path） */
  async renameFile(fileId, { name, sourcePath }) {
    const res = await api.patch(`/files/${fileId}`, {
      user_id: 1,
      name,
      source_path: sourcePath
    })
    return res.data
  }
}

// ==================== 知识 API ====================
export const knowledgeAPI = {
  /** 校验笔记内容 */
  async validate(content) {
    const res = await api.post('/knowledge/validate', { content })
    return res.data
  },

  /** 为新节点推理关联连线 */
  async inferLinks(nodes, weights, threshold) {
    const res = await api.post('/knowledge/infer', {
      nodes,
      weights: weights || {},
      threshold: threshold || 0.15
    })
    return res.data
  },

  /** 搜索知识库 */
  async search(keyword, limit = 20) {
    const res = await api.get('/knowledge/search', {
      params: { keyword, limit }
    })
    return res.data
  }
}

// ==================== 图谱 API ====================
export const graphAPI = {
  /** 构建图谱（获取完整节点+连线数据） */
  async build(options = {}) {
    const res = await api.post('/graph/build', {
      group_id: options.groupId || 'all',
      user_id: options.userId || 1,
      include_discarded: options.includeDiscarded || false
    })
    return res.data
  },

  /**
   * 读取图谱数据（只读，走 GET）。
   *
   * 与 build() 的差别只在 HTTP 动词：后端 `/api/graph/build` 实际上是纯查询，
   * 但它是 POST，会被写操作守卫要求管理口令 —— 而启动时就要读图谱，
   * 结果每次打开应用都弹口令框。
   * 只读场景请用本方法；build() 仅保留给需要传复杂参数的调用方。
   */
  async load({ groupId = 'all', userId = 1, includeDiscarded = false } = {}) {
    const res = await api.get('/graph', {
      params: {
        group_id: groupId,
        user_id: userId,
        include_discarded: includeDiscarded
      }
    })
    return res.data
  },

  /** 更新图谱配置（权重、阈值等） */
  async update(data) {
    const res = await api.post('/graph/update', {
      user_id: data.userId || 1,
      weights: data.weights,
      threshold: data.threshold,
      corpus_enabled: data.corpusEnabled
    })
    return res.data
  }
}

// ==================== 笔记 API ====================
export const noteAPI = {
  /** 保存笔记 */
  async save(note) {
    const res = await api.post('/notes/save', {
      id: note.id,
      user_id: note.userId || 1,
      title: note.title || '未命名笔记',
      content: note.content || '',
      tags: note.tags || [],
      linked_files: note.linkedFiles || [],
      linked_nodes: note.linkedNodes || [],
      archived: typeof note.archived === 'boolean' ? note.archived : null,
      accuracy_score: note.accuracyScore,
      // 模块2：v2 校验报告 / 状态随保存落库（未提交时后端不覆盖既有记录）
      validation_report: note.validationReport || null,
      validation_status: note.validationStatus || null,
      verified: typeof note.verified === 'boolean' ? note.verified : null
    })
    return res.data
  },

  /** 删除笔记 */
  async delete(noteId) {
    const res = await api.delete(`/notes/${noteId}`)
    return res.data
  },

  /** 获取笔记列表 */
  async list(filters = {}) {
    const res = await api.get('/notes', { params: filters })
    return res.data
  },

  /** 获取单个笔记 */
  async get(noteId) {
    const res = await api.get(`/notes/${noteId}`)
    return res.data
  }
}

// ==================== 知识库 API ====================
export const kbAPI = {
  /** 知识库总览（条目/关系/领域/覆盖情况） */
  async stats() {
    const res = await api.get('/kb/stats')
    return res.data
  },

  /** 条目列表（关键词/领域/层级筛选） */
  async entries({ keyword = '', domain = '', level = 0, limit = 50, offset = 0 } = {}) {
    const res = await api.get('/kb/entries', {
      params: { keyword, domain, level, limit, offset }
    })
    return res.data
  },

  /** 新增知识点 */
  async createEntry(payload) {
    const res = await api.post('/kb/entries', payload)
    return res.data
  },

  /** 编辑知识点 */
  async updateEntry(id, payload) {
    const res = await api.put(`/kb/entries/${id}`, payload)
    return res.data
  },

  /** 删除知识点 */
  async deleteEntry(id) {
    const res = await api.delete(`/kb/entries/${id}`)
    return res.data
  },

  /** 知识库关系边 */
  async relations({ entity = '', limit = 200 } = {}) {
    const res = await api.get('/kb/relations', { params: { entity, limit } })
    return res.data
  },

  /** 某个知识点的邻域（证据下钻） */
  async neighbors(entity, limit = 20) {
    const res = await api.get('/kb/neighbors', { params: { entity, limit } })
    return res.data
  },

  /** 上传知识库文档（dry_run=true 只出理解报告，不落库） */
  async upload(file, { dryRun = false, overwrite = false } = {}) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/kb/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { dry_run: dryRun, overwrite }
    })
    return res.data
  },

  /** 粘贴文本方式理解（默认只预览） */
  async preview({ text, name = '未命名知识库', dryRun = true, overwrite = false }) {
    const res = await api.post('/kb/preview', { text, name, dry_run: dryRun, overwrite })
    return res.data
  },

  /** 上传历史 */
  async imports(limit = 20) {
    const res = await api.get('/kb/imports', { params: { limit } })
    return res.data
  },

  /** 单次导入的完整理解报告 */
  async importDetail(id) {
    const res = await api.get(`/kb/imports/${id}`)
    return res.data
  },

  /** 知识锚定：文本命中了哪些知识点 */
  async match(text, limit = 30) {
    const res = await api.post('/kb/match', { text, limit })
    return res.data
  },

  /** 知识库本体图 */
  async graph({ domain = '', keyword = '', limit = 150 } = {}) {
    const res = await api.get('/kb/graph', { params: { domain, keyword, limit } })
    return res.data
  },

  /** 文件知识画像 + 文件间知识关联 */
  async files(threshold = 0) {
    const res = await api.get('/kb/files', { params: { threshold } })
    return res.data
  },

  /** 单个文件的知识画像详情 */
  async fileDetail(fileId) {
    const res = await api.get(`/kb/file/${fileId}`)
    return res.data
  },

  /** 重建知识库关联链（关系 → 锚定 → 画像 → 文件/节点关联） */
  async rebuild({ threshold = 0.15, nodeThreshold = 0.15, rebuildRelations = true } = {}) {
    const res = await api.post('/kb/rebuild', {
      user_id: 1,
      threshold,
      node_threshold: nodeThreshold,
      rebuild_relations: rebuildRelations
    })
    return res.data
  }
}

// ==================== 图谱总结 API ====================
export const summaryAPI = {
  /** 生成图谱总结（结构化总结 + Mermaid 流程图 + AI 可读摘要） */
  async build({ groupBy = 'level', maxPaths = 6, title = '知识图谱总结' } = {}) {
    const res = await api.post('/summary/build', {
      user_id: 1,
      group_by: groupBy,
      max_paths: maxPaths,
      title
    })
    return res.data
  },

  /** 只取 Mermaid 流程图源码 */
  async mermaid(groupBy = 'level') {
    const res = await api.get('/summary/mermaid', { params: { group_by: groupBy } })
    return res.data
  },

  /** AI 可读摘要（纯文本） */
  async aiDigest() {
    const res = await api.get('/summary/ai-digest')
    return res.data
  },

  /** 导出文件下载地址：fmt = md | docx | pptx | mermaid | digest | json */
  downloadUrl(fmt = 'md', { groupBy = 'level', title = '知识图谱总结' } = {}) {
    const base = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'
    const qs = new URLSearchParams({ fmt, group_by: groupBy, title, user_id: '1' })
    return `${base}/summary/download?${qs.toString()}`
  },

  /** 下载导出文件（blob，避免浏览器直接打开而不是下载） */
  async download(fmt = 'md', options = {}) {
    const res = await api.get('/summary/download', {
      params: {
        fmt,
        group_by: options.groupBy || 'level',
        title: options.title || '知识图谱总结'
      },
      responseType: 'blob'
    })
    return res.data
  }
}

// ==================== 个人主页 API ====================
export const profileAPI = {
  async get() {
    const res = await api.get('/profile')
    return res.data
  },

  async overview() {
    const res = await api.get('/profile/overview')
    return res.data
  },

  async update(payload) {
    const res = await api.put('/profile', payload)
    return res.data
  },

  async uploadAvatar(file) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/profile/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return res.data
  },

  async uploadBackground(file) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/profile/background', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return res.data
  },

  async clearBackground() {
    const res = await api.delete('/profile/background')
    return res.data
  },

  /** 把服务端的相对图片地址补全为可直接访问的 URL */
  fileUrl(path) {
    if (!path) return ''
    if (/^https?:\/\//.test(path)) return path
    const base = (import.meta.env.VITE_API_BASE || 'http://localhost:8000/api').replace(/\/api\/?$/, '')
    return `${base}${path}`
  }
}

// ==================== 后台管理 API（口令保护） ====================
const adminHeaders = (token) => ({ 'X-Admin-Token': token || '' })

export const adminAPI = {
  async auth(token) {
    const res = await api.get('/admin/auth', { headers: adminHeaders(token) })
    return res.data
  },

  async overview(token) {
    const res = await api.get('/admin/overview', { headers: adminHeaders(token) })
    return res.data
  },

  async candidates(token, params = {}) {
    const res = await api.get('/admin/candidates', { params, headers: adminHeaders(token) })
    return res.data
  },

  async candidateDetail(token, id) {
    const res = await api.get(`/admin/candidates/${id}`, { headers: adminHeaders(token) })
    return res.data
  },

  async review(token, id, payload) {
    const res = await api.post(`/admin/candidates/${id}/review`, payload,
      { headers: adminHeaders(token) })
    return res.data
  },

  async bulkReview(token, payload) {
    const res = await api.post('/admin/candidates/bulk-review', payload,
      { headers: adminHeaders(token) })
    return res.data
  },

  async verify(token, payload) {
    const res = await api.post('/admin/candidates/verify', payload,
      { headers: adminHeaders(token) })
    return res.data
  },

  async removeCandidate(token, id) {
    const res = await api.delete(`/admin/candidates/${id}`, { headers: adminHeaders(token) })
    return res.data
  },

  async audit(token, params = {}) {
    const res = await api.get('/admin/audit', { params, headers: adminHeaders(token) })
    return res.data
  },

  async auditDetail(token, id) {
    const res = await api.get(`/admin/audit/${id}`, { headers: adminHeaders(token) })
    return res.data
  },

  async users(token) {
    const res = await api.get('/admin/users', { headers: adminHeaders(token) })
    return res.data
  },

  async verdictStats(token) {
    const res = await api.get('/admin/stats/verdicts', { headers: adminHeaders(token) })
    return res.data
  },

  async adminFiles(token) {
    const res = await api.get('/admin/files', { headers: adminHeaders(token) })
    return res.data
  }
}

// ==================== 系统自检 API ====================
export const systemAPI = {
  /** 全量体检：环境/配置/数据库/表结构/知识库/依赖/磁盘 */
  async doctor() {
    const res = await api.get('/system/doctor')
    return res.data
  },

  /** 精简探活（给状态指示灯用） */
  async healthDeep() {
    const res = await api.get('/system/health-deep')
    return res.data
  },

  /** 主动上报一条前端错误（自动化/手工排查时可用） */
  async reportError(payload) {
    const res = await api.post('/system/client-error', payload)
    return res.data
  }
}

export default api