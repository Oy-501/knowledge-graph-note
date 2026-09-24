<template>
  <div class="panel-section validation-panel">
    <div class="vp-header" @click="collapsed = !collapsed">
      <h3>
        📋 知识点校验
        <span v-if="pendingCount > 0" class="count vp-badge-high">{{ pendingCount }}</span>
        <span v-else class="count vp-badge-ok">✓</span>
      </h3>
      <span class="vp-toggle">{{ collapsed ? '▶' : '▼' }}</span>
    </div>

    <div v-if="!collapsed" class="vp-body">
      <!-- 标签切换 -->
      <div class="vp-tabs">
        <button type="button"
          class="vp-tab"
          :class="{ active: activeTab === 'knowledge' }"
          @click="activeTab = 'knowledge'"
        >知识点校验</button>
        <button type="button"
          class="vp-tab"
          :class="{ active: activeTab === 'note' }"
          @click="activeTab = 'note'"
        >
          笔记校验
          <span v-if="noteValidationStats.totalIssues > 0" class="vp-tab-badge">{{ noteValidationStats.totalIssues }}</span>
        </button>
      </div>

      <!-- ===== 知识点校验 Tab ===== -->
      <template v-if="activeTab === 'knowledge'">
      <!-- 无待处理问题 -->
      <div v-if="pendingCount === 0" class="vp-empty">
        <span class="vp-empty-icon">✅</span>
        <span>所有知识点已通过校验</span>
      </div>

      <!-- 按严重程度分组 -->
      <template v-else>
        <!-- 高优先级 -->
        <div v-if="highIssues.length" class="vp-group">
          <div class="vp-group-title">🔴 高优先级 <span class="vp-group-count">({{ highIssues.length }})</span></div>
          <div
            v-for="item in highIssues"
            :key="item.nodeId + '_' + item.type"
            class="vp-issue vp-sev-high"
          >
            <div class="vp-issue-header">
              <span class="vp-issue-type" :class="'vp-type-' + item.severity">
                {{ item.label || item.type }}
              </span>
              <span class="vp-issue-node" :title="item.nodeTitle">{{ item.nodeTitle }}</span>
            </div>
            <div class="vp-issue-reason">{{ item.reason }}</div>
            <div class="vp-issue-suggestion">{{ item.suggestion }}</div>
            <div class="vp-issue-actions">
              <button type="button" class="btn btn-sm btn-primary" @click="onAccept(item)">接受</button>
              <button type="button" class="btn btn-sm" @click="onEdit(item)">编辑</button>
              <button type="button" class="btn btn-sm" @click="onDiscard(item)">丢弃</button>
              <button type="button" class="btn btn-sm" @click="onSkip(item)">跳过</button>
            </div>
          </div>
        </div>

        <!-- 中优先级 -->
        <div v-if="mediumIssues.length" class="vp-group">
          <div class="vp-group-title">🟡 中优先级 <span class="vp-group-count">({{ mediumIssues.length }})</span></div>
          <div
            v-for="item in mediumIssues"
            :key="item.nodeId + '_' + item.type"
            class="vp-issue vp-sev-medium"
          >
            <div class="vp-issue-header">
              <span class="vp-issue-type" :class="'vp-type-' + item.severity">
                {{ item.label || item.type }}
              </span>
              <span class="vp-issue-node" :title="item.nodeTitle">{{ item.nodeTitle }}</span>
            </div>
            <div class="vp-issue-reason">{{ item.reason }}</div>
            <div class="vp-issue-suggestion">{{ item.suggestion }}</div>
            <div class="vp-issue-actions">
              <button type="button" class="btn btn-sm btn-primary" @click="onAccept(item)">接受</button>
              <button type="button" class="btn btn-sm" @click="onEdit(item)">编辑</button>
              <button type="button" class="btn btn-sm" @click="onSkip(item)">跳过</button>
            </div>
          </div>
        </div>

        <!-- 低优先级 -->
        <div v-if="lowIssues.length" class="vp-group">
          <div class="vp-group-title">🟢 低优先级 <span class="vp-group-count">({{ lowIssues.length }})</span></div>
          <div
            v-for="item in lowIssues"
            :key="item.nodeId + '_' + item.type"
            class="vp-issue vp-sev-low"
          >
            <div class="vp-issue-header">
              <span class="vp-issue-type" :class="'vp-type-' + item.severity">
                {{ item.label || item.type }}
              </span>
              <span class="vp-issue-node" :title="item.nodeTitle">{{ item.nodeTitle }}</span>
            </div>
            <div class="vp-issue-reason">{{ item.reason }}</div>
            <div class="vp-issue-suggestion">{{ item.suggestion }}</div>
            <div class="vp-issue-actions">
              <button type="button" class="btn btn-sm btn-primary" @click="onAccept(item)">接受</button>
              <button type="button" class="btn btn-sm" @click="onEdit(item)">编辑</button>
              <button type="button" class="btn btn-sm" @click="onSkip(item)">跳过</button>
            </div>
          </div>
        </div>

        <!-- 底部批量操作 -->
        <div class="vp-batch">
          <label class="vp-auto-switch">
            <input type="checkbox" :checked="graphStore.autoAcceptLow" @change="onAutoToggle" />
            <span>自动确认低风险修正（别名归一化）</span>
          </label>
          <div class="btn-group" style="margin-top:6px">
            <button type="button" class="btn btn-sm btn-primary" @click="onAcceptAll">一键全部接受</button>
            <button type="button" class="btn btn-sm" @click="onIgnoreAll">全部跳过</button>
          </div>
        </div>
      </template>

      <!-- 已丢弃节点列表 -->
      <div v-if="discardedNodes.length" class="vp-group vp-discarded">
        <div class="vp-group-title" @click="showDiscarded = !showDiscarded">
          🗑 已丢弃节点 ({{ discardedNodes.length }})
          <span style="margin-left:auto;font-size:10px">{{ showDiscarded ? '收起' : '展开' }}</span>
        </div>
        <div v-if="showDiscarded">
          <div v-for="dn in discardedNodes" :key="dn.id" class="vp-issue vp-discarded-item">
            <span>{{ dn.title }}</span>
            <button type="button" class="btn btn-sm" @click="onRestore(dn)">恢复</button>
          </div>
        </div>
      </div>
      </template>

      <!-- ===== 笔记校验 Tab ===== -->
      <template v-if="activeTab === 'note'">
        <div v-if="noteValidationStats.totalIssues === 0" class="vp-empty vp-empty-pass">
          <span class="vp-empty-icon">✅</span>
          <span>所有笔记已通过校验</span>
        </div>

        <template v-else>
          <!-- 笔记校验统计 -->
          <div class="note-val-stats">
            <div class="nvs-row">
              <span>📄 笔记总数</span>
              <span class="nvs-val">{{ noteValidationStats.totalFiles }}</span>
            </div>
            <div class="nvs-row">
              <span>✅ 通过</span>
              <span class="nvs-val nvs-pass">{{ noteValidationStats.passedFiles }}</span>
            </div>
            <div class="nvs-row">
              <span>⚠️ 存在问题</span>
              <span class="nvs-val nvs-warn">{{ noteValidationStats.filesWithIssues }}</span>
            </div>
            <div class="nvs-row">
              <span>🔴 错误</span>
              <span class="nvs-val nvs-error">{{ noteValidationStats.totalErrors }}</span>
            </div>
            <div class="nvs-row">
              <span>🟡 警告</span>
              <span class="nvs-val nvs-warn">{{ noteValidationStats.totalWarnings }}</span>
            </div>
          </div>

          <!-- 按文件分组的问题列表 -->
          <div v-for="fileInfo in noteFilesWithIssues" :key="fileInfo.fileId" class="note-file-group">
            <div class="nfg-header" @click="fileInfo.expanded = !fileInfo.expanded">
              <span class="nfg-name">📄 {{ fileInfo.fileName }}</span>
              <span class="nfg-stats">
                <span class="nfg-err" v-if="fileInfo.errors > 0">🔴 {{ fileInfo.errors }}</span>
                <span class="nfg-warn" v-if="fileInfo.warnings > 0">🟡 {{ fileInfo.warnings }}</span>
                <span class="nfg-acc" :style="{ color: fileInfo.accuracy >= 80 ? '#4caf50' : fileInfo.accuracy >= 50 ? '#e8a020' : '#e84c4c' }">
                  {{ fileInfo.accuracy }}%
                </span>
                <span class="vp-toggle-sm">{{ fileInfo.expanded ? '▼' : '▶' }}</span>
              </span>
            </div>

            <div v-if="fileInfo.expanded">
              <div v-for="err in fileInfo.issues" :key="err.id" class="vp-issue" :class="err.severity === 'error' ? 'vp-sev-error' : 'vp-sev-warn'">
                <div class="vp-issue-header">
                  <span class="vp-issue-type" :class="err.severity === 'error' ? 'vp-type-error' : 'vp-type-warn'">
                    {{ err.type }}
                  </span>
                  <span class="vp-issue-node" :title="err.text">{{ err.text?.slice(0, 50) }}{{ err.text?.length > 50 ? '...' : '' }}</span>
                </div>
                <div class="vp-issue-reason">{{ err.description }}</div>
                <div class="vp-issue-suggestion" v-if="err.correction">💡 {{ err.correction }}</div>
                <div class="vp-issue-source" v-if="err.evidence">依据：{{ err.evidence }}</div>
                <div class="vp-issue-actions">
                  <button type="button" class="btn btn-sm btn-primary" @click="onAcceptNoteIssue(fileInfo.fileId, err)">接受修正</button>
                  <button type="button" class="btn btn-sm" @click="onIgnoreNoteIssue(fileInfo.fileId, err)">忽略</button>
                </div>
              </div>
            </div>
          </div>

          <!-- 批量操作 -->
          <div class="vp-batch">
            <button type="button" class="btn btn-sm btn-primary" @click="onAcceptAllNotes">一键全部接受</button>
            <button type="button" class="btn btn-sm" @click="onIgnoreAllNotes">全部忽略</button>
          </div>
        </template>
      </template>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="editDialog.visible" class="vp-edit-overlay" @click.self="closeEdit">
      <div class="vp-edit-dialog">
        <h4>手动编辑节点</h4>
        <p class="vp-edit-hint">当前节点: {{ editDialog.nodeTitle }}</p>
        <p class="vp-edit-hint" v-if="editDialog.suggestion">建议: {{ editDialog.suggestion }}</p>
        <input
          v-model="editDialog.value"
          class="vp-edit-input"
          placeholder="输入新的节点名称"
          @keyup.enter="confirmEdit"
        />
        <div class="vp-edit-actions">
          <button type="button" class="btn btn-sm btn-primary" @click="confirmEdit">确认</button>
          <button type="button" class="btn btn-sm" @click="closeEdit">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useGraphStore } from '@/store/graphStore'
import { useFileStore } from '@/store/fileStore'
import { getPendingIssues, ISSUE_TYPES } from '@/utils/knowledgeValidator'
import { getNodeValidationStatus } from '@/utils/noteValidator'

const graphStore = useGraphStore()
const fileStore = useFileStore()

const collapsed = ref(false)
const showDiscarded = ref(false)
const activeTab = ref('knowledge')

const editDialog = ref({
  visible: false,
  nodeId: '',
  nodeTitle: '',
  suggestion: '',
  value: '',
  issue: null
})

const pendingIssues = computed(() => getPendingIssues(graphStore.nodes))

const pendingCount = computed(() => {
  return pendingIssues.value.length
})

const highIssues = computed(() => pendingIssues.value.filter(i => i.severity === 'high'))
const mediumIssues = computed(() => pendingIssues.value.filter(i => i.severity === 'medium'))
const lowIssues = computed(() => pendingIssues.value.filter(i => i.severity === 'low'))

const discardedNodes = computed(() => graphStore.discardedNodes)

// === 笔记校验（noteValidator 集成）===

// 按文件聚合校验统计
const noteValidationStats = computed(() => {
  const nodes = graphStore.nodes || []
  const files = fileStore.uploadedFiles || []
  const fileMap = new Map()

  for (const n of nodes) {
    if (!n.fileId) continue
    if (!fileMap.has(n.fileId)) {
      const f = files.find(ff => ff.id === n.fileId)
      fileMap.set(n.fileId, { fileId: n.fileId, fileName: f?.name || n.fileId, nodes: [], errors: 0, warnings: 0, issues: [] })
    }
    const fi = fileMap.get(n.fileId)
    fi.nodes.push(n)

    const vs = getNodeValidationStatus(n)
    if (vs.status === 'error') fi.errors++
    if (vs.status === 'warning') fi.warnings++

    // 收集该节点的校验问题
    if (n.validationReport) {
      const report = n.validationReport
      if (report.errors) {
        for (const e of report.errors) {
          fi.issues.push({
            id: n.id + '_err_' + fi.issues.length,
            type: e.type || 'error',
            severity: 'error',
            text: e.text || e.assertion || n.title,
            description: e.description || '',
            correction: e.correction || '',
            evidence: e.evidence || '',
            nodeId: n.id
          })
        }
      }
      if (report.warnings) {
        for (const w of report.warnings) {
          fi.issues.push({
            id: n.id + '_warn_' + fi.issues.length,
            type: w.type || 'warning',
            severity: 'warning',
            text: w.text || w.assertion || n.title,
            description: w.description || '',
            correction: w.correction || '',
            evidence: w.evidence || '',
            nodeId: n.id
          })
        }
      }
    }
  }

  let totalErrors = 0, totalWarnings = 0, passedFiles = 0, filesWithIssues = 0
  for (const fi of fileMap.values()) {
    totalErrors += fi.errors
    totalWarnings += fi.warnings
    if (fi.errors === 0 && fi.warnings === 0) passedFiles++
    if (fi.issues.length > 0) filesWithIssues++
  }

  return {
    totalFiles: fileMap.size,
    passedFiles,
    filesWithIssues,
    totalErrors,
    totalWarnings,
    totalIssues: totalErrors + totalWarnings
  }
})

// 有问题文件的展开列表（带准确率）
const noteFilesWithIssues = computed(() => {
  const nodes = graphStore.nodes || []
  const files = fileStore.uploadedFiles || []
  const fileMap = new Map()

  for (const n of nodes) {
    if (!n.fileId) continue
    if (!fileMap.has(n.fileId)) {
      const f = files.find(ff => ff.id === n.fileId)
      fileMap.set(n.fileId, { fileId: n.fileId, fileName: f?.name || n.fileId, nodes: [], errors: 0, warnings: 0, issues: [], expanded: true, accuracy: 0 })
    }
    const fi = fileMap.get(n.fileId)
    fi.nodes.push(n)

    const vs = getNodeValidationStatus(n)
    if (vs.status === 'error') fi.errors++
    if (vs.status === 'warning') fi.warnings++

    if (n.validationReport) {
      const report = n.validationReport
      if (report.errors) {
        for (const e of report.errors) {
          fi.issues.push({
            id: n.id + '_err_' + fi.issues.length,
            type: e.type || 'error',
            severity: 'error',
            text: e.text || e.assertion || n.title,
            description: e.description || '',
            correction: e.correction || '',
            evidence: e.evidence || '',
            nodeId: n.id
          })
        }
      }
      if (report.warnings) {
        for (const w of report.warnings) {
          fi.issues.push({
            id: n.id + '_warn_' + fi.issues.length,
            type: w.type || 'warning',
            severity: 'warning',
            text: w.text || w.assertion || n.title,
            description: w.description || '',
            correction: w.correction || '',
            evidence: w.evidence || '',
            nodeId: n.id
          })
        }
      }
    }
    // 计算准确率
    const totalAssertions = fi.nodes.reduce((sum, nd) => sum + (nd.validationReport?.totalAssertions || 1), 0)
    const passedAssertions = fi.nodes.reduce((sum, nd) => sum + (nd.validationReport?.passedAssertions || 0), 0)
    fi.accuracy = totalAssertions > 0 ? Math.round((passedAssertions / totalAssertions) * 100) : 100
  }

  // 只返回有问题（有 issues）的文件
  return Array.from(fileMap.values())
    .filter(fi => fi.issues.length > 0)
    .sort((a, b) => b.issues.length - a.issues.length)
})

// 接受单个笔记问题
function onAcceptNoteIssue(fileId, err) {
  if (err.nodeId) {
    const node = graphStore.nodes.find(n => n.id === err.nodeId)
    if (node && err.correction) {
      // 应用修正：更新节点标题/描述
      if (err.type === 'factual_error' || err.type === 'outdated' || err.type === 'imprecision') {
        node.title = err.correction
        node.verified = true
        if (!node.validationReport) node.validationReport = { totalAssertions: 1, passedAssertions: 1, errors: [], warnings: [], checkedAt: Date.now() }
        node.validationReport.errors = (node.validationReport.errors || []).filter(e => e.text !== err.text)
        node.validationReport.passedAssertions = (node.validationReport.passedAssertions || 0) + 1
        node.accuracyScore = 100
        graphStore.version++
        ElMessage.success('已应用修正')
      } else {
        // 对于其他类型，标记为已验证
        node.verified = true
        if (node.validationReport) {
          node.validationReport.warnings = (node.validationReport.warnings || []).filter(w => w.text !== err.text)
          node.validationReport.passedAssertions = (node.validationReport.passedAssertions || 0) + 1
        }
        graphStore.version++
        ElMessage.success('已接受修正')
      }
    }
  }
}

// 忽略单个笔记问题
function onIgnoreNoteIssue(fileId, err) {
  if (err.nodeId) {
    const node = graphStore.nodes.find(n => n.id === err.nodeId)
    if (node && node.validationReport) {
      node.validationReport.errors = (node.validationReport.errors || []).filter(e => e.text !== err.text)
      node.validationReport.warnings = (node.validationReport.warnings || []).filter(w => w.text !== err.text)
      graphStore.version++
      ElMessage.info('已忽略')
    }
  }
}

// 一键全部接受笔记修正
function onAcceptAllNotes() {
  let count = 0
  for (const fi of noteFilesWithIssues.value) {
    for (const err of fi.issues) {
      onAcceptNoteIssue(fi.fileId, err)
      count++
    }
  }
  ElMessage.success(`已应用 ${count} 项修正`)
}

// 全部忽略笔记问题
function onIgnoreAllNotes() {
  let count = 0
  for (const fi of noteFilesWithIssues.value) {
    for (const err of fi.issues) {
      onIgnoreNoteIssue(fi.fileId, err)
      count++
    }
  }
  ElMessage.success(`已忽略 ${count} 项`)
}

function severityColor(s) {
  if (s === 'high') return '#f87086'
  if (s === 'medium') return '#f5b462'
  return '#6dd48a'
}

// 展开校验面板当有问题时
watch(pendingCount, (val) => {
  if (val > 0 && collapsed.value) {
    collapsed.value = false
  }
})

async function onAccept(item) {
  // 合并操作需要用户确认
  if (item.type === 'duplicate_synonym' && item.aiFix === 'merge') {
    try {
      await ElMessageBox.confirm(
        `确认将「${item.nodeTitle}」合并到目标节点？合并后连线将自动转移，此操作不可逆。`,
        '合并确认',
        { type: 'warning', confirmButtonText: '确认合并', cancelButtonText: '取消' }
      )
    } catch { return }
  }
  const res = graphStore.handleAcceptFix(item.nodeId, item)
  if (res.ok) {
    ElMessage.success(res.action === 'merged' ? '节点已合并' : (res.action === 'discarded' ? '节点已丢弃' : '修正已应用'))
  }
}

function onEdit(item) {
  editDialog.value = {
    visible: true,
    nodeId: item.nodeId,
    nodeTitle: item.nodeTitle,
    suggestion: item.aiFix || item.suggestion || '',
    value: item.aiFix || item.nodeTitle,
    issue: item
  }
}

function confirmEdit() {
  if (editDialog.value.value.trim()) {
    graphStore.handleManualEdit(editDialog.value.nodeId, editDialog.value.value.trim())
    ElMessage.success('节点名称已更新')
  }
  closeEdit()
}

function closeEdit() {
  editDialog.value.visible = false
}

function onDiscard(item) {
  graphStore.handleDiscardNode(item.nodeId)
  ElMessage.success('节点已丢弃，连线已清除')
}

function onSkip(item) {
  graphStore.handleSkipIssue(item.nodeId, item)
}

async function onAcceptAll() {
  try {
    await ElMessageBox.confirm(
      '将接受所有高/中优先级修正建议，低优先级根据自动开关决定。确认执行？',
      '批量确认',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
  } catch { return }
  const res = graphStore.handleAcceptAll()
  ElMessage.success(`已处理 ${res.accepted} 项修正`)
}

function onIgnoreAll() {
  graphStore.handleIgnoreAll()
  ElMessage.success('已全部跳过')
}

function onAutoToggle(e) {
  graphStore.toggleAutoAcceptLow(e.target.checked)
}

function onRestore(node) {
  graphStore.handleRestoreNode(node.id)
  ElMessage.success('节点已恢复')
}
</script>

<style scoped>
.vp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}
.vp-header h3 {
  margin-bottom: 0 !important;
}
.vp-toggle {
  color: var(--text-muted);
  font-size: 10px;
}
.vp-badge-high {
  background: var(--danger-soft) !important;
  color: var(--danger) !important;
  font-family: var(--font-mono);
}
.vp-badge-ok {
  background: var(--success-soft) !important;
  color: var(--success) !important;
  font-family: var(--font-mono);
}
.vp-body {
  margin-top: 10px;
}
.vp-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 14px 12px;
  color: var(--text-muted);
  font-size: 12px;
}
.vp-empty-pass {
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid color-mix(in srgb, var(--success) 25%, transparent);
  border-radius: var(--radius-full);
  font-weight: 500;
}
.vp-empty-icon {
  font-size: 14px;
}
.vp-group {
  margin-bottom: 10px;
}
.vp-group-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  cursor: default;
}
.vp-group-count {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
}
.vp-issue {
  position: relative;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 8px 10px 8px 24px;
  margin-bottom: 6px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.vp-issue:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.vp-issue::before {
  content: '';
  position: absolute;
  left: 10px;
  top: 14px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.vp-sev-high::before, .vp-sev-error::before {
  background: var(--danger);
  box-shadow: 0 0 0 3px var(--danger-soft);
}
.vp-sev-medium::before, .vp-sev-warn::before {
  background: var(--warning);
  box-shadow: 0 0 0 3px var(--warning-soft);
}
.vp-sev-low::before {
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
}
.vp-issue-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.vp-issue-type {
  font-size: 9px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  white-space: nowrap;
  font-weight: 500;
}
.vp-type-high, .vp-type-error {
  background: var(--danger-soft);
  color: var(--danger);
}
.vp-type-medium, .vp-type-warn {
  background: var(--warning-soft);
  color: var(--warning);
}
.vp-type-low {
  background: var(--success-soft);
  color: var(--success);
}
.vp-issue-node {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vp-issue-reason {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 3px;
  line-height: 1.4;
}
.vp-issue-suggestion {
  font-size: 11px;
  color: var(--accent-light);
  margin-bottom: 6px;
}
.vp-issue-actions {
  display: flex;
  gap: 4px;
}
.vp-issue-actions .btn {
  font-size: 10px;
  padding: 2px 8px;
}
.vp-batch {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
}
.vp-auto-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
}
.vp-auto-switch input {
  accent-color: var(--accent);
}
.vp-discarded {
  margin-top: 8px;
}
.vp-discarded-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
}
.vp-discarded-item .btn {
  font-size: 10px;
  padding: 2px 8px;
}

/* 编辑弹窗 */
.vp-edit-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
}
.vp-edit-dialog {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 20px;
  min-width: 320px;
  max-width: 420px;
  box-shadow: var(--shadow-lg);
}
.vp-edit-dialog h4 {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.vp-edit-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.vp-edit-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 13px;
  margin: 8px 0;
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.vp-edit-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.vp-edit-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 8px;
}

/* 笔记校验 Tab */
.vp-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  padding: 4px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
.vp-tab {
  flex: 1;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.vp-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.vp-tab.active {
  background: var(--accent);
  color: #fff;
}
.vp-tab-badge {
  background: rgba(248, 112, 134, 0.9);
  color: #fff;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
}
.vp-toggle-sm {
  font-size: 9px;
  color: var(--text-muted);
  margin-left: 4px;
}

/* 笔记校验统计 */
.note-val-stats {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 10px 12px;
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  box-shadow: var(--shadow-sm);
}
.nvs-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}
.nvs-val {
  font-weight: 600;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
}
.nvs-pass { color: var(--success); }
.nvs-warn { color: var(--warning); }
.nvs-error { color: var(--danger); }

/* 按文件分组 */
.note-file-group {
  margin-bottom: 8px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-secondary);
  box-shadow: var(--shadow-sm);
}
.nfg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.nfg-header:hover {
  background: var(--bg-hover);
}
.nfg-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 6px;
}
.nfg-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  flex-shrink: 0;
}
.nfg-err, .nfg-warn {
  font-family: var(--font-mono);
  font-weight: 500;
}
.nfg-err { color: var(--danger); }
.nfg-warn { color: var(--warning); }
.nfg-acc {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 11px;
}

/* 笔记问题源 */
.vp-issue-source {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
  font-style: italic;
}
</style>