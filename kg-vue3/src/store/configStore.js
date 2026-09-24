/**
 * configStore.js 四维权重 α/β/γ/δ、关联阈值、知识库开关、持久化
 */
import { defineStore } from 'pinia'

export const useConfigStore = defineStore('config', {
  state: () => ({
    w_alpha: 0.15, w_beta: 0.25, w_gamma: 0.50, w_delta: 0.10,
    threshold: 0.15,
    corpusEnabled: true,
    showSystemNodes: false, showSemanticBridge: true, showCorpusLinks: true, showUserLinks: true, showCrossTemporal: true,
    vectorEngineReady: false, vectorEngineMode: 'pending'
  }),
  getters: {
    weights(state) { return { alpha: state.w_alpha, beta: state.w_beta, gamma: state.w_gamma, delta: state.w_delta } },
    totalWeight(state) { return state.w_alpha + state.w_beta + state.w_gamma + state.w_delta },
    normalizedWeights(state) {
      const tot = state.w_alpha + state.w_beta + state.w_gamma + state.w_delta || 1
      return { alpha: state.w_alpha / tot, beta: state.w_beta / tot, gamma: state.w_gamma / tot, delta: state.w_delta / tot }
    }
  },
  actions: {
    setWeight(name, v) { const key = 'w_' + name; if (key in this.$state) this[key] = Number(v) },
    setThreshold(v) { this.threshold = Number(v) },
    toggleCorpus(v) { this.corpusEnabled = v ?? !this.corpusEnabled },
    setEngineReady(info) { this.vectorEngineReady = info && (info.mode === 'transformers' || info.mode === 'fallback-tfidf' || info.mode === 'fallback-ngram'); this.vectorEngineMode = info?.mode || 'pending' },
    resetWeights() { this.w_alpha = 0.15; this.w_beta = 0.25; this.w_gamma = 0.50; this.w_delta = 0.10; this.threshold = 0.15; this.corpusEnabled = true }
  },
  persist: { key: 'kg-config-v1', storage: localStorage }
})
