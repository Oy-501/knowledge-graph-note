/**
 * folderFs.js File System Access API 封装
 */
export const KG_META_DIR = '.kg_meta'
export const KG_META_FILE = 'kg.json'

const TEXT_EXTS = new Set(['md', 'markdown', 'txt', 'mdown', 'mkd'])
const SKIP_DIRS = new Set([KG_META_DIR, '.git', '.svn', '.hg', '.idea', '.vscode', 'node_modules', 'dist', '.DS_Store'])

export function fsSupported() { return typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function' }

export async function pickRootDir() {
  if (!fsSupported()) throw new Error('当前浏览器不支持 File System Access API，请使用最新版 Chrome / Edge（需要 https 或 localhost 环境）')
  return window.showDirectoryPicker({ mode: 'readwrite', id: 'kg-root' })
}

export async function requestDirPermission(dirHandle) {
  const opts = { mode: 'readwrite' }
  let state = dirHandle.queryPermission ? await dirHandle.queryPermission(opts) : 'granted'
  if (state === 'prompt' && dirHandle.requestPermission) state = await dirHandle.requestPermission(opts)
  return state
}

export async function scanDirTree(dirHandle, opts = {}) {
  const prefix = opts.prefix || ''; const parentRel = opts.parentRel || ''
  const tree = { name: prefix || dirHandle.name, relPath: prefix || '', kind: 'dir', dirHandle, children: [] }
  const notes = []; const entries = []
  for await (const entry of dirHandle.values()) entries.push(entry)
  entries.sort((a, b) => { if (a.kind !== b.kind) return a.kind === 'directory' ? -1 : 1; return a.name.localeCompare(b.name, 'zh') })
  for (const entry of entries) {
    const relPath = (parentRel ? parentRel + '/' : '') + entry.name
    if (entry.kind === 'directory') {
      if (SKIP_DIRS.has(entry.name)) continue
      const sub = await scanDirTree(entry, { prefix: relPath, parentRel: relPath })
      tree.children.push(sub.tree); notes.push(...sub.notes)
    } else {
      const ext = entry.name.split('.').pop().toLowerCase()
      if (!TEXT_EXTS.has(ext)) continue
      const noteItem = { name: entry.name, relPath, kind: 'file', fileHandle: entry, dirRelPath: parentRel }
      tree.children.push(noteItem); notes.push(noteItem)
    }
  }
  return { tree, notes }
}

export async function resolveDirHandle(rootDir, dirRelPath) {
  if (!dirRelPath) return rootDir
  let cur = rootDir
  for (const seg of dirRelPath.split('/').filter(Boolean)) cur = await cur.getDirectoryHandle(seg)
  return cur
}

export async function ensureMetaDir(rootDir) { return rootDir.getDirectoryHandle(KG_META_DIR, { create: true }) }

export async function readKgMeta(rootDir) {
  try {
    const metaDir = await ensureMetaDir(rootDir)
    const fh = await metaDir.getFileHandle(KG_META_FILE)
    const file = await fh.getFile(); const text = await file.text()
    const meta = text ? JSON.parse(text) : null
    return meta && typeof meta === 'object' ? meta : null
  } catch (e) {
    if (e && e.name === 'NotFoundError') return null
    console.warn('[folderFs] readKgMeta failed:', e.message)
    return null
  }
}

export async function writeKgMeta(rootDir, meta) {
  const metaDir = await ensureMetaDir(rootDir)
  const fh = await metaDir.getFileHandle(KG_META_FILE, { create: true })
  const w = await fh.createWritable(); let aborted = false
  try { await w.write(JSON.stringify(meta, null, 2)) }
  catch (e) { aborted = true; await w.abort(); throw e }
  finally { if (!aborted) await w.close() }
  return true
}

export async function readTextFile(fileHandle) { const file = await fileHandle.getFile(); return file.text() }

export async function writeTextFile(fileHandle, content) {
  const w = await fileHandle.createWritable(); let aborted = false
  try { await w.write(content) }
  catch (e) { aborted = true; await w.abort(); throw e }
  finally { if (!aborted) await w.close() }
  return true
}

export async function createNoteFile(rootDir, dirRelPath, fileName) {
  const safeName = (fileName || '未命名笔记').trim().replace(/[\\/:*?"<>|]/g, '_')
  const baseName = safeName.replace(/\.(md|markdown|txt)$/i, '')
  const ext = (safeName.match(/\.(md|markdown|txt)$/i) || ['.md'])[0]
  const dir = await resolveDirHandle(rootDir, dirRelPath)
  let fh = null; let fullName = ''
  for (let i = 0; i < 100; i++) {
    const stem = i === 0 ? baseName : `${baseName} (${i})`
    fullName = stem + ext
    try {
      fh = await dir.getFileHandle(fullName, { create: true })
      const file = await fh.getFile()
      if (file.size > 0) { fh = null; continue }
      await writeTextFile(fh, `# ${stem}\n\n`)
      break
    } catch (e) { if (e && e.name === 'NotAllowedError') throw e }
  }
  if (!fh) throw new Error('无法在当前目录创建唯一文件（名称冲突过多）')
  const relPath = (dirRelPath ? dirRelPath + '/' : '') + fullName
  return { fileHandle: fh, relPath }
}

export async function renameEntry(rootDir, oldRelPath, newName, kind = 'file') {
  const segs = oldRelPath.split('/').filter(Boolean); const oldBaseName = segs.pop()
  const parentDir = await resolveDirHandle(rootDir, segs.join('/'))
  const getter = kind === 'directory' ? 'getDirectoryHandle' : 'getFileHandle'
  const target = await parentDir[getter](oldBaseName)
  if (!target.move) throw new Error('当前浏览器不支持句柄移动（rename），请在较新 Chrome/Edge 中使用')
  const newNameSafe = newName.trim().replace(/[\\/:*?"<>|]/g, '_') || oldBaseName
  await target.move(parentDir, newNameSafe)
  return (segs.length ? segs.join('/') + '/' : '') + newNameSafe
}

export async function deleteEntry(rootDir, relPath, kind = 'file') {
  const segs = relPath.split('/').filter(Boolean); const baseName = segs.pop()
  const parentDir = await resolveDirHandle(rootDir, segs.join('/'))
  await parentDir.removeEntry(baseName, { recursive: kind === 'directory' })
  return true
}

export function isTextNoteRelPath(relPath) {
  const ext = relPath.split('.').pop().toLowerCase()
  return TEXT_EXTS.has(ext)
}

export function extractTitle(content, fileName) {
  const m = /^\s*#\s+(.+?)\s*$/m.exec(content || '')
  if (m) return m[1].trim()
  return (fileName || '未命名').replace(/\.(md|markdown|txt)$/i, '')
}

export function contentDigest(text) {
  let h = 5381; const s = text || ''
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0
  return 'd' + h.toString(36)
}
