/**
 * folderFs.js
 * File System Access API 封装 —— 「本地文件夹工作区」的底层读写工具。
 *
 * 设计原则：
 *  - 本地 .md/.txt 为权威数据源；.kg_meta/kg.json 存放知识图谱元数据（本地双写本体）
 *  - 目录结构约定：
 *      <root>/
 *        ├── .kg_meta/
 *        │     └── kg.json          ← 本地知识元数据（笔记索引/节点/关系/分组快照）
 *        └── (任意层级) .md/.markdown/.txt ← 笔记正文
 *  - 所有函数尽量返回结构化的 { ok, ... } 或直接 throw，由调用方（folderStore）统一消化
 *
 * 环境：File System Access API 仅存在于 Chromium 系浏览器，且要求安全上下文
 *       （https 或 localhost）。不支持时 fsSupported() 返回 false，UI 显示降级提示。
 */

/** 应用元数据目录名 */
export const KG_META_DIR = '.kg_meta'
/** 元数据文件名 */
export const KG_META_FILE = 'kg.json'

/** 参与知识解析的文本扩展名 */
const TEXT_EXTS = new Set(['md', 'markdown', 'txt', 'mdown', 'mkd'])

/** 目录扫描时需要跳过的目录（点目录通常为工具目录） */
const SKIP_DIRS = new Set([KG_META_DIR, '.git', '.svn', '.hg', '.idea', '.vscode', 'node_modules', 'dist', '.DS_Store'])

/**
 * 浏览器是否支持 File System Access API
 * @returns {boolean}
 */
export function fsSupported() {
  return typeof window !== 'undefined'
    && typeof window.showDirectoryPicker === 'function'
}

/**
 * 弹出系统目录选择框，请求读写授权
 * @returns {Promise<FileSystemDirectoryHandle>}
 */
export async function pickRootDir() {
  if (!fsSupported()) {
    throw new Error('当前浏览器不支持 File System Access API，请使用最新版 Chrome / Edge（需要 https 或 localhost 环境）')
  }
  return window.showDirectoryPicker({ mode: 'readwrite', id: 'kg-root' })
}

/**
 * 请求目录句柄的读写权限（恢复工作区时需要）
 * @param {FileSystemDirectoryHandle} dirHandle
 * @returns {Promise<'granted'|'prompt'|'denied'>}
 */
export async function requestDirPermission(dirHandle) {
  const opts = { mode: 'readwrite' }
  let state = dirHandle.queryPermission ? await dirHandle.queryPermission(opts) : 'granted'
  if (state === 'prompt' && dirHandle.requestPermission) {
    state = await dirHandle.requestPermission(opts)
  }
  return state
}

/**
 * 递归扫描目录树，构建可渲染树结构 + 扁平笔记索引。
 * 返回结果不包含文件内容（内容按需 openNote 时读取）。
 *
 * @param {FileSystemDirectoryHandle} dirHandle 根目录句柄
 * @param {object} opts
 * @param {string} [opts.prefix=''] 相对根目录的路径前缀（内部递归用）
 * @param {string} [opts.parentRel=''] 父级相对路径（内部递归用）
 * @returns {Promise<{tree: object, notes: Array}>}
 *          tree = { name, relPath, kind:'dir', dirHandle, children:[...] }
 *          notes = [{ name, relPath, kind:'file', fileHandle, dirRelPath }]
 */
export async function scanDirTree(dirHandle, opts = {}) {
  const prefix = opts.prefix || ''
  const parentRel = opts.parentRel || ''
  const tree = {
    name: prefix || dirHandle.name,
    relPath: prefix || '',
    kind: 'dir',
    dirHandle,
    children: []
  }
  const notes = []

  const entries = []
  // FileSystemDirectoryHandle 的 values() 异步迭代
  for await (const entry of dirHandle.values()) {
    entries.push(entry)
  }

  // 目录优先，便于稳定展示
  entries.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'directory' ? -1 : 1
    return a.name.localeCompare(b.name, 'zh')
  })

  for (const entry of entries) {
    const relPath = (parentRel ? parentRel + '/' : '') + entry.name

    if (entry.kind === 'directory') {
      if (SKIP_DIRS.has(entry.name)) continue
      const sub = await scanDirTree(entry, {
        prefix: relPath,
        parentRel: relPath
      })
      tree.children.push(sub.tree)
      notes.push(...sub.notes)
    } else {
      const ext = entry.name.split('.').pop().toLowerCase()
      if (!TEXT_EXTS.has(ext)) continue
      const noteItem = {
        name: entry.name,
        relPath,
        kind: 'file',
        fileHandle: entry,
        dirRelPath: parentRel
      }
      tree.children.push(noteItem)
      notes.push(noteItem)
    }
  }

  return { tree, notes }
}

/**
 * 将相对路径逐级解析出目录句柄（不创建）。
 * @param {FileSystemDirectoryHandle} rootDir
 * @param {string} dirRelPath 形如 "sub/dir" 或 ""
 * @returns {Promise<FileSystemDirectoryHandle>}
 */
export async function resolveDirHandle(rootDir, dirRelPath) {
  if (!dirRelPath) return rootDir
  let cur = rootDir
  for (const seg of dirRelPath.split('/').filter(Boolean)) {
    cur = await cur.getDirectoryHandle(seg)
  }
  return cur
}

/**
 * 打开 .kg_meta 目录（不存在则创建）
 * @param {FileSystemDirectoryHandle} rootDir
 * @returns {Promise<FileSystemDirectoryHandle>}
 */
export async function ensureMetaDir(rootDir) {
  return rootDir.getDirectoryHandle(KG_META_DIR, { create: true })
}

/**
 * 读取 .kg_meta/kg.json；不存在或解析失败时返回 null（不自动创建默认值）
 * @param {FileSystemDirectoryHandle} rootDir
 * @returns {Promise<object|null>}
 */
export async function readKgMeta(rootDir) {
  try {
    const metaDir = await ensureMetaDir(rootDir)
    const fh = await metaDir.getFileHandle(KG_META_FILE)
    const file = await fh.getFile()
    const text = await file.text()
    const meta = text ? JSON.parse(text) : null
    return meta && typeof meta === 'object' ? meta : null
  } catch (e) {
    if (e && e.name === 'NotFoundError') return null
    console.warn('[folderFs] readKgMeta failed:', e.message)
    return null
  }
}

/**
 * 序列化写入 .kg_meta/kg.json
 * @param {FileSystemDirectoryHandle} rootDir
 * @param {object} meta
 * @returns {Promise<boolean>}
 */
export async function writeKgMeta(rootDir, meta) {
  const metaDir = await ensureMetaDir(rootDir)
  const fh = await metaDir.getFileHandle(KG_META_FILE, { create: true })
  const w = await fh.createWritable()
  let aborted = false
  try {
    await w.write(JSON.stringify(meta, null, 2))
  } catch (e) {
    // 写入失败：放弃本次写入流（abort 后不可再 close），原样抛出由调用方处理
    aborted = true
    await w.abort()
    throw e
  } finally {
    if (!aborted) await w.close()
  }
  return true
}

/**
 * 读取文本文件内容
 * @param {FileSystemFileHandle} fileHandle
 * @returns {Promise<string>}
 */
export async function readTextFile(fileHandle) {
  const file = await fileHandle.getFile()
  return file.text()
}

/**
 * 写文本内容到文件（整体覆盖）
 * @param {FileSystemFileHandle} fileHandle
 * @param {string} content
 * @returns {Promise<boolean>}
 */
export async function writeTextFile(fileHandle, content) {
  const w = await fileHandle.createWritable()
  let aborted = false
  try {
    await w.write(content)
  } catch (e) {
    // 写入失败：放弃本次写入流（abort 后不可再 close），原样抛出由调用方处理
    aborted = true
    await w.abort()
    throw e
  } finally {
    if (!aborted) await w.close()
  }
  return true
}

/**
 * 新建 Markdown 笔记（带默认标题模板）
 * @param {FileSystemDirectoryHandle} rootDir
 * @param {string} dirRelPath 新建文件所在子目录相对路径（'' 表示根目录）
 * @param {string} fileName 不含扩展名的笔记名
 * @returns {Promise<{fileHandle: FileSystemFileHandle, relPath: string}>}
 */
export async function createNoteFile(rootDir, dirRelPath, fileName) {
  const safeName = (fileName || '未命名笔记').trim().replace(/[\\/:*?"<>|]/g, '_')
  // 拆分「基底名 + 扩展名」，同名冲突时自动追加 (1)(2)... 避免覆盖已有文件
  const baseName = safeName.replace(/\.(md|markdown|txt)$/i, '')
  const ext = (safeName.match(/\.(md|markdown|txt)$/i) || ['.md'])[0]
  const dir = await resolveDirHandle(rootDir, dirRelPath)

  let fh = null
  let fullName = ''
  for (let i = 0; i < 100; i++) {
    const stem = i === 0 ? baseName : `${baseName} (${i})`
    fullName = stem + ext
    try {
      fh = await dir.getFileHandle(fullName, { create: true })
      const file = await fh.getFile()
      // 文件为空 = 本次新建（或恰好空文件），才写标题模板；非空视为既有内容跳过
      if (file.size > 0) {
        // 关键：清空 fh 再试下一个候选名，避免循环结束后残留既有文件句柄导致误写
        fh = null
        continue
      }
      await writeTextFile(fh, `# ${stem}\n\n`)
      break
    } catch (e) {
      if (e && e.name === 'NotAllowedError') throw e
      // 其它错误（如冲突检查失败）继续尝试下一个候选名
    }
  }
  if (!fh) throw new Error('无法在当前目录创建唯一文件（名称冲突过多）')
  const relPath = (dirRelPath ? dirRelPath + '/' : '') + fullName
  return { fileHandle: fh, relPath }
}

/**
 * 重命名目录内条目（文件或目录）
 * @param {FileSystemDirectoryHandle} rootDir
 * @param {string} oldRelPath 相对路径
 * @param {string} newName 新名称（含扩展名）
 * @param {string} kind 'file'|'directory'
 * @returns {Promise<string>} 新的相对路径
 */
export async function renameEntry(rootDir, oldRelPath, newName, kind = 'file') {
  const segs = oldRelPath.split('/').filter(Boolean)
  const oldBaseName = segs.pop()
  const parentDir = await resolveDirHandle(rootDir, segs.join('/'))

  const getter = kind === 'directory' ? 'getDirectoryHandle' : 'getFileHandle'
  const target = await parentDir[getter](oldBaseName)
  if (!target.move) {
    throw new Error('当前浏览器不支持句柄移动（rename），请在较新 Chrome/Edge 中使用')
  }
  const newNameSafe = newName.trim().replace(/[\\/:*?"<>|]/g, '_') || oldBaseName
  await target.move(parentDir, newNameSafe)
  return (segs.length ? segs.join('/') + '/' : '') + newNameSafe
}

/**
 * 删除目录内条目（文件或目录，目录需为空）
 * @param {FileSystemDirectoryHandle} rootDir
 * @param {string} relPath
 * @param {string} kind
 * @returns {Promise<boolean>}
 */
export async function deleteEntry(rootDir, relPath, kind = 'file') {
  const segs = relPath.split('/').filter(Boolean)
  const baseName = segs.pop()
  const parentDir = await resolveDirHandle(rootDir, segs.join('/'))
  // removeEntry 对文件与目录统一使用同名方法，recursive 用于非空目录
  await parentDir.removeEntry(baseName, { recursive: kind === 'directory' })
  return true
}

/** 判断相对路径是否以 .md 等文本扩展名结尾 */
export function isTextNoteRelPath(relPath) {
  const ext = relPath.split('.').pop().toLowerCase()
  return TEXT_EXTS.has(ext)
}

/**
 * 从文件内容提取展示标题（取首个 # 一级标题或文件名）
 * @param {string} content
 * @param {string} fileName
 * @returns {string}
 */
export function extractTitle(content, fileName) {
  const m = /^\s*#\s+(.+?)\s*$/m.exec(content || '')
  if (m) return m[1].trim()
  return (fileName || '未命名').replace(/\.(md|markdown|txt)$/i, '')
}

/**
 * 简易内容指纹（djb2 变体，用于脏检测，非加密用途）
 * @param {string} text
 * @returns {string}
 */
export function contentDigest(text) {
  let h = 5381
  const s = text || ''
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) >>> 0
  }
  return 'd' + h.toString(36)
}
