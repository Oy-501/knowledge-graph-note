/**
 * fileStore.js（混合架构版）
 * 1) 文件上传到后端解析（FastAPI）
 * 2) 后端返回解析结果 → 前端添加到图谱
 * 3) 删除文件调用后端 API + 清理本地状态
 * 4) 状态标识：'pending' | 'parsing' | 'indexed' | 'failed'
 */

import { defineStore } from 'pinia'
import { useGraphStore } from './graphStore'
import { useGroupStore } from './groupStore'
import { fileAPI, graphAPI } from '@/api/index'

// 轮询间隔（毫秒）
const POLL_INTERVAL = 2000
const POLL_TIMEOUT = 120000  // 2分钟超时

/**
 * 轮询后端获取文件节点，直到解析完成
 * @param {string} fileId - 文件ID
 * @param {Function} onProgress - 进度回调
 * @param {number} epoch - 轮询epoch（用于取消过期轮询）
 * @param {number} currentEpoch - 当前store的epoch
 */
async function pollForNodes(fileId, onProgress, epoch, currentEpoch) {
  const startTime = Date.now()
  let pollCount = 0
  while (Date.now() - startTime < POLL_TIMEOUT) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL))
    // 检查是否过期
    if (epoch !== null && epoch !== undefined && epoch !== currentEpoch) {
      return null
    }
    try {
      const result = await fileAPI.getNodes(fileId)
      // 404错误立即退出
      if (result?.error?.status === 404) throw new Error('文件不存在')
      pollCount++
      // 每2-3轮检查一次文件状态
      if (pollCount % 2 === 0) {
        try {
          const fileList = await fileAPI.list()
          const fileMeta = fileList.files?.find(f => f.id === fileId)
          if (fileMeta && (fileMeta.status === 'done' || fileMeta.status === 'indexed')) {
            // 即使nodes为空也立即返回空数组
            if (onProgress) onProgress(80)
            return result.nodes || []
          }
        } catch (e) {
          // 继续轮询
        }
      }
      if (result.nodes?.length > 0) {
        if (onProgress) onProgress(80)
        return result.nodes
      }
    } catch (e) {
      if (e.message === '文件不存在') throw e
      // 继续轮询
    }
    if (onProgress) {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      onProgress(30 + Math.min(elapsed / 10, 50))
    }
  }
  throw new Error('文件解析超时')
}

export const useFileStore = defineStore('file', {
  state: () => ({
    uploadedFiles: [], // {id, name, size, status, kpCount, parsedAt}
    loading: false,
    _pollEpoch: 0
  }),
  getters: {
    fileCount: (s) => s.uploadedFiles.length,
    indexedCount: (s) => s.uploadedFiles.filter(f => f.status === 'indexed').length
  },
  actions: {
    /**
     * 从后端加载已持久化的文件列表和图谱数据
     */
    async loadPersisted() {
      try {
        const graphStore = useGraphStore()
        // 尝试从后端加载图谱数据
        const result = await graphStore.loadFromBackend()
        if (result.ok) {
          // 同时加载文件列表
          try {
            const filesData = await fileAPI.list()
            if (filesData.files) {
              this.uploadedFiles = filesData.files.map(f => ({
                id: f.id,
                name: f.name,
                size: 0,
                status: f.status || 'indexed',
                kpCount: f.node_count || 0,
                parsedAt: f.uploaded_at ? new Date(f.uploaded_at).getTime() : 0
              }))
            }
          } catch (e) {
            console.warn('[fileStore] load file list failed:', e.message)
          }
        }
      } catch (e) {
        console.error('[fileStore] loadPersisted failed', e)
      }
    },

    /**
     * 上传多个文件到后端解析
     */
    async uploadFiles(fileList) {
      const files = Array.from(fileList || []).filter(
        f => /\.(md|txt|markdown)$/i.test(f.name) ||
             (f.type && f.type.startsWith('text'))
      )
      if (files.length === 0) {
        return { ok: 0, msg: '只支持 .md/.txt 文本文件' }
      }

      if (this.loading) return { ok: 0, msg: '正在上传中' }
      this.loading = true
      const graphStore = useGraphStore()
      graphStore.setBusy('上传文件到后端解析')
      let okCount = 0

      for (const f of files) {
        try {
          graphStore.setBusy('上传 ' + f.name)
          graphStore.setProgress(10)

          // Step 1: 上传到后端
          const uploadResult = await fileAPI.upload(f)
          const fileId = uploadResult.file_id
          graphStore.setProgress(25)

          // Step 2: 轮询等待解析完成
          graphStore.setBusy('解析 ' + f.name + '（后端处理中...）')
          const epoch = ++this._pollEpoch
          const nodes = await pollForNodes(
            fileId,
            p => graphStore.setProgress(p),
            epoch,
            this._pollEpoch
          )
          if (nodes === null) {
            // 轮询被新操作取消
            console.warn('[fileStore] poll cancelled for', f.name)
            break
          }

          // Step 3: 转换为前端格式
          const kps = nodes.map((n, idx) => ({
            id: n.id || 'kp_' + idx + '_' + Math.random().toString(36).slice(2, 6) + '_' + Date.now().toString(36),
            title: n.title || n.entity || '',
            description: n.description || '',
            rawText: n.description || '',
            type: n.type || 'knowledge',
            level: n.level || 3,
            levelLabel: n.level === 1 ? 'L1: 元概念' : n.level === 2 ? 'L2: 核心理论' : n.level === 4 ? 'L4: 实现工具' : 'L3: 具体技术',
            keywords: n.keywords || [],
            entities: n.entities || [],
            _domain: n.domain || ''
          }))

          const fileMeta = {
            id: fileId,
            name: f.name,
            size: f.size,
            type: f.name.split('.').pop(),
            status: 'parsing',
            kpCount: kps.length,
            parsedAt: Date.now()
          }
          this.uploadedFiles.push(fileMeta)

          // Step 4: 交给 graphStore 处理（入库 + 调用推理 API）
          graphStore.setBusy('推理关联关系')
          await graphStore.ingestNewNodes(fileId, kps)

          // Step 5: 自动分组
          const groupName = f.name.replace(/\.(md|txt|markdown)$/i, '')
          const newNodes = graphStore.nodes.filter(n => n.fileId === fileId)
          const groupStore = useGroupStore()
          groupStore.assignGroupForNodes(newNodes, groupName)

          fileMeta.status = 'indexed'
          okCount++
          graphStore.setProgress(100)
        } catch (e) {
          console.error('[fileStore] upload failed', f.name, e)
          const meta = this.uploadedFiles.find(x => x.name === f.name)
          if (meta) {
            meta.status = 'failed'
            meta.error = String(e?.message || e)
          } else {
            this.uploadedFiles.push({
              id: 'f_failed_' + Date.now().toString(36),
              name: f.name,
              size: f.size,
              status: 'failed',
              kpCount: 0,
              parsedAt: Date.now(),
              error: String(e?.message || e)
            })
          }
        }
      }

      graphStore.setBusy('')
      this.loading = false
      return { ok: okCount, msg: '成功解析 ' + okCount + '/' + files.length + ' 个文件' }
    },

    /**
     * 删除单个文件
     */
    async deleteFile(fileId) {
      const graphStore = useGraphStore()
      graphStore.setBusy('清理删除数据')
      try {
        // 1) 调用后端删除 API（失败则抛出错误，不清理本地）
        await fileAPI.delete(fileId)

        // 2) 本地数据层清理
        await graphStore.removeNodesByFile(fileId)

        // 3) UI 列表移除
        this.uploadedFiles = this.uploadedFiles.filter(f => f.id !== fileId)

        // 4) 视图层刷新
        graphStore.afterDeleteRefresh()
        graphStore.setBusy('')
        return { ok: true }
      } catch (e) {
        console.error('[fileStore] delete failed', e)
        graphStore.setBusy('')
        return { ok: false, msg: String(e?.message || e) }
      }
    },

    /**
     * 清空所有数据
     */
    async clearAll() {
      const graphStore = useGraphStore()
      graphStore.setBusy('清空全部数据')
      // 逐个删除文件
      for (const f of [...this.uploadedFiles]) {
        try {
          await fileAPI.delete(f.id)
        } catch (e) { /* ignore */ }
      }
      this._pollEpoch++
      graphStore.reset()
      this.uploadedFiles = []
      graphStore.setBusy('')
      return { ok: true }
    }
  },
  persist: false
})