/**
 * configStore.js
 * 四维权重 α/β/γ/δ、关联阈值、知识库开关、持久化
 */
import { defineStore } from 'pinia'

export const useConfigStore = defineStore('config', {
  state: () => ({
    // 四维权重（新默认配比：降低语义向量，提高知识库权威）
    w_alpha: 0.15, // α: 关键词 Jaccard 重合度
    w_beta: 0.25,  // β: 语义向量余弦（核心调整：降低"像但不对"的误连）
    w_gamma: 0.50, // γ: 知识库推理（核心调整：提高知识库权威性）
    w_delta: 0.10, // δ: 拓扑邻居重叠

    // 关联阈值
    threshold: 0.15,

    // 知识库推理总开关
    corpusEnabled: true,

    // 显示开关
    showSystemNodes: false, // 是否显示系统知识库节点
    showSemanticBridge: true,
    showCorpusLinks: true,
    showUserLinks: true,
    showCrossTemporal: true,

    // 模型加载状态
    vectorEngineReady: false,
    vectorEngineMode: 'pending'
  }),
  getters: {
    weights(state) {
      return {
        alpha: state.w_alpha,
        beta: state.w_beta,
        gamma: state.w_gamma,
        delta: state.w_delta
      }
    },
    totalWeight(state) {
      return state.w_alpha + state.w_beta + state.w_gamma + state.w_delta
    },
    normalizedWeights(state) {
      const tot = state.w_alpha + state.w_beta + state.w_gamma + state.w_delta || 1
      return {
        alpha: state.w_alpha / tot,
        beta: state.w_beta / tot,
        gamma: state.w_gamma / tot,
        delta: state.w_delta / tot
      }
    }
  },
  actions: {
    setWeight(name, v) {
      const key = 'w_' + name
      if (key in this.$state) this[key] = Number(v)
    },
    setThreshold(v) { this.threshold = Number(v) },
    toggleCorpus(v) { this.corpusEnabled = v ?? !this.corpusEnabled },
    setEngineReady(info) {
      this.vectorEngineReady = info && (info.mode === 'transformers' || info.mode === 'fallback-tfidf' || info.mode === 'fallback-ngram')
      this.vectorEngineMode = info?.mode || 'pending'
    },
    resetWeights() {
      this.w_alpha = 0.15
      this.w_beta = 0.25
      this.w_gamma = 0.50
      this.w_delta = 0.10
      this.threshold = 0.15
      this.corpusEnabled = true
    }
  },
  persist: {
    key: 'kg-config-v1',
    storage: localStorage
  }
})
