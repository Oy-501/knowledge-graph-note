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
  /**
   * 是否是「需要（重新）登录」。
   *
   * 只认这两个码，不看状态码本身 —— 401 也可能是「密码错」这类业务失败，
   * 那种情况把人踢回登录页会把用户刚输入的内容清掉。
   * 后端在写守卫里明确回 session_required，在这里才意味着会话没了。
   */
  get isSessionExpired() { return this.status === 401 && this.code === 'session_required' }
  /** 是否存在但权限不够（普通用户做了管理员操作）—— 这种情况**不要**踢回登录页 */
  get isForbidden() { return this.status === 403 && this.code === 'admin_required' }
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
    if (res.status === 401) {
      hint = '登录状态已失效，请重新登录。'
    } else if (res.status === 403) {
      hint = '当前账号没有这个权限；写操作需要管理员账号。'
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

// ============================================================ 会话令牌
//
// 写操作的身份凭证现在是**登录会话**（X-Session-Token），不再是配置文件里的
// 明文管理口令。这么做之后前端只需要记住一件事：把当前令牌挂到每个请求上。
//
// 这里刻意用「模块级变量 + 读写函数」而不是直接 import authStore：
// authStore 要 import 本文件的 authAPI，直接反向 import 会形成循环依赖，
// 循环依赖在打包器里表现为「某个模块拿到的是半初始化的对象」，
// 症状是难查的 undefined。用回调注册把依赖方向掰直。
//
// 另外必须兼容 AxiosHeaders：axios v1 会把 config.headers 归一化成
// AxiosHeaders 实例，此时**直接赋值普通属性不会生效**。
// 之前踩过这个坑（用户输了口令、重试请求却依然 401），有 set() 就用 set()。

let _sessionToken = ''

/** 由 authStore 调用：设置/清空当前会话令牌 */
export function setSessionToken(token) {
  _sessionToken = token || ''
}

/**
 * 注册「会话失效」回调（由 authStore 注册）。
 * 任意请求收到 401 session_required 时触发一次，让 store 清理本地状态并回登录页。
 */
let _onSessionExpired = null
export function onSessionExpired(fn) {
  _onSessionExpired = typeof fn === 'function' ? fn : null
}

function attachSessionToken(config) {
  if (!_sessionToken) return
  const h = config.headers
  if (h && typeof h.set === 'function') {
    if (!h.has?.('X-Session-Token')) h.set('X-Session-Token', _sessionToken)
  } else {
    config.headers = config.headers || {}
    if (!config.headers['X-Session-Token']) config.headers['X-Session-Token'] = _sessionToken
  }
}

// 旧版管理口令的存储键：仅用于**登录成功后清理**它。
// 它已经不再参与鉴权（前端不再弹口令框），但老用户的浏览器里可能还留着，
// 留着会让人误以为「这里还存着一个密钥」。登录成功时顺手删掉。
export const ADMIN_TOKEN_KEY = 'kg-admin-token'

function dropLegacyAdminToken() {
  try {
    localStorage.removeItem(ADMIN_TOKEN_KEY)
  } catch { /* 读不到 localStorage 也无所谓 */ }
}

// 请求拦截器：注入 user_id + 会话令牌
api.interceptors.request.use(config => {
  // 默认 user_id=1（单用户模式）
  if (!config.params) config.params = {}
  if (!config.params.user_id) config.params.user_id = 1

  // 自动携带会话令牌：后端对写操作强制校验（零信任），登录一次后无需再管
  attachSessionToken(config)
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

    // ---- 会话失效：通知上层回到登录页 ----
    //
    // 后端写守卫在「未登录/会话过期」时回 401 session_required。
    // 这里**不再**弹口令框（旧做法已废弃），而是交给 authStore 清状态、回登录页。
    // 用回调而不是在这里 import store，是为了避免循环依赖（见文件上方说明）。
    if (apiError.isSessionExpired) {
      try {
        _onSessionExpired?.()
      } catch (e) {
        console.warn('[API] 会话失效回调执行失败：', e?.message || e)
      }
    }

    return Promise.reject(apiError)
  }
)

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
    // 兜底值与主 baseURL 保持一致（127.0.0.1 而非 localhost：
    // localhost 可能被解析成 IPv6 ::1，后端只绑 IPv4 回环 → 图片全裂）
    const base = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8080/api').replace(/\/api\/?$/, '')
    return `${base}${path}`
  }
}

// ==================== 认证 API ====================
//
// 登录页只用这几个接口。令牌由请求拦截器自动挂到请求头，调用方无需关心。
// 三个成功路径都会顺手删掉 localStorage 里遗留的旧管理口令 ——
// 它已经不再参与鉴权，留着只会让人以为「这里还存着一个密钥」。
export const authAPI = {
  /** 登录页初始探测：是否需初始化、是否开放注册、当前是否已登录 */
  async status() {
    const res = await api.get('/auth/status')
    return res.data
  },

  /** 首次初始化：设置账号密码并成为首个管理员 */
  async bootstrap({ username, password, displayName = '' }) {
    const res = await api.post('/auth/bootstrap', {
      username, password, display_name: displayName,
    })
    dropLegacyAdminToken()
    return res.data
  },

  async login({ username, password }) {
    const res = await api.post('/auth/login', { username, password })
    dropLegacyAdminToken()
    return res.data
  },

  async register({ username, password }) {
    const res = await api.post('/auth/register', { username, password })
    dropLegacyAdminToken()
    return res.data
  },

  async logout() {
    const res = await api.post('/auth/logout')
    return res.data
  },

  async me() {
    const res = await api.get('/auth/me')
    return res.data
  },

  async changePassword({ oldPassword, newPassword }) {
    const res = await api.post('/auth/password', {
      old_password: oldPassword, new_password: newPassword,
    })
    return res.data
  },
}

// ==================== 后台管理 API ====================
//
// 令牌不再作为参数逐个传递 —— 请求拦截器统一挂 X-Session-Token。
// 旧签名是 `overview(token)`，那样每加一个端点就要多传一次 token，
// 漏传的端点会静默地退化成「未登录」，问题只在点了那个功能时才暴露。
export const adminAPI = {
  async auth() {
    const res = await api.get('/admin/auth')
    return res.data
  },

  async overview() {
    const res = await api.get('/admin/overview')
    return res.data
  },

  async candidates(params = {}) {
    const res = await api.get('/admin/candidates', { params })
    return res.data
  },

  async candidateDetail(id) {
    const res = await api.get(`/admin/candidates/${id}`)
    return res.data
  },

  async review(id, payload) {
    const res = await api.post(`/admin/candidates/${id}/review`, payload)
    return res.data
  },

  async bulkReview(payload) {
    const res = await api.post('/admin/candidates/bulk-review', payload)
    return res.data
  },

  async verify(payload) {
    const res = await api.post('/admin/candidates/verify', payload)
    return res.data
  },

  async removeCandidate(id) {
    const res = await api.delete(`/admin/candidates/${id}`)
    return res.data
  },

  async audit(params = {}) {
    const res = await api.get('/admin/audit', { params })
    return res.data
  },

  async auditDetail(id) {
    const res = await api.get(`/admin/audit/${id}`)
    return res.data
  },

  async users() {
    const res = await api.get('/admin/users')
    return res.data
  },

  async verdictStats() {
    const res = await api.get('/admin/stats/verdicts')
    return res.data
  },

  async adminFiles() {
    const res = await api.get('/admin/files')
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