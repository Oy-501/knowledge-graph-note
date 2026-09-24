/**
 * fileStore.js（混合架构版）
 */
import { defineStore } from 'pinia'
import { useGraphStore } from './graphStore'
import { useGroupStore } from './groupStore'
import { fileAPI, graphAPI } from '@/api/index'

const POLL_INTERVAL = 2000
const POLL_TIMEOUT = 120000

async function pollForNodes(fileId, onProgress, epoch, currentEpoch) {
  const startTime = Date.now()
  let pollCount = 0
  while (Date.now() - startTime < POLL_TIMEOUT) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL))
    if (epoch !== null && epoch !== undefined && epoch !== currentEpoch) return null
    try {
      const result = await fileAPI.getNodes(fileId)
      if (result?.error?.status === 404) throw new Error('文件不存在')
      pollCount++
      if (pollCount % 2 === 0) {
        try {
          const fileList = await fileAPI.list()
          const fileMeta = fileList.files?.find(f => f.id === fileId)
          if (fileMeta && (fileMeta.status === 'done' || fileMeta.status === 'indexed')) {
            if (onProgress) onProgress(80)
            return result.nodes || []
          }
        } catch (e) {}
      }
      if (result.nodes?.length > 0) { if (onProgress) onProgress(80); return result.nodes }
    } catch (e) {
      if (e.message === '文件不存在') throw e
    }
    if (onProgress) { const elapsed = Math.floor((Date.now() - startTime) / 1000); onProgress(30 + Math.min(elapsed / 10, 50)) }
  }
  throw new Error('文件解析超时')
}

export const useFileStore = defineStore('file', {
  state: () => ({ uploadedFiles: [], loading: false, _pollEpoch: 0 }),
  getters: {
    fileCount: (s) => s.uploadedFiles.length,
    indexedCount: (s) => s.uploadedFiles.filter(f => f.status === 'indexed').length
  },
  actions: {
    async loadPersisted() {
      try {
        const graphStore = useGraphStore()
        const result = await graphStore.loadFromBackend()
        if (result.ok) {
          try {
            const filesData = await fileAPI.list()
            if (filesData.files) {
              this.uploadedFiles = filesData.files.map(f => ({ id: f.id, name: f.name, size: 0, status: f.status || 'indexed', kpCount: f.node_count || 0, parsedAt: f.uploaded_at ? new Date(f.uploaded_at).getTime() : 0 }))
            }
          } catch (e) { console.warn('[fileStore] load file list failed:', e.message) }
        }
      } catch (e) { console.error('[fileStore] loadPersisted failed', e) }
    },
    async uploadFiles(fileList) {
      const files = Array.from(fileList || []).filter(f => /\.(md|txt|markdown)$/i.test(f.name) || (f.type && f.type.startsWith('text')))
      if (files.length === 0) return { ok: 0, msg: '只支持 .md/.txt 文本文件' }
      if (this.loading) return { ok: 0, msg: '正在上传中' }
      this.loading = true
      const graphStore = useGraphStore()
      graphStore.setBusy('上传文件到后端解析')
      let okCount = 0
      for (const f of files) {
        try {
          graphStore.setBusy('上传 ' + f.name); graphStore.setProgress(10)
          const uploadResult = await fileAPI.upload(f)
          const fileId = uploadResult.file_id
          graphStore.setProgress(25)
          graphStore.setBusy('解析 ' + f.name + '（后端处理中...）')
          const epoch = ++this._pollEpoch
          const nodes = await pollForNodes(fileId, p => graphStore.setProgress(p), epoch, this._pollEpoch)
          if (nodes === null) { console.warn('[fileStore] poll cancelled for', f.name); break }
          const kps = nodes.map((n, idx) => ({
            id: n.id || 'kp_' + idx + '_' + Math.random().toString(36).slice(2, 6) + '_' + Date.now().toString(36),
            title: n.title || n.entity || '', description: n.description || '', rawText: n.description || '',
            type: n.type || 'knowledge', level: n.level || 3,
            levelLabel: n.level === 1 ? 'L1: 元概念' : n.level === 2 ? 'L2: 核心理论' : n.level === 4 ? 'L4: 实现工具' : 'L3: 具体技术',
            keywords: n.keywords || [], entities: n.entities || [], _domain: n.domain || ''
          }))
          this.uploadedFiles.push({ id: fileId, name: f.name, size: f.size, type: f.name.split('.').pop(), status: 'parsing', kpCount: kps.length, parsedAt: Date.now() })
          graphStore.setBusy('推理关联关系')
          await graphStore.ingestNewNodes(fileId, kps)
          const groupName = f.name.replace(/\.(md|txt|markdown)$/i, '')
          const newNodes = graphStore.nodes.filter(n => n.fileId === fileId)
          const groupStore = useGroupStore()
          groupStore.assignGroupForNodes(newNodes, groupName)
          const meta = this.uploadedFiles.find(x => x.id === fileId)
          if (meta) meta.status = 'indexed'
          okCount++; graphStore.setProgress(100)
        } catch (e) {
          console.error('[fileStore] upload failed', f.name, e)
          const meta = this.uploadedFiles.find(x => x.name === f.name)
          if (meta) { meta.status = 'failed'; meta.error = String(e?.message || e) }
          else { this.uploadedFiles.push({ id: 'f_failed_' + Date.now().toString(36), name: f.name, size: f.size, status: 'failed', kpCount: 0, parsedAt: Date.now(), error: String(e?.message || e) }) }
        }
      }
      graphStore.setBusy(''); this.loading = false
      return { ok: okCount, msg: '成功解析 ' + okCount + '/' + files.length + ' 个文件' }
    },
    async deleteFile(fileId) {
      const graphStore = useGraphStore()
      graphStore.setBusy('清理删除数据')
      try {
        await fileAPI.delete(fileId)
        await graphStore.removeNodesByFile(fileId)
        this.uploadedFiles = this.uploadedFiles.filter(f => f.id !== fileId)
        graphStore.afterDeleteRefresh()
        graphStore.setBusy('')
        return { ok: true }
      } catch (e) { console.error('[fileStore] delete failed', e); graphStore.setBusy(''); return { ok: false, msg: String(e?.message || e) } }
    },
    async clearAll() {
      const graphStore = useGraphStore()
      graphStore.setBusy('清空全部数据')
      for (const f of [...this.uploadedFiles]) { try { await fileAPI.delete(f.id) } catch (e) {} }
      this._pollEpoch++
      graphStore.reset(); this.uploadedFiles = []; graphStore.setBusy('')
      return { ok: true }
    }
  },
  persist: false
})
