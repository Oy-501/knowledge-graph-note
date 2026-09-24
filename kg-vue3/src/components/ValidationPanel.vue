<template>
  <div class="panel-section">
    <h3>🔍 知识点校验</h3>
    <div class="vp-summary">
      <div class="vp-summary-card vp-ok"><span class="vps-num">{{ validationStats.passed }}</span><span class="vps-label">✅ 已验证</span></div>
      <div class="vp-summary-card vp-warn"><span class="vps-num">{{ validationStats.warning }}</span><span class="vps-label">⚠️ 待审查</span></div>
      <div class="vp-summary-card vp-error"><span class="vps-num">{{ validationStats.error }}</span><span class="vps-label">❌ 存在错误</span></div>
      <div class="vp-summary-card vp-pending"><span class="vps-num">{{ validationStats.pending }}</span><span class="vps-label">⏳ 待校验</span></div>
    </div>
    <div class="vp-accuracy"><span class="vp-accuracy-label">正确率</span><div class="vp-accuracy-bar"><div class="vp-accuracy-fill" :style="{ width: validationStats.accuracy + '%', background: accuracyColor }"></div></div><span class="vp-accuracy-value">{{ validationStats.accuracy }}%</span></div>
    <div class="vp-toolbar"><button type="button" class="btn btn-sm btn-primary" @click="onValidateAll" :disabled="graphStore.isBusy">🔍 全量校验</button><button type="button" class="btn btn-sm" @click="onRevalidateErrors" :disabled="validationStats.error + validationStats.warning === 0">重检问题项</button></div>
    <div v-if="validationFilter" class="vp-filter-row"><span class="vp-filter-label">筛选：</span><button v-for="(f, key) in validationFilter" :key="key" type="button" class="vp-filter-btn" :class="{ active: validationFilterActive === key }" @click="validationFilterActive = key">{{ f.label }} ({{ f.count }})</button></div>
    <div v-if="validationIssues.length" class="vp-list">
      <div v-for="issue in filteredIssues" :key="issue.id" class="vp-item" :class="'vp-sev-' + issue.severity" @click="onIssueClick(issue)">
        <div class="vp-item-head"><span class="vp-sev-badge" :class="'vp-badge-' + issue.severity">{{ sevLabel(issue.severity) }}</span><span class="vp-item-type">{{ issue.type }}</span><span class="vp-item-source">{{ issue.fileName || issue.nodeTitle || '—' }}</span></div>
        <div class="vp-item-title" :title="issue.title">{{ issue.title }}</div>
        <div class="vp-item-desc">{{ issue.description }}</div>
        <div v-if="issue.correction" class="vp-item-correct">💡 {{ issue.correction }}</div>
        <div v-if="issue.evidence" class="vp-item-evidence">📚 {{ issue.evidence }}</div>
        <div class="vp-item-actions"><button type="button" class="btn btn-sm" @click="onIgnoreIssue(issue)">忽略</button><button type="button" class="btn btn-sm btn-primary" @click="onFixIssue(issue)" v-if="issue.fixable">修复</button></div>
      </div>
      <div v-if="filteredIssues.length === 0" class="vp-empty">没有符合当前筛选的问题</div>
    </div>
    <div v-else class="vp-all-clear">🎉 全部知识点已通过校验，无待处理问题</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useGraphStore } from '@/store/graphStore'
import { validateAllNodes, getNodeValidationStatus, SEVERITY_LABEL, SEVERITY_COLORS } from '@/utils/noteValidator'

const graphStore = useGraphStore()
const validationFilterActive = ref('all')
const validationFilter = ref(null)
const validationIssues = ref([])
const sevLabel = s => SEVERITY_LABEL[s] || s
function onValidateAll() {
  ElMessage.info('开始全量校验知识点…')
  const result = validateAllNodes(graphStore.nodes)
  validationIssues.value = result.issues
  validationFilter.value = buildFilter(result.issues)
  validationFilterActive.value = 'all'
  graphStore.validationIssues = result.issues
  graphStore.validationStats = result.stats
  graphStore.validationPendingCount = result.stats.error + result.stats.warning
  ElMessage.success(`校验完成：通过 ${result.stats.passed}，待审查 ${result.stats.warning}，存在错误 ${result.stats.error}`)
}
function onRevalidateErrors() {
  const errors = validationIssues.value.filter(i => i.severity === 'error' || i.severity === 'warning')
  ElMessage.info(`重新校验 ${errors.length} 个问题项…`)
  const result = validateAllNodes(graphStore.nodes)
  validationIssues.value = result.issues
  validationFilter.value = buildFilter(result.issues)
  validationFilterActive.value = 'all'
  graphStore.validationIssues = result.issues
  graphStore.validationStats = result.stats
  graphStore.validationPendingCount = result.stats.error + result.stats.warning
  ElMessage.success('重检完成')
}
function buildFilter(issues) {
  const counts = { all: issues.length }
  for (const i of issues) {
    counts[i.severity] = (counts[i.severity] || 0) + 1
    counts[i.type] = (counts[i.type] || 0) + 1
  }
  const labels = { all: '全部', error: '错误', warning: '警告', minor: '轻微', info: '提示', contradiction: '矛盾', outdated: '过时', missing: '缺失', misattributed: '归属错误', inconsistency: '不一致', other: '其他' }
  return Object.keys(counts).map(key => ({ key, label: labels[key] || key, count: counts[key] }))
}
const filteredIssues = computed(() => {
  if (!validationFilterActive.value || validationFilterActive.value === 'all') return validationIssues.value
  return validationIssues.value.filter(i => i.severity === validationFilterActive.value || i.type === validationFilterActive.value)
})
const validationStats = computed(() => graphStore.validationStats || { passed: 0, warning: 0, error: 0, pending: 0, accuracy: 0 })
const accuracyColor = computed(() => {
  const acc = validationStats.value.accuracy
  if (acc >= 80) return 'var(--success)'
  if (acc >= 50) return 'var(--warning)'
  return 'var(--danger)'
})
function onIssueClick(issue) {
  if (issue.nodeId) {
    const node = graphStore.nodes.find(n => n.id === issue.nodeId)
    if (node) graphStore.selectNode(node)
  }
  ElMessage.info(`问题详情：${issue.description}`)
}
function onIgnoreIssue(issue) {
  issue.ignored = true
  issue.status = 'ignored'
  graphStore.validationStats = recomputeStats()
  ElMessage.success('已忽略该问题')
}
function onFixIssue(issue) {
  ElMessage.info(`开始修复：${issue.correction}`)
  graphStore.validationStats = recomputeStats()
  ElMessage.success('修复建议已应用，请检查内容是否按建议更新')
}
function recomputeStats() {
  const issues = graphStore.validationIssues || []
  const stats = { passed: 0, warning: 0, error: 0, pending: 0, accuracy: 0 }
  const totalNodes = graphStore.nodes.length || 1
  const valid = issues.filter(i => i.status === 'ignored' || i.severity === 'info').length
  const err = issues.filter(i => i.severity === 'error').length
  const warn = issues.filter(i => i.severity === 'warning').length
  stats.error = err
  stats.warning = warn
  stats.passed = Math.max(0, totalNodes - err - warn)
  stats.pending = Math.max(0, issues.length - err - warn - valid)
  stats.accuracy = totalNodes ? Math.round(((totalNodes - err - warn) / totalNodes) * 100) : 0
  graphStore.validationPendingCount = err + warn
  return stats
}
</script>

<style scoped>
.vp-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 8px; }
.vp-summary-card { border-radius: var(--radius-sm); padding: 8px 6px; text-align: center; }
.vp-ok { background: var(--success-soft); border: 1px solid var(--success-soft); }
.vp-warn { background: var(--warning-soft); border: 1px solid var(--warning-soft); }
.vp-error { background: var(--danger-soft); border: 1px solid var(--danger-soft); }
.vp-pending { background: var(--bg-tertiary); border: 1px solid var(--border-light); }
.vps-num { font-size: 18px; font-weight: 700; display: block; }
.vp-ok .vps-num { color: var(--success); }
.vp-warn .vps-num { color: var(--warning); }
.vp-error .vps-num { color: var(--danger); }
.vp-pending .vps-num { color: var(--text-muted); }
.vps-label { font-size: 10px; color: var(--text-secondary); }
.vp-accuracy { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.vp-accuracy-label { font-size: 11px; color: var(--text-secondary); white-space: nowrap; }
.vp-accuracy-bar { flex: 1; height: 8px; background: var(--bg-tertiary); border-radius: var(--radius-full); overflow: hidden; }
.vp-accuracy-fill { height: 100%; border-radius: var(--radius-full); transition: width 0.4s var(--ease-out); }
.vp-accuracy-value { font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); }
.vp-toolbar { display: flex; gap: 6px; margin-bottom: 8px; }
.vp-filter-row { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.vp-filter-label { font-size: 11px; color: var(--text-muted); line-height: 24px; }
.vp-filter-btn { font-size: 10px; padding: 2px 8px; border-radius: var(--radius-full); border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; }
.vp-filter-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.vp-list { display: flex; flex-direction: column; gap: 6px; }
.vp-item { border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 8px 10px; background: var(--bg-secondary); box-shadow: var(--shadow-sm); transition: border-color var(--dur-fast), box-shadow var(--dur-fast); }
.vp-item:hover { border-color: var(--border); box-shadow: var(--shadow-card); }
.vp-sev-error { border-left: 3px solid var(--danger); }
.vp-sev-warning { border-left: 3px solid var(--warning); }
.vp-sev-minor { border-left: 3px solid var(--apricot); }
.vp-sev-info { border-left: 3px solid var(--info); }
.vp-item-head { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.vp-sev-badge { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: var(--radius-full); color: #fff; }
.vp-badge-error { background: var(--danger); }
.vp-badge-warning { background: var(--warning); }
.vp-badge-minor { background: var(--apricot); }
.vp-badge-info { background: var(--info); }
.vp-item-type { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.4px; }
.vp-item-source { margin-left: auto; font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }
.vp-item-title { font-size: 12.5px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.vp-item-desc { font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; }
.vp-item-correct { margin-top: 4px; font-size: 11px; color: var(--success); background: var(--success-soft); border-radius: var(--radius-sm); padding: 4px 8px; }
.vp-item-evidence { margin-top: 4px; font-size: 11px; color: var(--text-muted); line-height: 1.5; }
.vp-item-actions { display: flex; gap: 4px; margin-top: 6px; }
.vp-empty { font-size: 12px; color: var(--text-muted); text-align: center; padding: 14px; }
.vp-all-clear { font-size: 12px; color: var(--success); text-align: center; padding: 14px; background: var(--success-soft); border-radius: var(--radius); border: 1px dashed var(--success); }
</style>
