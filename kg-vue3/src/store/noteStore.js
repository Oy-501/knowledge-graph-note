/**
 * noteStore.js（混合架构版）
 */
import { defineStore } from 'pinia'
import { dbPut, dbGetAll, dbDelete, STORE_NOTES } from './indexedDB'
import { noteAPI } from '@/api/index'

function generateId() { return 'note_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8) }

export const useNoteStore = defineStore('note', {
  state: () => ({ notes: [], currentNoteId: null, loading: false, _backendReady: false }),
  getters: {
    noteCount: (s) => s.notes.length,
    currentNote: (s) => s.notes.find(n => n.id === s.currentNoteId) || null,
    sortedNotes: (s) => [...s.notes].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
  },
  actions: {
    async loadNotes() {
      try {
        const result = await noteAPI.list()
        if (result.notes) {
          this.notes = result.notes.map(n => ({ id: n.id, title: n.title, content: n.content || '', tags: n.tags || [], createdAt: n.created_at ? new Date(n.created_at).getTime() : Date.now(), updatedAt: n.updated_at ? new Date(n.updated_at).getTime() : Date.now(), linkedFiles: n.linked_files || [], linkedNodes: n.linked_nodes || [], linkedNotes: [], archived: n.archived || false, validationReport: n.validation_report || null, validationStatus: n.validation_status || null, accuracyScore: n.accuracy_score || 0, verified: n.verified || false }))
          this._backendReady = true; return
        }
      } catch (e) { console.warn('[noteStore] backend load failed, falling back to IndexedDB:', e.message); this._backendReady = false }
      try { this.notes = await dbGetAll(STORE_NOTES) } catch (e) { console.error('[noteStore] loadNotes failed', e); this.notes = [] }
    },
    async createNote(title = '未命名笔记', content = '') {
      const note = { id: generateId(), title, content, tags: [], createdAt: Date.now(), updatedAt: Date.now(), linkedFiles: [], linkedNodes: [], linkedNotes: [], validationReport: null, accuracyScore: 0, verified: false }
      if (this._backendReady) {
        try {
          const result = await noteAPI.save({ title, content, tags: [], linkedFiles: [], linkedNodes: [] })
          if (result.ok && result.note) { note.id = result.note.id; note.createdAt = result.note.created_at ? new Date(result.note.created_at).getTime() : Date.now(); note.updatedAt = result.note.updated_at ? new Date(result.note.updated_at).getTime() : Date.now() }
        } catch (e) { console.warn('[noteStore] backend create failed:', e.message) }
      }
      this.notes.push(note); await dbPut(STORE_NOTES, note); this.currentNoteId = note.id; return note
    },
    async saveNote(noteId, updates) {
      const idx = this.notes.findIndex(n => n.id === noteId); if (idx === -1) return false
      const note = this.notes[idx]
      Object.assign(note, updates, { updatedAt: Date.now() })
      this.notes[idx] = note
      if (this._backendReady) {
        try {
          await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null })
        } catch (e) { console.warn('[noteStore] backend save failed:', e.message) }
      }
      await dbPut(STORE_NOTES, note); return true
    },
    async deleteNote(noteId) {
      this.notes = this.notes.filter(n => n.id !== noteId)
      if (this._backendReady) { try { await noteAPI.delete(noteId) } catch (e) { console.warn('[noteStore] backend delete failed:', e.message) } }
      await dbDelete(STORE_NOTES, noteId)
      if (this.currentNoteId === noteId) this.currentNoteId = null
    },
    async linkFile(noteId, fileId) {
      const note = this.notes.find(n => n.id === noteId); if (!note) return false
      if (!note.linkedFiles.includes(fileId)) { note.linkedFiles.push(fileId); note.updatedAt = Date.now(); await dbPut(STORE_NOTES, note); if (this._backendReady) { try { await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, archived: typeof note.archived === 'boolean' ? note.archived : null, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null }) } catch (e) { console.warn('[noteStore] backend sync failed for linkFile:', e.message) } } }
      return true
    },
    async unlinkFile(noteId, fileId) {
      const note = this.notes.find(n => n.id === noteId); if (!note) return false
      note.linkedFiles = note.linkedFiles.filter(id => id !== fileId); note.updatedAt = Date.now(); await dbPut(STORE_NOTES, note)
      if (this._backendReady) { try { await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, archived: typeof note.archived === 'boolean' ? note.archived : null, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null }) } catch (e) { console.warn('[noteStore] backend sync failed for unlinkFile:', e.message) } }
      return true
    },
    async linkNode(noteId, nodeId) {
      const note = this.notes.find(n => n.id === noteId); if (!note) return false
      if (!note.linkedNodes.includes(nodeId)) { note.linkedNodes.push(nodeId); note.updatedAt = Date.now(); await dbPut(STORE_NOTES, note); if (this._backendReady) { try { await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, archived: typeof note.archived === 'boolean' ? note.archived : null, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null }) } catch (e) { console.warn('[noteStore] backend sync failed for linkNode:', e.message) } } }
      return true
    },
    async unlinkNode(noteId, nodeId) {
      const note = this.notes.find(n => n.id === noteId); if (!note) return false
      note.linkedNodes = note.linkedNodes.filter(id => id !== nodeId); note.updatedAt = Date.now(); await dbPut(STORE_NOTES, note)
      if (this._backendReady) { try { await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, archived: typeof note.archived === 'boolean' ? note.archived : null, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null }) } catch (e) { console.warn('[noteStore] backend sync failed for unlinkNode:', e.message) } }
      return true
    },
    async linkNote(noteId, targetNoteId) {
      const note = this.notes.find(n => n.id === noteId); if (!note || noteId === targetNoteId) return false
      if (!note.linkedNotes.includes(targetNoteId)) { note.linkedNotes.push(targetNoteId); note.updatedAt = Date.now(); await dbPut(STORE_NOTES, note); if (this._backendReady) { try { await noteAPI.save({ id: note.id, title: note.title, content: note.content, tags: note.tags, linkedFiles: note.linkedFiles, linkedNodes: note.linkedNodes, accuracyScore: note.accuracyScore, archived: typeof note.archived === 'boolean' ? note.archived : null, validationReport: note.validationReport || null, validationStatus: note.validationStatus || null, verified: typeof note.verified === 'boolean' ? note.verified : null }) } catch (e) { console.warn('[noteStore] backend sync failed for linkNote:', e.message) } } }
      return true
    },
    getNoteAssociations(noteId) { const note = this.notes.find(n => n.id === noteId); if (!note) return { files: [], nodes: [], notes: [] }; return { files: note.linkedFiles || [], nodes: note.linkedNodes || [], notes: note.linkedNotes || [] } },
    setCurrentNote(noteId) { this.currentNoteId = noteId }
  }
})
