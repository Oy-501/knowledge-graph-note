<template>
  <Transition name="drawer-slide">
    <div v-if="visible" class="node-drawer-overlay" @click.self="$emit('close')">
      <div class="node-drawer">
        <div class="drawer-header">
          <h3>{{ node?.title || '节点详情' }}</h3>
          <button type="button" class="drawer-close" @click="$emit('close')">✕</button>
        </div>

        <div class="drawer-body" v-if="node">
          <!-- 基本信息 -->
          <div class="drawer-section">
            <h4>基本信息</h4>
            <div class="info-row">
              <span class="info-label">节点 ID</span>
              <span class="info-value mono">{{ node.id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">描述</span>
              <span class="info-value">{{ node.description || '无' }}</span>
            </div>
            <div class="info-row" v-if="node.keywords?.length">
              <span class="info-label">关键词</span>
              <span class="info-value">
                <span class="tag" v-for="k in node.keywords.slice(0, 10)" :key="k">#{{ k }}</span>
              </span>
            </div>
            <div class="info-row" v-if="node.entities?.length">
              <span class="info-label">实体</span>
              <span class="info-value">
                <span class="tag entity" v-for="e in node.entities.slice(0, 8)" :key="e">{{ e }}</span>
              </span>
            </div>
          </div>

          <!-- 知识层级 -->
          <div class="drawer-section">
            <h4>知识层级</h4>
            <div class="info-row">
              <span class="info-label">层级</span>
              <span class="info-value">
                <span class="tag" :style="levelBadgeStyle">{{ levelLabel }}</span>
              </span>
            </div>
            <div class="info-row" v-if="levelInfo">
              <span class="info-label">说明</span>
              <span class="info-value" style="font-size: var(--fs-xs);color:var(--text-secondary)">{{ levelInfo.desc }}</span>
            </div>
          </div>

          <!-- 所属分组 -->
          <div class="drawer-section">
            <h4>所属分组</h4>
            <div class="info-row">
              <span class="info-label">当前分组</span>
              <span class="info-value">
                <select class="info-select" @change="onGroupChange($event.target.value)">
                  <option v-for="g in groupStore.groups" :key="g.id" :value="g.id" :selected="node.groupId === g.id">
                    {{ g.name }}
                  </option>
                </select>
              </span>
            </div>
          </div>

          <!-- 隔离黑名单 -->
          <div class="drawer-section">
            <h4>隔离黑名单</h4>
            <div v-if="node.isolateBlackList?.length" class="isolate-blacklist">
              <div v-for="bid in node.isolateBlackList" :key="bid" class="ib-item">
                <span class="ib-name">{{ getNodeName(bid) }}</span>
                <button type="button" class="btn btn-sm" @click="onRemoveIsolate(bid)">解除</button>
              </div>
            </div>
            <div v-else style="font-size: var(--fs-xs);color:var(--text-muted)">暂无隔离</div>
          </div>

          <!-- 校验状态 -->
          <div class="drawer-section" v-if="node.validate">
            <h4>校验状态</h4>
            <div class="info-row">
              <span class="info-label">状态</span>
              <span class="info-value">
                <span class="tag" :style="validateStatusStyle">{{ validateStatusLabel }}</span>
              </span>
            </div>
            <div v-if="node.validate.issues?.length" class="validation-issues">
              <div
                v-for="(issue, idx) in node.validate.issues"
                :key="idx"
                class="validation-issue-item"
                :style="{ borderLeftColor: severityColor(issue.severity) }"
              >
                <span class="vi-type" :style="{ background: severityColor(issue.severity) }">
                  {{ issue.label || issue.type }}
                </span>
                <div class="vi-reason">{{ issue.reason }}</div>
                <div class="vi-suggestion" v-if="issue.suggestion">{{ issue.suggestion }}</div>
              </div>
            </div>
            <div v-if="node.validate.aiFix" class="info-row">
              <span class="info-label">AI修正</span>
              <span class="info-value mono">{{ node.validate.aiFix }}</span>
            </div>
            <div v-if="node.validate.manualEdit" class="info-row">
              <span class="info-label">手动编辑</span>
              <span class="info-value mono">{{ node.validate.manualEdit }}</span>
            </div>
            <div v-if="node.validate.confirmedAt" class="info-row">
              <span class="info-label">确认时间</span>
              <span class="info-value mono">{{ new Date(node.validate.confirmedAt).toLocaleString() }}</span>
            </div>
          </div>

          <!-- 关联关系列表 -->
          <div class="drawer-section">
            <h4>关联关系（{{ links.length }} 条）</h4>
            <div v-if="links.length === 0" class="empty-hint">该节点暂无关联连线</div>
            <div v-else class="relation-list">
              <div
                v-for="link in links"
                :key="link.id"
                class="relation-item"
                :style="{ borderLeftColor: link.relation_color || '#8a93b0' }"
              >
                <div class="rel-header">
                  <span class="rel-type-badge" :style="{ background: link.relation_color || '#8a93b0' }">
                    {{ link.relation_icon || '~' }} {{ link.relation_label || '关联' }}
                  </span>
                  <span class="rel-score">{{ (link.score * 100).toFixed(1) }}%</span>
                </div>
                <div class="rel-target">
                  <span class="rel-arrow">→</span>
                  <span class="rel-target-name">{{ getTargetName(link, node.id) }}</span>
                </div>
                <div class="rel-evidence" v-if="link.relation_evidence">
                  {{ link.relation_evidence }}
                </div>
                <div class="rel-meta" v-if="link.relation_method">
                  判定方法：{{ link.relation_method }}
                </div>
              </div>
            </div>
          </div>

          <!-- 学习路径 -->
          <div class="drawer-section">
            <h4>学习路径（前置知识链）</h4>
            <div v-if="learningPath.prerequisites.length === 0" class="empty-hint">
              未发现前置知识点，可直接开始学习
            </div>
            <div v-else>
              <div v-for="g in learningGroups" :key="g.level" class="lp-group">
                <div class="lp-level">{{ g.level ? 'L' + g.level : '' }} {{ g.label }}</div>
                <div class="lp-item" v-for="item in g.items" :key="item.id">
                  <span class="lp-arrow">→</span>
                  <span class="lp-name">{{ item.title }}</span>
                </div>
              </div>
              <button type="button" class="btn btn-primary lp-export" @click="onExportLearningPath">导出学习路径 (Markdown)</button>
            </div>
          </div>

          <!-- 知识时间线 -->
          <div class="drawer-section">
            <h4>知识时间线（演变追踪）</h4>
            <KnowledgeTimeline :node="node" />
          </div>

          <!-- 原始文本溯源 -->
          <div class="drawer-section" v-if="node.rawText">
            <h4>原始上下文</h4>
            <div class="raw-text">{{ node.rawText }}</div>
          </div>

          <!-- 笔记校验状态 -->
          <div class="drawer-section" v-if="node.validationReport || node.accuracyScore !== undefined">
            <h4>🔍 知识校验</h4>
            <div class="info-row">
              <span class="info-label">校验状态</span>
              <span class="info-value" :style="{ color: validationStatus.color, fontWeight: 600 }">
                {{ validationStatus.label }}
              </span>
            </div>
            <div class="info-row" v-if="node.accuracyScore !== undefined">
              <span class="info-label">正确率</span>
              <span
                class="info-value"
                :style="{
                  color: node.accuracyScore >= 80
                    // 状态色统一走调色板，不再写死旧品牌的绿/橙/红
                    ? SEMANTIC.success
                    : node.accuracyScore >= 50 ? SEMANTIC.warning : SEMANTIC.danger
                }"
              >
                {{ node.accuracyScore }}%
              </span>
            </div>
            <div class="info-row">
              <span class="info-label">可信度</span>
              <span class="info-value">
                <span class="credibility-stars">{{ credibility.stars }}</span>
                <span class="credibility-tag">{{ credibility.tag }}</span>
              </span>
            </div>
            <div v-if="node.validationReport?.errors?.length" class="val-errors">
              <div class="val-error-header">🔴 校验错误（{{ node.validationReport.errors.length }}）</div>
              <div v-for="(err, idx) in node.validationReport.errors" :key="idx" class="val-error-item">
                <div class="val-error-text">{{ err.text || err.assertion }}</div>
                <div class="val-error-desc">{{ err.description }}</div>
                <div class="val-error-fix" v-if="err.correction">💡 {{ err.correction }}</div>
                <div class="val-error-source" v-if="err.evidence">依据：{{ err.evidence }}</div>
              </div>
            </div>
            <div v-if="node.validationReport?.warnings?.length" class="val-warnings">
              <div class="val-warn-header">🟡 校验警告（{{ node.validationReport.warnings.length }}）</div>
              <div v-for="(warn, idx) in node.validationReport.warnings" :key="idx" class="val-warn-item">
                <span>{{ warn.description }}</span>
                <span class="val-warn-fix" v-if="warn.correction">→ {{ warn.correction }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { LEVEL_COLORS, SEMANTIC } from '@/utils/palette'
import { ElMessage } from 'element-plus'
import { useGraphStore } from '@/store/graphStore'
import { useGroupStore } from '@/store/groupStore'
import { getRelationLabel } from '@/utils/relationClassifier'
import { getLevelInfo } from '@/utils/mdParser'
import { getNodeValidationStatus, getCredibility } from '@/utils/noteValidator'
import { buildLearningPath, groupByLevel, toLearningPathMarkdown, downloadText } from '@/utils/learningPath'
import { endpointId } from '@/utils/graph'
import KnowledgeTimeline from './KnowledgeTimeline.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  node: { type: Object, default: null },
  links: { type: Array, default: () => [] },
  allNodes: { type: Array, default: () => [] }
})

defineEmits(['close'])

const graphStore = useGraphStore()
const groupStore = useGroupStore()

const levelInfo = computed(() => {
  const lv = props.node?.level
  if (!lv) return null
  return getLevelInfo(lv)
})

const levelLabel = computed(() => {
  return props.node?.levelLabel || (levelInfo.value ? `L${props.node.level}: ${levelInfo.value.label}` : '未知')
})

const levelBadgeStyle = computed(() => {
  const lv = props.node?.level || 3
  // 对齐图谱节点体系：L1 青 / L2 紫 / L3 琥珀 / L4 品红
  // 色值来自 utils/palette.js —— 与图谱节点渐变同源，避免两处各调各的
  const c = LEVEL_COLORS[lv] || LEVEL_COLORS[3]
  return {
    background: c,
    // 这四个颜色都是中高明度的霓虹色，白字压上去对比度不足，用深色字
    color: '#0B0E16',
    border: '1px solid ' + c
  }
})

// 笔记校验状态（来自 noteValidator）
const validationStatus = computed(() => {
  return getNodeValidationStatus(props.node)
})

const credibility = computed(() => {
  return getCredibility(props.node)
})

const validateStatusLabel = computed(() => {
  const s = props.node?.validate?.status
  if (s === 'pending') return '待处理'
  if (s === 'confirmed') return '已确认'
  if (s === 'discarded') return '已丢弃'
  if (s === 'auto_fixed') return '已自动修正'
  return '未校验'
})

const validateStatusStyle = computed(() => {
  const s = props.node?.validate?.status
  if (s === 'pending') {
    return {
      background: 'rgba(248,112,134,0.15)',
      color: '#f87086',
      border: '1px solid rgba(248,112,134,0.4)'
    }
  }
  if (s === 'confirmed') {
    return {
      background: 'rgba(109,212,138,0.15)',
      color: '#6dd48a',
      border: '1px solid rgba(109,212,138,0.4)'
    }
  }
  if (s === 'discarded') {
    return {
      background: 'rgba(138,147,176,0.15)',
      color: '#8a93b0',
      border: '1px solid rgba(138,147,176,0.4)'
    }
  }
  if (s === 'auto_fixed') {
    return {
      background: 'rgba(126,176,255,0.15)',
      color: '#7eb0ff',
      border: '1px solid rgba(126,176,255,0.4)'
    }
  }
  return { background: 'rgba(138,147,176,0.1)', color: '#8a93b0', border: '1px solid rgba(138,147,176,0.3)' }
})

function severityColor(s) {
  if (s === 'high') return '#f87086'
  if (s === 'medium') return '#f5b462'
  return '#6dd48a'
}

function getTargetName(link, currentNodeId) {
  const s = endpointId(link.source)
  const t = endpointId(link.target)
  const targetId = s === currentNodeId ? t : s
  const targetNode = props.allNodes.find(n => n.id === targetId)
  return targetNode ? targetNode.title : targetId.slice(0, 12)
}

function getNodeName(nodeId) {
  const n = props.allNodes.find(x => x.id === nodeId)
  return n ? n.title : nodeId.slice(0, 12)
}

// === 分组切换 ===
function onGroupChange(groupId) {
  if (!groupId || !props.node) return
  groupStore.moveNodeToGroup(props.node.id, groupId)
  graphStore.version++
  graphStore.restartTick++
  ElMessage.success('节点已移动到目标分组')
}

// === 隔离管理 ===
function onRemoveIsolate(nodeId) {
  if (!props.node) return
  graphStore.removeIsolate(props.node.id, nodeId)
  ElMessage.success('已解除隔离')
}

// === 学习路径 ===
const learningPath = computed(() => {
  if (!props.node) return { target: null, prerequisites: [] }
  return buildLearningPath(props.node.id, graphStore.nodes, graphStore.links)
})
const learningGroups = computed(() => groupByLevel(learningPath.value.prerequisites))
function onExportLearningPath() {
  const { target, prerequisites } = learningPath.value
  const md = toLearningPathMarkdown(target, prerequisites)
  downloadText(`${(target?.title || '学习路径')}.md`, md)
  ElMessage.success('学习路径已导出为 Markdown')
}
</script>

<style scoped>
.node-drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 900;
  display: flex;
  justify-content: flex-end;
}
.node-drawer {
  width: 380px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-primary);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.drawer-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-full);
  transition: all 0.15s var(--ease-out);
}
.drawer-close:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.drawer-section {
  margin-bottom: 20px;
}
.drawer-section h4 {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-light);
}
.info-row {
  display: flex;
  margin-bottom: 6px;
  font-size: var(--fs-md);
}
.info-label {
  color: var(--text-muted);
  width: 70px;
  flex-shrink: 0;
}
.info-value {
  color: var(--text-primary);
  flex: 1;
  word-break: break-all;
}
.mono {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}
.tag {
  display: inline-block;
  font-size: var(--fs-xs);
  background: var(--bg-tertiary);
  color: var(--accent-light);
  padding: 1px 8px;
  border-radius: var(--radius-full);
  margin-right: 3px;
  margin-bottom: 3px;
}
.tag.entity {
  color: var(--warning);
}
.empty-hint {
  color: var(--text-muted);
  font-size: var(--fs-md);
  text-align: center;
  padding: 20px;
}
.relation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.relation-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  padding: 10px 12px;
  transition: box-shadow 0.15s var(--ease-out), transform 0.15s var(--ease-out);
}
.relation-item:hover {
  transform: translateY(-1px);
}
.rel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.rel-type-badge {
  font-size: var(--fs-xs);
  color: #fff;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-weight: 500;
}
.rel-score {
  font-size: var(--fs-sm);
  font-family: var(--font-mono);
  color: var(--accent);
}
.rel-target {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-md);
}
.rel-arrow {
  color: var(--text-muted);
}
.rel-target-name {
  color: var(--text-primary);
  font-weight: 500;
}
.rel-evidence {
  margin-top: 4px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 6px 8px;
  border-radius: 4px;
  border-left: 2px solid var(--accent);
  word-break: break-all;
}
.rel-meta {
  margin-top: 3px;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.raw-text {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  font-family: var(--font-mono);
}

/* 校验状态 */
.validation-issues {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.validation-issue-item {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: 6px 8px;
  font-size: var(--fs-xs);
}
.vi-type {
  font-size: var(--fs-xs);
  color: #fff;
  padding: 1px 6px;
  border-radius: 8px;
  display: inline-block;
  margin-bottom: 3px;
}
.vi-reason {
  color: var(--text-secondary);
  line-height: 1.4;
}
.vi-suggestion {
  color: var(--accent-light);
  margin-top: 3px;
}

/* 分组选择 */
.info-select {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: var(--fs-sm);
  padding: 3px 6px;
  outline: none;
  cursor: pointer;
}
.info-select:focus {
  border-color: var(--accent);
}

/* 隔离黑名单 */
.isolate-blacklist {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ib-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: var(--fs-xs);
}
.ib-name {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 6px;
}
.ib-item .btn {
  font-size: var(--fs-xs);
  padding: 2px 6px;
}

/* 学习路径 */
.lp-group {
  margin-bottom: 8px;
}
.lp-level {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 4px;
}
.lp-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-primary);
  padding: 3px 0 3px 4px;
}
.lp-arrow {
  color: var(--text-muted);
  flex-shrink: 0;
}
.lp-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lp-export {
  width: 100%;
  margin-top: 10px;
  padding: 7px 12px;
  border-radius: var(--radius-full);
  background: var(--accent-fill);
  color: var(--on-accent);
  border: none;
  cursor: pointer;
  font-size: var(--fs-sm);
  transition: background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.lp-export:hover {
  background: var(--accent-strong);
  transform: translateY(-1px);
}
.lp-export:active {
  transform: scale(0.97);
}

/* 过渡动画 */
.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-slide-enter-active .node-drawer,
.drawer-slide-leave-active .node-drawer {
  transition: transform 0.25s ease;
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
}
.drawer-slide-enter-from .node-drawer,
.drawer-slide-leave-to .node-drawer {
  transform: translateX(100%);
}
</style>