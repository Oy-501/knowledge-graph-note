/**
 * questionsStore.js
 * 问题与思考独立存储
 *
 * 功能：
 *  - 存储用户笔记中的问题、思考、示例（不进入知识图谱）
 *  - 独立于主知识图谱，不影响图谱逻辑
 *  - 持久化到 LocalStorage
 */

import { defineStore } from 'pinia'

export const useQuestionsStore = defineStore('questions', {
  state: () => ({
    /**
     * 条目列表
     * 每条记录：{ id, fileId, fileName, title, description, rawText, type, fileContext, createdAt, resolved }
     */
    items: [],

    /**
     * 按文件归组的视图
     * 运行时计算
     */
    _fileGroups: null
  }),

  getters: {
    /**
     * 按文件分组
     */
    fileGroups(state) {
      const groups = {}
      for (const item of state.items) {
        if (!groups[item.fileId]) {
          groups[item.fileId] = {
            fileId: item.fileId,
            fileName: item.fileName,
            items: []
          }
        }
        groups[item.fileId].items.push(item)
      }
      return Object.values(groups)
    },

    /**
     * 问题列表
     */
    questions(state) {
      return state.items.filter(i => i.type === 'question')
    },

    /**
     * 思考列表
     */
    thoughts(state) {
      return state.items.filter(i => i.type === 'thought')
    },

    /**
     * 示例列表
     */
    examples(state) {
      return state.items.filter(i => i.type === 'example')
    },

    /**
     * 未解决项数量
     */
    unresolvedCount(state) {
      return state.items.filter(i => !i.resolved).length
    },

    /**
     * 按类型统计
     */
    typeStats(state) {
      return {
        question: state.items.filter(i => i.type === 'question').length,
        thought: state.items.filter(i => i.type === 'thought').length,
        example: state.items.filter(i => i.type === 'example').length
      }
    }
  },

  actions: {
    /**
     * 从文件解析结果中添加问题/思考/示例
     * @param {string} fileId - 文件ID
     * @param {string} fileName - 文件名
     * @param {Object} parsed - parseMarkdown 返回的结果
     */
    addFromFile(fileId, fileName, parsed) {
      const now = Date.now()
      const items = []

      for (const q of (parsed.questions || [])) {
        items.push({
          id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6),
          fileId,
          fileName,
          title: q.title,
          description: q.description,
          rawText: q.rawText,
          type: 'question',
          fileContext: parsed.fileContext || {},
          createdAt: now,
          resolved: false
        })
      }

      for (const t of (parsed.thoughts || [])) {
        items.push({
          id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6),
          fileId,
          fileName,
          title: t.title,
          description: t.description,
          rawText: t.rawText,
          type: 'thought',
          fileContext: parsed.fileContext || {},
          createdAt: now,
          resolved: false
        })
      }

      for (const e of (parsed.examples || [])) {
        items.push({
          id: 'qst_' + now + '_' + Math.random().toString(36).slice(2, 6),
          fileId,
          fileName,
          title: e.title,
          description: e.description,
          rawText: e.rawText,
          type: 'example',
          fileContext: parsed.fileContext || {},
          createdAt: now,
          resolved: false
        })
      }

      if (items.length > 0) {
        this.items.push(...items)
      }
    },

    /**
     * 标记为已解决
     */
    markResolved(itemId) {
      const item = this.items.find(i => i.id === itemId)
      if (item) {
        item.resolved = true
      }
    },

    /**
     * 标记为未解决
     */
    markUnresolved(itemId) {
      const item = this.items.find(i => i.id === itemId)
      if (item) {
        item.resolved = false
      }
    },

    /**
     * 删除单个条目
     */
    removeItem(itemId) {
      this.items = this.items.filter(i => i.id !== itemId)
    },

    /**
     * 按文件删除所有相关条目
     */
    removeByFile(fileId) {
      this.items = this.items.filter(i => i.fileId !== fileId)
    },

    /**
     * 清空所有
     */
    reset() {
      this.items = []
    }
  },

  persist: {
    key: 'kg-questions-v1',
    storage: localStorage
  }
})