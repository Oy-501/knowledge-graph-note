/**
 * API 服务层
 * 封装所有后端接口调用
 */
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000
})

api.interceptors.request.use(config => {
  if (!config.params) config.params = {}
  if (!config.params.user_id) config.params.user_id = 1
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    const msg = err.response?.data?.detail || err.message || '网络请求失败'
    console.error('[API]', err.config?.url, msg)
    return Promise.reject(new Error(msg))
  }
)

export const fileAPI = {
  async upload(file) {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/files/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    return res.data
  },
  async delete(fileId) {
    const res = await api.delete(`/files/${fileId}`)
    return res.data
  },
  async list() {
    const res = await api.get('/files')
    return res.data
  },
  async getNodes(fileId) {
    const res = await api.get(`/files/${fileId}/nodes`)
    return res.data
  },
  async syncLocal({ sourcePath, name, content }) {
    const res = await api.post('/files/sync', { user_id: 1, source_path: sourcePath, name: name || '未命名笔记', content: content || '' })
    return res.data
  },
  async renameFile(fileId, { name, sourcePath }) {
    const res = await api.patch(`/files/${fileId}`, { user_id: 1, name, source_path: sourcePath })
    return res.data
  }
}

export const knowledgeAPI = {
  async validate(content) {
    const res = await api.post('/knowledge/validate', { content })
    return res.data
  },
  async inferLinks(nodes, weights, threshold) {
    const res = await api.post('/knowledge/infer', { nodes, weights: weights || {}, threshold: threshold || 0.15 })
    return res.data
  },
  async search(keyword, limit = 20) {
    const res = await api.get('/knowledge/search', { params: { keyword, limit } })
    return res.data
  }
}

export const graphAPI = {
  async build(options = {}) {
    const res = await api.post('/graph/build', { group_id: options.groupId || 'all', user_id: options.userId || 1, include_discarded: options.includeDiscarded || false })
    return res.data
  },
  async update(data) {
    const res = await api.post('/graph/update', { user_id: data.userId || 1, weights: data.weights, threshold: data.threshold, corpus_enabled: data.corpusEnabled })
    return res.data
  }
}

export const noteAPI = {
  async save(note) {
    const res = await api.post('/notes/save', {
      id: note.id, user_id: note.userId || 1, title: note.title || '未命名笔记',
      content: note.content || '', tags: note.tags || [], linked_files: note.linkedFiles || [],
      linked_nodes: note.linkedNodes || [], archived: typeof note.archived === 'boolean' ? note.archived : null,
      accuracy_score: note.accuracyScore, validation_report: note.validationReport || null,
      validation_status: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null
    })
    return res.data
  },
  async delete(noteId) { const res = await api.delete(`/notes/${noteId}`); return res.data },
  async list(filters = {}) { const res = await api.get('/notes', { params: filters }); return res.data },
  async get(noteId) { const res = await api.get(`/notes/${noteId}`); return res.data }
}

export const kbAPI = {
  async stats() { const res = await api.get('/kb/stats'); return res.data },
  async entries({ keyword = '', domain = '', level = 0, limit = 50, offset = 0 } = {}) {
    const res = await api.get('/kb/entries', { params: { keyword, domain, level, limit, offset } }); return res.data
  },
  async createEntry(payload) { const res = await api.post('/kb/entries', payload); return res.data },
  async updateEntry(id, payload) { const res = await api.put(`/kb/entries/${id}`, payload); return res.data },
  async deleteEntry(id) { const res = await api.delete(`/kb/entries/${id}`); return res.data },
  async relations({ entity = '', limit = 200 } = {}) { const res = await api.get('/kb/relations', { params: { entity, limit } }); return res.data },
  async neighbors(entity, limit = 20) { const res = await api.get('/kb/neighbors', { params: { entity, limit } }); return res.data },
  async upload(file, { dryRun = false, overwrite = false } = {}) {
    const formData = new FormData(); formData.append('file', file)
    const res = await api.post('/kb/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' }, params: { dry_run: dryRun, overwrite } })
    return res.data
  },
  async preview({ text, name = '未命名知识库', dryRun = true, overwrite = false }) {
    const res = await api.post('/kb/preview', { text, name, dry_run: dryRun, overwrite }); return res.data
  },
  async imports(limit = 20) { const res = await api.get('/kb/imports', { params: { limit } }); return res.data },
  async importDetail(id) { const res = await api.get(`/kb/imports/${id}`); return res.data },
  async match(text, limit = 30) { const res = await api.post('/kb/match', { text, limit }); return res.data },
  async graph({ domain = '', keyword = '', limit = 150 } = {}) { const res = await api.get('/kb/graph', { params: { domain, keyword, limit } }); return res.data },
  async files(threshold = 0) { const res = await api.get('/kb/files', { params: { threshold } }); return res.data },
  async fileDetail(fileId) { const res = await api.get(`/kb/file/${fileId}`); return res.data },
  async rebuild({ threshold = 0.15, nodeThreshold = 0.15, rebuildRelations = true } = {}) {
    const res = await api.post('/kb/rebuild', { user_id: 1, threshold, node_threshold: nodeThreshold, rebuild_relations: rebuildRelations }); return res.data
  }
}

export default api
