/**
 * folderStore.js —— 本地文件夹工作区（模块1 · 文件与笔记管理）
 *
 * 架构语义（用户已确认：本地为源 + 双写）：
 *  - 本地 .md/.txt 是笔记的「权威数据源」；
 *  - .kg_meta/kg.json 是本地知识元数据本体（笔记索引 / 标签 / 后端映射 / 删除历史）；
 *  - 知识节点/关系在后端可用时同步到 FastAPI（见 Stage D 的 _backendSync 钩子），
 *    后端不可用时不影响本地读写 —— 离线可干活。
 *
 * 数据模型：
 *  workspaces : [{ id, rootName, handle }]         目录句柄同时持久化到 IndexedDB(fs_roots)
 *  kgMeta     : { schema, app, workspace, notes:{relPath:{...}}, removed:[], settings:{} }
 *  notes      : [{ name, relPath, dirRelPath, fileHandle, content, title, digest, tags, backendFileId }]
 */

import { defineStore } from 'pinia'
import { dbPut, dbGetAll, dbDelete, STORE_FS_ROOTS } from './indexedDB'
import { fileAPI } from '@/api'
import {
  fsSupported, pickRootDir, requestDirPermission,
  scanDirTree, readKgMeta, writeKgMeta, readTextFile, writeTextFile,
  createNoteFile, renameEntry, deleteEntry, resolveDirHandle,
  extractTitle, contentDigest
} from '@/utils/folderFs'
import { KG_META_FILE } from '@/utils/folderFs'

/** 生成工作区 / 会话内 id */
function genId(prefix) {
  return prefix + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
}

/** kg.json 默认结构 */
function defaultKgMeta(rootName) {
  const now = Date.now()
  return {
    schema: 1,
    app: 'kg-notes',
    workspace: { rootName, createdAt: now, updatedAt: now },
    notes: {},       // relPath -> { name, relPath, title, tags, backendFileId, updatedAt, digest }
    removed: [],     // { relPath, name, removedAt, backendFileId } 删除历史（知识节点保留）
    settings: {}
  }
}

export const useFolderStore = defineStore('folder', {
  state: () => ({
    supported: false,
    loading: false,
    workspaces: [],           // [{ id, rootName, handle }]
    currentWorkspaceId: null,
    tree: null,               // 目录树（render 用）
    notes: [],                // 扁平笔记索引 [{ name, relPath, dirRelPath, fileHandle }]
    kgMeta: null,
    currentOpenNote: null,     // { name, relPath, title, content, digest, savedAt, tags, backendFileId }
    saveState: 'clean',       // clean | dirty | saving | error
    error: null,
    searchKeyword: '',
    lastScanReport: null      // rescan 时发现的新增/缺失 diff，供 UI 提示
  }),

  getters: {
    currentWorkspace(s) {
      return s.workspaces.find(w => w.id === s.currentWorkspaceId) || null
    },
    workspaceCount(s) {
      return s.workspaces.length
    },
    /** 按关键字过滤笔记列表（relPath / title 命中） */
    filteredNotes(s) {
      const kw = (s.searchKeyword || '').trim().toLowerCase()
      if (!kw) return s.notes
      return s.notes.filter(n =>
        n.relPath.toLowerCase().includes(kw) ||
        (n.title || n.name).toLowerCase().includes(kw)
      )
    },
    noteCount(s) {
      return s.notes.length
    },
    isDirty(s) {
      return s.saveState === 'dirty'
    }
  },

  actions: {
    // ==================== 生命周期 ====================

    /** 探测浏览器能力 + 从 IndexedDB 恢复已授权工作区 */
    async init() {
      this.supported = fsSupported()
      if (!this.supported) return { ok: false, msg: '浏览器不支持本地文件夹工作区' }
      try {
        const saved = await dbGetAll(STORE_FS_ROOTS) // [{id, rootName, handle}]
        const valid = []
        for (const item of saved || []) {
          if (!item || !item.handle) continue
          try {
            const perm = await requestDirPermission(item.handle)
            if (perm === 'granted') {
              valid.push({ id: item.id, rootName: item.rootName || item.handle.name, handle: item.handle })
            } else if (perm === 'prompt') {
              // 保留但标记需要重新点击授权（此处统一尝试过一次仍 prompt 则剔除）
              console.warn('[folderStore] workspace needs re-grant:', item.rootName)
            }
          } catch (e) {
            console.warn('[folderStore] drop invalid workspace:', item.id, e.message)
          }
        }
        this.workspaces = valid
        if (valid.length > 0 && !this.currentWorkspaceId) {
          // 恢复上一次会话使用的工作区（localStorage 仅存 id 轻量标记）
          let lastId
          try {
            lastId = localStorage.getItem('kg.folder.lastWorkspaceId')
          } catch (e) {
            lastId = null
          }
          const target = valid.find(w => w.id === lastId) || valid[0]
          this.currentWorkspaceId = target.id
          await this._activateWorkspace(target)
        }
        return { ok: true, count: this.workspaces.length }
      } catch (e) {
        console.error('[folderStore] init failed', e)
        return { ok: false, msg: e.message }
      }
    },

    // ==================== 工作区选择 / 切换 ====================

    /** 选择本地文件夹作为知识工作区（幂等：同一句柄不重复添加） */
    async pickWorkspace() {
      if (!fsSupported()) {
        this.error = 'File System Access API 不可用'
        return { ok: false, msg: this.error }
      }
      let dirHandle
      try {
        dirHandle = await pickRootDir()
      } catch (e) {
        if (e && (e.name === 'AbortError' || e.code === 20)) {
          return { ok: false, msg: '已取消选择' }
        }
        this.error = e.message
        return { ok: false, msg: e.message }
      }

      // 去重：同一目录句柄（按 name + isSameEntry 判定）
      const existing = this.workspaces.find(w =>
        w.handle.name === dirHandle.name &&
        w.handle.isSameEntry && w.handle.isSameEntry(dirHandle)
      )
      if (existing) {
        this.currentWorkspaceId = existing.id
        await this._activateWorkspace(existing)
        return { ok: true, workspace: existing, reused: true }
      }

      const id = genId('ws')
      const item = { id, rootName: dirHandle.name, handle: dirHandle }
      this.workspaces.push(item)
      this.currentWorkspaceId = id
      // 持久化句柄（IndexedDB 支持结构化克隆 FileSystemDirectoryHandle）
      try {
        await dbPut(STORE_FS_ROOTS, { id, rootName: dirHandle.name, handle: dirHandle })
      } catch (e) {
        console.warn('[folderStore] persist workspace handle failed:', e.message)
      }
      try {
        localStorage.setItem('kg.folder.lastWorkspaceId', id)
      } catch (e) {
        console.warn('[folderStore] set lastWorkspaceId failed:', e.message)
      }

      await this._activateWorkspace(item)
      return { ok: true, workspace: item, reused: false }
    },

    /** 切换到已授权的其它工作区 */
    async switchWorkspace(id) {
      const ws = this.workspaces.find(w => w.id === id)
      if (!ws) return { ok: false, msg: '工作区不存在' }
      this.currentWorkspaceId = id
      try {
        localStorage.setItem('kg.folder.lastWorkspaceId', id)
      } catch (e) {
        console.warn('[folderStore] set lastWorkspaceId failed:', e.message)
      }
      await this._activateWorkspace(ws)
      return { ok: true }
    },

    /** 从应用移除工作区（不影响磁盘文件） */
    async removeWorkspace(id) {
      this.workspaces = this.workspaces.filter(w => w.id !== id)
      await dbDelete(STORE_FS_ROOTS, id)
      if (this.currentWorkspaceId === id) {
        this.currentWorkspaceId = null
        this.tree = null
        this.notes = []
        this.kgMeta = null
        this.currentOpenNote = null
        this.saveState = 'clean'
      }
      return { ok: true }
    },

    /** 激活工作区：请求权限 → 确保 kg_meta → 扫描目录 */
    async _activateWorkspace(ws) {
      this.loading = true
      this.error = null
      try {
        const perm = await requestDirPermission(ws.handle)
        if (perm !== 'granted') {
          throw new Error(`目录「${ws.rootName}」未获得读写授权`)
        }
        if (this.currentWorkspaceId !== ws.id) return
        await this._ensureKgMeta()
        if (this.currentWorkspaceId !== ws.id) return
        const report = await this.rescan()
        return report
      } catch (e) {
        this.error = e.message
        console.error('[folderStore] activate failed', e)
        return { ok: false, msg: e.message }
      } finally {
        this.loading = false
      }
    },

    // ==================== .kg_meta 双写 ====================

    /** 确保 kg.json 存在并加载到内存 */
    async _ensureKgMeta() {
      const root = this.currentWorkspace?.handle
      if (!root) return null
      let meta = await readKgMeta(root)
      if (!meta) {
        meta = defaultKgMeta(root.name)
        await writeKgMeta(root, meta)
      }
      // 与工作区根名对齐
      if (!meta.workspace) meta.workspace = { rootName: root.name, createdAt: Date.now(), updatedAt: Date.now() }
      meta.workspace.rootName = root.name
      meta.app = 'kg-notes'
      meta.schema = meta.schema || 1
      // 稳定工作区 id：跨会话持久（同目录重选仍复用），作为后端 source_path 前缀
      if (!meta.workspace.id) {
        meta.workspace.id = (crypto.randomUUID?.() || genId('wsk'))
      }
      if (!meta.notes) meta.notes = {}
      if (!meta.removed) meta.removed = []
      if (!meta.settings) meta.settings = {}
      this.kgMeta = meta
      return meta
    },

    /** 将内存 kgMeta 序列化回 .kg_meta/kg.json */
    async saveKgMeta() {
      const root = this.currentWorkspace?.handle
      if (!root || !this.kgMeta) return false
      this.kgMeta.workspace.updatedAt = Date.now()
      try {
        await writeKgMeta(root, this.kgMeta)
        return true
      } catch (e) {
        console.error('[folderStore] saveKgMeta failed', e)
        this.error = '写入 ' + KG_META_FILE + ' 失败：' + e.message
        return false
      }
    },

    // ==================== 目录扫描 / 索引对齐 ====================

    /**
     * 重扫目录树，并对照 kgMeta.notes 输出差异报告
     * @returns {Promise<{ok:boolean, added:Array, missing:Array, tree:object, notes:Array}>}
     */
    async rescan() {
      const ws = this.currentWorkspace
      if (!ws) return { ok: false, msg: '未选择工作区' }
      this.loading = true
      try {
        const { tree, notes } = await scanDirTree(ws.handle)
        this.tree = tree
        this.notes = notes

        // 与 kgMeta.notes 对齐：新增 / 缺失
        const added = []
        const missing = []
        const known = this.kgMeta?.notes || {}
        for (const n of notes) {
          if (!known[n.relPath]) added.push(n.relPath)
        }
        for (const relPath of Object.keys(known)) {
          const stillThere = notes.some(n => n.relPath === relPath)
          if (!stillThere) missing.push({ relPath, meta: known[relPath] })
        }
        this.lastScanReport = { added, missing }
        return { ok: true, added, missing, tree, notes }
      } catch (e) {
        this.error = '扫描目录失败：' + e.message
        return { ok: false, msg: this.error }
      } finally {
        this.loading = false
      }
    },

    /** 登记（或更新）一个笔记到 kgMeta.notes */
    _indexNote(relPath, patch = {}) {
      if (!this.kgMeta) return
      const prev = this.kgMeta.notes[relPath] || {}
      this.kgMeta.notes[relPath] = {
        name: patch.name || prev.name || relPath.split('/').pop(),
        relPath,
        title: patch.title ?? prev.title,
        tags: patch.tags ?? prev.tags ?? [],
        backendFileId: patch.backendFileId ?? prev.backendFileId ?? null,
        updatedAt: Date.now(),
        digest: patch.digest ?? prev.digest ?? null,
        syncedDigest: patch.syncedDigest ?? prev.syncedDigest ?? null
      }
    },

    // ==================== 笔记 CRUD ====================

    /** 新建笔记文件（默认落在当前目录或指定子目录） */
    async createNote(dirRelPath = '', fileName = '') {
      const ws = this.currentWorkspace
      if (!ws) return { ok: false, msg: '未选择工作区' }
      try {
        const { fileHandle, relPath } = await createNoteFile(ws.handle, dirRelPath, fileName || '未命名笔记')
        const file = await fileHandle.getFile()
        const content = await file.text()
        const meta = await this._ensureKgMeta()
        this._indexNote(relPath, {
          name: relPath.split('/').pop(),
          title: extractTitle(content, relPath.split('/').pop()),
          digest: contentDigest(content)
        })
        await this.saveKgMeta()
        await this.rescan()
        // 打开新文件进入编辑态
        await this.openNote(relPath)
        return { ok: true, relPath }
      } catch (e) {
        this.error = '新建笔记失败：' + e.message
        return { ok: false, msg: this.error }
      }
    },

    /** 打开笔记（从磁盘读取最新内容） */
    async openNote(relPath) {
      const note = this.notes.find(n => n.relPath === relPath)
      if (!note) return { ok: false, msg: '笔记不存在（可能已被删除）：' + relPath }
      // 保存中的内容先落盘，避免切换丢失
      if (this.currentOpenNote && this.currentOpenNote.relPath === relPath) {
        return { ok: true, note: this.currentOpenNote }
      }
      try {
        const content = await readTextFile(note.fileHandle)
        const fileName = note.name
        const known = this.kgMeta?.notes?.[relPath]
        const digest = contentDigest(content)
        this.currentOpenNote = {
          name: fileName,
          relPath,
          dirRelPath: note.dirRelPath,
          title: known?.title || extractTitle(content, fileName),
          content,
          digest,
          savedAt: Date.now(),
          tags: known?.tags || [],
          backendFileId: known?.backendFileId || null,
          syncedDigest: known?.syncedDigest || null,
          syncError: null
        }
        // 首次出现的外部文件自动登记进 kg.json
        if (!known) {
          await this._ensureKgMeta()
          this._indexNote(relPath, {
            name: fileName,
            title: this.currentOpenNote.title,
            digest
          })
          await this.saveKgMeta()
        }
        this.saveState = 'clean'
        this.error = null
        return { ok: true, note: this.currentOpenNote }
      } catch (e) {
        this.error = '打开笔记失败：' + e.message
        return { ok: false, msg: this.error }
      }
    },

    /**
     * 保存当前笔记：先写本地 .md（权威），再更新 kg.json 元数据，
     * 后端在线时经 _backendSync 双写（Stage D）。
     */
    async saveNote() {
      const note = this.currentOpenNote
      const ws = this.currentWorkspace
      if (!note || !ws) return { ok: false, msg: '没有打开的笔记' }
      this.saveState = 'saving'
      try {
        const item = this.notes.find(n => n.relPath === note.relPath)
        if (!item) throw new Error('笔记句柄失效，请重扫目录')
        await writeTextFile(item.fileHandle, note.content)
        const digest = contentDigest(note.content)

        // 本地元数据双写
        await this._ensureKgMeta()
        this._indexNote(note.relPath, {
          name: note.name,
          title: note.title || extractTitle(note.content, note.name),
          tags: note.tags || [],
          digest,
          backendFileId: note.backendFileId
        })
        await this.saveKgMeta()

        note.digest = digest
        note.savedAt = Date.now()
        this.saveState = 'clean'

        // 后端双写钩子（Stage D 接入 file 同步 / 重命名 / 解析）
        await this._backendSync(note)
        return { ok: true }
      } catch (e) {
        this.saveState = 'error'
        this.error = '保存失败：' + e.message
        return { ok: false, msg: this.error }
      }
    },

    /** 编辑器内容更新（由编辑器防抖调用） */
    setDraft(content) {
      if (!this.currentOpenNote) return
      if (this.currentOpenNote.content === content) return
      this.currentOpenNote.content = content
      this.saveState = 'dirty'
    },

    /** 修改标题（同步刷新 kg.json 索引） */
    async updateTitle(title) {
      const note = this.currentOpenNote
      if (!note) return false
      note.title = title || note.name.replace(/\.(md|markdown|txt)$/i, '')
      this._indexNote(note.relPath, { name: note.name, title: note.title })
      await this.saveKgMeta()
      return true
    },

    /**
     * 重命名笔记文件（本地 move），kg.json 键路径同步迁移；
     * 若已同步后端（backendFileId 存在），标记待同步并触发 _backendSync。
     */
    async renameNote(relPath, newName) {
      const ws = this.currentWorkspace
      if (!ws) return { ok: false, msg: '未选择工作区' }
      const wasOpen = this.currentOpenNote?.relPath === relPath
      try {
        const meta = this.kgMeta?.notes?.[relPath]
        const newRelPath = await renameEntry(ws.handle, relPath, newName, 'file')
        // kg.json 键迁移
        if (meta && newRelPath !== relPath) {
          await this._ensureKgMeta()
          const migrated = { ...meta, relPath: newRelPath, name: newRelPath.split('/').pop(), updatedAt: Date.now() }
          delete this.kgMeta.notes[relPath]
          this.kgMeta.notes[newRelPath] = migrated
          await this.saveKgMeta()
        }
        // 本地索引刷新
        const report = await this.rescan()
        // 若重命名的是当前编辑文件，重开以更新句柄
        if (wasOpen) {
          const note = this.currentOpenNote
          this.currentOpenNote = null
          await this.openNote(newRelPath)
          if (note) {
            this.currentOpenNote.title = note.title
            this.currentOpenNote.content = note.content
            this.currentOpenNote.tags = note.tags || []
            this.saveState = 'clean'
          }
        }
        // 后端同步钩子（重命名）
        if (meta && meta.backendFileId) {
          await this._backendRenameSync(relPath, newRelPath, meta.backendFileId)
        }
        return { ok: true, relPath: newRelPath, scan: report }
      } catch (e) {
        this.error = '重命名失败：' + e.message
        return { ok: false, msg: this.error }
      }
    },

    /**
     * 删除笔记（本地文件 + kg.json 索引）。
     * 知识节点保留：已入库的笔记（backendFileId）仅登记 removed 历史，
     * 不主动调用后端删除节点 —— 真正清库属于「彻底删除」模块。
     */
    async deleteNote(relPath) {
      const ws = this.currentWorkspace
      if (!ws) return { ok: false, msg: '未选择工作区' }
      try {
        const meta = this.kgMeta?.notes?.[relPath]
        await deleteEntry(ws.handle, relPath, 'file')
        // kg.json：登记删除历史（保留 backendFileId，知识节点不删）
        await this._ensureKgMeta()
        if (meta) {
          this.kgMeta.removed.push({
            relPath,
            name: meta.name || relPath.split('/').pop(),
            removedAt: Date.now(),
            backendFileId: meta.backendFileId || null
          })
          delete this.kgMeta.notes[relPath]
        }
        await this.saveKgMeta()
        // 当前打开的笔记被删除时关闭编辑态
        if (this.currentOpenNote?.relPath === relPath) {
          this.currentOpenNote = null
          this.saveState = 'clean'
        }
        await this.rescan()
        return { ok: true }
      } catch (e) {
        this.error = '删除失败：' + e.message
        return { ok: false, msg: this.error }
      }
    },

    // ==================== 后端双写钩子（Stage D 实装） ====================

    /** 构造后端 file 的幂等映射键：'ws:{workspaceId}:{relPath}' */
    _sourcePath(relPath) {
      const wsId = this.kgMeta?.workspace?.id || 'unknown'
      return `ws:${wsId}:${relPath}`
    },

    /**
     * 保存后的后端同步（本地为源）：
     *  - 首次同步（backendFileId 空）→ 后端按 source_path 建 File 并解析；
     *  - 内容不变（digest 相同）→ 跳过，不产生无谓重解析；
     *  - 内容变化 → 更新后端 File 内容并清旧节点重解析；
     *  - 后端不可达 → 静默降级（本地权威不受影响），UI 以 syncError 提示可稍后重试。
     */
    async _backendSync(note) {
      if (!note || !this.kgMeta) return { ok: true, synced: false, skipped: true }
      const known = this.kgMeta.notes?.[note.relPath]
      if (known && known.syncedDigest && known.syncedDigest === note.digest) {
        return { ok: true, synced: false, skipped: true }
      }
      try {
        const res = await fileAPI.syncLocal({
          sourcePath: this._sourcePath(note.relPath),
          name: note.name,
          content: note.content
        })
        if (!res?.ok) throw new Error(res?.message || '同步失败')
        // 登记 backendFileId + 已同步摘要，落盘 kg.json
        note.backendFileId = res.file_id
        note.syncError = null
        this._indexNote(note.relPath, {
          name: note.name,
          title: note.title,
          backendFileId: res.file_id,
          digest: note.digest,
          syncedDigest: note.digest
        })
        await this.saveKgMeta()
        return { ok: true, synced: true, fileId: res.file_id }
      } catch (e) {
        console.warn('[folderStore] backend sync skipped (offline?):', e.message)
        note.syncError = e.message
        return { ok: true, synced: false, error: e.message }
      }
    },

    /** 重命名后端文件记录：name 与新 relPath 对应，source_path 键同步迁移 */
    async _backendRenameSync(oldRelPath, newRelPath, backendFileId) {
      const newName = newRelPath.split('/').pop()
      try {
        const res = await fileAPI.renameFile(backendFileId, {
          name: newName,
          sourcePath: this._sourcePath(newRelPath)
        })
        if (!res?.ok) throw new Error(res?.message || '同步失败')
        return { ok: true, synced: true }
      } catch (e) {
        console.warn('[folderStore] backend rename sync failed:', e.message)
        return { ok: true, synced: false, error: e.message }
      }
    }
  },
  persist: false
})
