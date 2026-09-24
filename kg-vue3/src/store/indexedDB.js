/**
 * indexedDB.js
 * 共享 IndexedDB 工具函数
 */

const DB_NAME = 'kg-vue3-db'
const DB_VERSION = 4
const STORE_FILES = 'files'
const STORE_NODES = 'kp_nodes'
const STORE_NOTES = 'user_notes'
const STORE_FS_ROOTS = 'fs_roots'
const STORE_SETTINGS = 'user_settings'

let _db = null
export function openDb() {
  return new Promise((resolve, reject) => {
    if (_db) return resolve(_db)
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (ev) => {
      const db = ev.target.result
      if (!db.objectStoreNames.contains(STORE_FILES)) {
        db.createObjectStore(STORE_FILES, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(STORE_NODES)) {
        const os = db.createObjectStore(STORE_NODES, { keyPath: 'id' })
        os.createIndex('file_id', 'fileId', { unique: false })
      }
      if (!db.objectStoreNames.contains(STORE_NOTES)) {
        db.createObjectStore(STORE_NOTES, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(STORE_FS_ROOTS)) {
        // 本地文件夹工作区句柄（FileSystemDirectoryHandle 可结构化克隆）
        db.createObjectStore(STORE_FS_ROOTS, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(STORE_SETTINGS)) {
        db.createObjectStore(STORE_SETTINGS, { keyPath: 'id' })
      }
    }
    req.onblocked = () => reject(new Error('IndexedDB upgrade blocked by another tab'))
    req.onsuccess = () => {
      _db = req.result
      _db.onversionchange = () => {
        _db.close()
        _db = null
      }
      resolve(_db)
    }
    req.onerror = () => reject(req.error)
  })
}

export async function dbPut(store, val) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).put(val)
    tx.oncomplete = () => resolve(true)
    tx.onerror = () => reject(tx.error)
  })
}

export async function dbGetAll(store) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    if (!db.objectStoreNames.contains(store)) return resolve([])
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

export async function dbDelete(store, id) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).delete(id)
    tx.oncomplete = () => resolve(true)
    tx.onerror = () => reject(tx.error)
  })
}

export async function dbClear(store) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).clear()
    tx.oncomplete = () => resolve(true)
    tx.onerror = () => reject(tx.error)
  })
}

export async function dbGetByIndex(store, indexName, value) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).index(indexName).getAll(value)
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

export { STORE_FILES, STORE_NODES, STORE_NOTES, STORE_FS_ROOTS, STORE_SETTINGS }