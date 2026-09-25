/**
 * API 服务层
 * 封装所有后端接口调用，替换前端本地计算逻辑
 */

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000 // 推理可能较慢，放宽超时
})

// 请求拦截器：注入 user_id
api.interceptors.request.use(config => {
  // 默认 user_id=1（单用户模式）
  if (!config.params) config.params = {}
  if (!config.params.user_id) config.params.user_id = 1
  return config
})

// 响应拦截器：统一错误处理
api.interceptors.response.use(
  res => res,
  err => {
    const msg = err.response?.data?.detail || err.message || '网络请求失败'
    console.error('[API]', err.config?.url, msg)
    return Promise.reject(new Error(msg))
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

export default api