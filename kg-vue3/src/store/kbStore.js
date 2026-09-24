/**
 * kbStore.js
 * 知识库状态管理
 *
 * 定位：知识库是本系统的「知识权威源」。图谱建立在知识库之上，
 * 文件之间的关联由知识库概念空间决定（而不是文本语义相似度）。
 *
 * 职责：
 *  1) 知识库条目 / 关系 / 统计（概览与条目管理）
 *  2) 知识库文档上传理解（新增 / 同义合并 / 定义冲突 / 新增关系）
 *  3) 知识锚定匹配（一段文本命中了哪些知识点）
 *  4) 文件知识画像与文件间知识关联（含证据下钻）
 *  5) 重建关联链并通知图谱刷新
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { kbAPI } from '@/api/index'

export const useKbStore = defineStore('kb', () => {
  // ---- 概览 ----
  const stats = ref(null)
  const loadingStats = ref(false)

  // ---- 条目 ----
  const entries = ref([])
  const entryTotal = ref(0)
  const entryFilter = ref({ keyword: '', domain: '', level: 0 })
  const loadingEntries = ref(false)

  // ---- 关系与本体图 ----
  const relations = ref([])
  const graph = ref({ nodes: [], links: [] })
  const graphLoading = ref(false)

  // ---- 上传理解 ----
  const report = ref(null)          // 最近一次理解报告
  const previewing = ref(false)
  const importing = ref(false)
  const imports = ref([])

  // ---- 知识锚定 ----
  const matchResult = ref(null)
  const matching = ref(false)

  // ---- 文件知识关联 ----
  const fileProfiles = ref([])
  const fileLinks = ref([])
  const fileDetail = ref(null)
  const loadingFiles = ref(false)
  const rebuildThreshold = ref(0.15)
  const rebuilding = ref(false)

  // ---- getters ----
  const domains = computed(() => {
    const map = stats.value?.domains || {}
    return Object.entries(map)
      .map(([domain, count]) => ({ domain, count }))
      .sort((a, b) => b.count - a.count)
  })

  const coveredFiles = computed(() => fileProfiles.value.filter(f => f.concept_count > 0))
  const uncoveredFiles = computed(() => fileProfiles.value.filter(f => !f.concept_count))
  const avgCoverage = computed(() => {
    if (!fileProfiles.value.length) return 0
    const sum = fileProfiles.value.reduce((acc, f) => acc + (f.coverage || 0), 0)
    return sum / fileProfiles.value.length
  })

  // ---- actions ----
  async function loadStats() {
    loadingStats.value = true
    try {
      stats.value = await kbAPI.stats()
    } catch (e) {
      ElMessage.error(`知识库统计加载失败：${e.message}`)
    } finally {
      loadingStats.value = false
    }
  }

  async function loadEntries(extra = {}) {
    loadingEntries.value = true
    try {
      const params = { ...entryFilter.value, ...extra }
      const data = await kbAPI.entries(params)
      entries.value = data.entries || []
      entryTotal.value = data.total || 0
    } catch (e) {
      ElMessage.error(`知识点加载失败：${e.message}`)
    } finally {
      loadingEntries.value = false
    }
  }

  async function createEntry(payload) {
    const res = await kbAPI.createEntry(payload)
    if (res.ok) {
      ElMessage.success(res.message || '已新增知识点')
      await Promise.all([loadStats(), loadEntries(), loadGraph()])
    } else {
      ElMessage.warning(res.message || '新增失败')
    }
    return res
  }

  async function updateEntry(id, payload) {
    const res = await kbAPI.updateEntry(id, payload)
    if (res.ok) {
      ElMessage.success(res.message || '已更新知识点')
      await Promise.all([loadStats(), loadEntries(), loadRelations(), loadGraph()])
    } else {
      ElMessage.warning(res.message || '更新失败')
    }
    return res
  }

  async function deleteEntry(id) {
    const res = await kbAPI.deleteEntry(id)
    if (res.ok) {
      ElMessage.success(res.message || '已删除知识点')
      await Promise.all([loadStats(), loadEntries(), loadRelations(), loadGraph()])
    } else {
      ElMessage.warning(res.message || '删除失败')
    }
    return res
  }

  async function loadRelations(entity = '') {
    try {
      const data = await kbAPI.relations({ entity, limit: 200 })
      relations.value = data.relations || []
    } catch (e) {
      ElMessage.error(`知识库关系加载失败：${e.message}`)
    }
  }

  async function loadGraph(params = {}) {
    graphLoading.value = true
    try {
      graph.value = await kbAPI.graph(params)
    } catch (e) {
      ElMessage.error(`本体图加载失败：${e.message}`)
    } finally {
      graphLoading.value = false
    }
  }

  /** 上传知识库文档 → 理解（dryRun=true 只预览报告） */
  async function uploadKb(file, { dryRun = false, overwrite = false } = {}) {
    if (dryRun) previewing.value = true
    else importing.value = true
    try {
      const res = await kbAPI.upload(file, { dryRun, overwrite })
      report.value = res.report
      if (!dryRun && res.ok) {
        ElMessage.success(res.report?.summary || '知识库已导入')
        await refreshAll()
      }
      return res.report
    } catch (e) {
      ElMessage.error(`知识库理解失败：${e.message}`)
      return null
    } finally {
      previewing.value = false
      importing.value = false
    }
  }

  /** 粘贴文本理解 */
  async function previewText(text, name = '未命名知识库', dryRun = true) {
    if (dryRun) previewing.value = true
    else importing.value = true
    try {
      const res = await kbAPI.preview({ text, name, dryRun })
      report.value = res.report
      if (!dryRun) {
        ElMessage.success(res.report?.summary || '知识库已导入')
        await refreshAll()
      }
      return res.report
    } catch (e) {
      ElMessage.error(`理解失败：${e.message}`)
      return null
    } finally {
      previewing.value = false
      importing.value = false
    }
  }

  async function loadImports(limit = 20) {
    try {
      const data = await kbAPI.imports(limit)
      imports.value = data.imports || []
    } catch (e) {
      /* 历史加载失败不打断主流程 */
    }
  }

  async function loadImportDetail(id) {
    try {
      const data = await kbAPI.importDetail(id)
      if (data.ok) report.value = data.import.report
      return data.import
    } catch (e) {
      ElMessage.error(`报告读取失败：${e.message}`)
      return null
    }
  }

  /** 知识锚定：文本 → 命中的知识点 */
  async function matchText(text, limit = 30) {
    matching.value = true
    try {
      matchResult.value = await kbAPI.match(text, limit)
      return matchResult.value
    } catch (e) {
      ElMessage.error(`知识锚定失败：${e.message}`)
      return null
    } finally {
      matching.value = false
    }
  }

  async function loadFiles(threshold = 0) {
    loadingFiles.value = true
    try {
      const data = await kbAPI.files(threshold)
      fileProfiles.value = data.files || []
      fileLinks.value = data.links || []
    } catch (e) {
      ElMessage.error(`文件知识画像加载失败：${e.message}`)
    } finally {
      loadingFiles.value = false
    }
  }

  async function loadFileDetail(fileId) {
    try {
      fileDetail.value = await kbAPI.fileDetail(fileId)
      return fileDetail.value
    } catch (e) {
      ElMessage.error(`文件画像读取失败：${e.message}`)
      return null
    }
  }

  /** 重建关联链：知识库关系 → 文件锚定 → 知识画像 → 文件/节点关联 */
  async function rebuild({ threshold, nodeThreshold, rebuildRelations = true } = {}) {
    rebuilding.value = true
    try {
      const res = await kbAPI.rebuild({
        threshold: threshold ?? rebuildThreshold.value,
        nodeThreshold: nodeThreshold ?? rebuildThreshold.value,
        rebuildRelations
      })
      const r = res.result || {}
      ElMessage.success(
        `重建完成：锚定 ${r.anchored_nodes || 0} 个节点、` +
        `文件关联 ${r.file_links?.links || 0} 条、节点关联 ${r.node_links?.total || 0} 条`
      )
      await refreshAll()
      return r
    } catch (e) {
      ElMessage.error(`重建失败：${e.message}`)
      return null
    } finally {
      rebuilding.value = false
    }
  }

  async function refreshAll() {
    await Promise.all([
      loadStats(), loadEntries(), loadRelations(), loadGraph(),
      loadFiles(), loadImports()
    ])
  }

  return {
    // state
    stats, entries, entryTotal, entryFilter, relations, graph,
    report, imports, matchResult, fileProfiles, fileLinks, fileDetail,
    rebuildThreshold,
    // loading flags
    loadingStats, loadingEntries, graphLoading, previewing, importing,
    matching, loadingFiles, rebuilding,
    // getters
    domains, coveredFiles, uncoveredFiles, avgCoverage,
    // actions
    loadStats, loadEntries, createEntry, updateEntry, deleteEntry,
    loadRelations, loadGraph, uploadKb, previewText, loadImports, loadImportDetail,
    matchText, loadFiles, loadFileDetail, rebuild, refreshAll
  }
})
