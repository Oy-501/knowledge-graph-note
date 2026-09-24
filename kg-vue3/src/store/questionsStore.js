/**
 * questionsStore.js 问题与思考独立存储
 */
import { defineStore } from 'pinia'

export const useQuestionsStore = defineStore('questions', {
  state: () => ({ items: [], _fileGroups: null }),
  getters: {
    fileGroups(state) {
      const groups = {}
      for (const item of state.items) {
        if (!groups[item.fileId]) groups[item.fileId] = { fileId: item.fileId, fileName: item.fileName, items: [] }
        groups[item.fileId].items.push(item)
      }
      return Object.values(groups)
    },
    questions(state) { return state.items.filter(i => i.type === 'question') },
    thoughts(state) { return state.items.filter(i => i.type === 'thought') },
    examples(state) { return state.items.filter(i => i.type === 'example') },
    unresolvedCount(state) { return state.items.filter(i => !i.resolved).length },
    typeStats(state) { return { question: state.items.filter(i => i.type === 'question').length, thought: state.items.filter(i => i.type === 'thought').length, example: state.items.filter(i => i.type === 'example').length } }
  },
  actions: {
    addFromFile(fileId, fileName, parsed) {
      const now = Date.now(); const items = []
      for (const q of (parsed.questions || [])) items.push({ id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6), fileId, fileName, title: q.title, description: q.description, rawText: q.rawText, type: 'question', fileContext: parsed.fileContext || {}, createdAt: now, resolved: false })
      for (const t of (parsed.thoughts || [])) items.push({ id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6), fileId, fileName, title: t.title, description: t.description, rawText: t.rawText, type: 'thought', fileContext: parsed.fileContext || {}, createdAt: now, resolved: false })
      for (const e of (parsed.examples || [])) items.push({ id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6), fileId, fileName, title: e.title, description: e.description, rawText: e.rawText, type: 'example', fileContext: parsed.fileContext || {}, createdAt: now, resolved: false })
      if (items.length > 0) this.items.push(...items)
    },
    markResolved(itemId) { const item = this.items.find(i => i.id === itemId); if (item) item.resolved = true },
    markUnresolved(itemId) { const item = this.items.find(i => i.id === itemId); if (item) item.resolved = false },
    removeItem(itemId) { this.items = this.items.filter(i => i.id !== itemId) },
    removeByFile(fileId) { this.items = this.items.filter(i => i.fileId !== fileId) },
    reset() { this.items = [] }
  },
  persist: { key: 'kg-questions-v1', storage: localStorage }
})
