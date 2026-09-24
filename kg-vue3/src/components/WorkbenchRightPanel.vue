<template>
  <div class="wbr-panel">
    <div v-if="visibleRecommendations.length > 0" class="wbr-section wbr-recommend">
      <div class="wbr-section-header"><h4>🔮 智能连接推荐 <span class="wbr-count">({{ visibleRecommendations.length }})</span></h4></div>
      <div v-for="rec in visibleRecommendations" :key="rec.node.id" class="wbr-recommend-item">
        <div class="wbr-recommend-text">检测到笔记可能涉及 <b>「{{ rec.node.title }}」</b><span v-if="rec.reason" class="wbr-recommend-reason">（提及：{{ rec.reason }}）</span></div>
        <div class="wbr-item-actions">
          <button type="button" class="wbr-btn wbr-btn-primary" @click="$emit('link-node', rec.node.id)">＋ 关联</button>
          <button type="button" class="wbr-btn" @click="dismissRecommend(rec.node.id)">忽略</button>
        </div>
      </div>
    </div>
    <div class="wbr-section">
      <div class="wbr-section-header" @click="showFiles = !showFiles">
        <h4>📄 相关文件 <span class="wbr-count">({{ linkedFiles.length }})</span></h4>
        <span class="wbr-toggle">{{ showFiles ? '▼' : '▶' }}</span>
      </div>
      <div v-if="showFiles">
        <div v-if="linkedFiles.length === 0" class="wbr-empty"><el-icon class="wbr-empty-icon" :size="22"><FolderOpened /></el-icon><span>暂无关联文件，拖拽文件到笔记即可关联</span></div>
        <div v-for="f in linkedFiles" :key="f.id" class="wbr-item">
          <div class="wbr-item-header"><span class="wbr-item-title">📄 {{ f.name }}</span><span class="wbr-item-score">{{ f.matchScore || 0 }}%</span></div>
          <div v-if="f.relationType" class="wbr-item-meta">关联类型：<span class="wbr-rel-pill">{{ f.relationType }}</span></div>
          <div class="wbr-item-actions"><button type="button" class="wbr-btn" @click="$emit('open-file', f.id)">查看</button><button type="button" class="wbr-btn wbr-btn-danger" @click="$emit('unlink-file', f.id)">解除</button></div>
        </div>
      </div>
    </div>
    <div class="wbr-section">
      <div class="wbr-section-header" @click="showNodes = !showNodes">
        <h4>🧩 相关知识点 <span class="wbr-count">({{ linkedNodes.length + matchedNodes.length }})</span></h4>
        <span class="wbr-toggle">{{ showNodes ? '▼' : '▶' }}</span>
      </div>
      <div v-if="showNodes">
        <div v-if="linkedNodes.length === 0 && matchedNodes.length === 0" class="wbr-empty"><el-icon class="wbr-empty-icon" :size="22"><Connection /></el-icon><span>暂无相关知识点，编辑笔记时将自动匹配</span></div>
        <div v-for="item in linkedNodes" :key="item.node.id" class="wbr-item wbr-linked">
          <div class="wbr-item-header"><span class="wbr-item-title">{{ item.node.title }}</span><span class="wbr-item-badge" :style="{ background: getLevelColor(item.node.level) }">L{{ item.node.level || 3 }}</span></div>
          <div class="wbr-item-meta" v-if="item.relationLabel">关系：<span class="wbr-rel-pill">{{ item.relationLabel }}</span><span v-if="item.evidence" class="wbr-evidence">证据：{{ item.evidence }}</span></div>
          <div class="wbr-item-actions"><span class="wbr-confirmed" v-if="item.confirmed">✅ 已确认</span><button type="button" v-else class="wbr-btn wbr-btn-primary" @click="$emit('confirm-link', item.node.id)">确认</button><button type="button" class="wbr-btn" @click="$emit('edit-relation', item.node.id)">修改关系</button><button type="button" class="wbr-btn wbr-btn-danger" @click="$emit('unlink-node', item.node.id)">解除</button></div>
        </div>
        <div v-for="item in matchedNodes" :key="item.node.id" class="wbr-item wbr-pending">
          <div class="wbr-item-header"><span class="wbr-item-title">{{ item.node.title }}</span><span class="wbr-item-badge wbr-badge-pending">待确认</span></div>
          <div class="wbr-item-meta">匹配词：{{ item.term }}<span class="wbr-match-type">({{ item.matchType }})</span></div>
          <div class="wbr-item-actions"><button type="button" class="wbr-btn wbr-btn-primary" @click="$emit('link-node', item.node.id)">关联</button><button type="button" class="wbr-btn" @click="$emit('create-node', item.term)">创建知识点</button><button type="button" class="wbr-btn" @click="$emit('ignore-node', item.node.id)">忽略</button></div>
        </div>
      </div>
    </div>
    <div class="wbr-section">
      <div class="wbr-section-header" @click="showValidation = !showValidation">
        <h4>✅ 知识校验 <span class="wbr-count">({{ validationIssues.length }})</span></h4>
        <span class="wbr-toggle">{{ showValidation ? '▼' : '▶' }}</span>
      </div>
      <div v-if="showValidation">
        <div v-if="validationIssues.length === 0" class="wbr-pass"><span class="wbr-empty-icon">✅</span> 所有内容已通过校验</div>
        <div v-for="(issue, idx) in validationIssues" :key="idx" class="wbr-issue" :class="issue.severity === 'error' ? 'wbr-issue-error' : 'wbr-issue-warn'">
          <div class="wbr-issue-type" :class="issue.severity === 'error' ? 'wbr-type-error' : 'wbr-type-warn'">{{ issue.type }}</div>
          <div class="wbr-issue-text">{{ issue.text?.slice(0, 80) }}</div>
          <div class="wbr-issue-desc" v-if="issue.description">{{ issue.description }}</div>
          <div class="wbr-issue-fix" v-if="issue.correction">💡 {{ issue.correction }}</div>
          <div class="wbr-issue-actions"><button type="button" class="wbr-btn wbr-btn-primary" @click="$emit('accept-fix', idx)">一键修正</button><button type="button" class="wbr-btn" @click="$emit('ignore-fix', idx)">忽略</button></div>
        </div>
      </div>
    </div>
    <div v-if="linkDialog.visible" class="wbr-overlay" @click.self="closeLinkDialog">
      <div class="wbr-dialog">
        <h4>关联到知识点</h4>
        <p class="wbr-dialog-hint">选择要关联的知识点及关系类型</p>
        <div class="wbr-dialog-list">
          <div v-for="n in linkDialog.candidates" :key="n.id" class="wbr-dialog-item" :class="{ 'wbr-dialog-item-selected': linkDialog.selected?.id === n.id }" @click="selectLinkCandidate(n)">
            <span>{{ n.title }}</span><span class="wbr-dialog-level">L{{ n.level || 3 }}</span>
          </div>
        </div>
        <div v-if="linkDialog.selected" class="wbr-dialog-rel">
          <span>关系类型：</span>
          <select v-model="linkDialog.relationType" class="wbr-select">
            <option value="contains">包含</option><option value="depends">依赖</option><option value="comparison">对比</option><option value="extends">扩展</option><option value="implements">实现</option><option value="based_on">基于</option><option value="related">相关</option>
          </select>
        </div>
        <div class="wbr-dialog-actions"><button type="button" class="wbr-btn wbr-btn-primary" @click="confirmLink">确认关联</button><button type="button" class="wbr-btn" @click="closeLinkDialog">取消</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGraphStore } from '@/store/graphStore'
import { useFileStore } from '@/store/fileStore'
import { getLevelColor } from '@/utils/mdParser'

const props = defineProps({
  linkedNodeIds: { type: Array, default: () => [] },
  linkedFileIds: { type: Array, default: () => [] },
  matchedNodes: { type: Array, default: () => [] },
  validationIssues: { type: Array, default: () => [] },
  nodeRelations: { type: Object, default: () => ({}) },
  recommendations: { type: Array, default: () => [] }
})
const emit = defineEmits(['open-file', 'unlink-file', 'unlink-node', 'link-node', 'create-node', 'ignore-node', 'confirm-link', 'edit-relation', 'accept-fix', 'ignore-fix'])
const graphStore = useGraphStore()
const fileStore = useFileStore()
const showFiles = ref(true)
const showNodes = ref(true)
const showValidation = ref(true)
const dismissedRecs = ref([])
const visibleRecommendations = computed(() => props.recommendations.filter(r => !dismissedRecs.value.includes(r.node.id)))
function dismissRecommend(nodeId) { dismissedRecs.value.push(nodeId) }
const linkDialog = ref({ visible: false, candidates: [], selected: null, relationType: 'related', onConfirm: null })
const linkedFiles = computed(() => props.linkedFileIds.map(fid => {
  const f = fileStore.uploadedFiles.find(ff => ff.id === fid)
  return { id: fid, name: f?.name || fid, matchScore: 85 }
}))
const linkedNodes = computed(() => props.linkedNodeIds.map(nid => {
  const node = graphStore.nodes.find(n => n.id === nid)
  if (!node) return null
  const rel = props.nodeRelations[nid] || {}
  return { node, relationLabel: rel.label || '关联', evidence: rel.evidence || '', confirmed: rel.confirmed || false }
}).filter(Boolean))
function openLinkDialog(candidates, onConfirm) {
  linkDialog.value = { visible: true, candidates: candidates || [], selected: null, relationType: 'related', onConfirm }
}
function selectLinkCandidate(node) { linkDialog.value.selected = node }
function confirmLink() {
  if (linkDialog.value.selected && linkDialog.value.onConfirm) linkDialog.value.onConfirm(linkDialog.value.selected, linkDialog.value.relationType)
  closeLinkDialog()
}
function closeLinkDialog() { linkDialog.value.visible = false }
defineExpose({ openLinkDialog })
</script>

<style scoped>
.wbr-panel { display: flex; flex-direction: column; height: 100%; overflow-y: auto; padding: 8px; }
.wbr-section { margin-bottom: 12px; }
.wbr-section-header { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; cursor: pointer; user-select: none; border-bottom: 1px solid var(--border-light); }
.wbr-section-header h4 { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; color: var(--text-secondary); margin: 0; transition: color var(--dur-fast) var(--ease-out); }
.wbr-section-header:hover h4 { color: var(--text-primary); }
.wbr-count { font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); font-weight: 500; }
.wbr-toggle { font-size: 9px; color: var(--text-muted); transition: color var(--dur-fast) var(--ease-out); }
.wbr-section-header:hover .wbr-toggle { color: var(--text-secondary); }
.wbr-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 18px 12px; color: var(--text-muted); font-size: 11px; text-align: center; }
.wbr-empty-icon { font-size: 14px; color: var(--text-muted); opacity: 0.75; }
.wbr-pass { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 6px; padding: 7px 12px; background: var(--success-soft); color: var(--success); border: 1px solid color-mix(in srgb, var(--success) 25%, transparent); border-radius: var(--radius-full); font-size: 11px; font-weight: 500; }
.wbr-item { position: relative; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: 12px; padding: 9px 11px; margin-top: 6px; box-shadow: var(--shadow-sm); transition: box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out); }
.wbr-item:hover { border-color: var(--border); box-shadow: var(--shadow-card-hover); transform: translateY(-1px); }
.wbr-item:active { transform: scale(0.98); }
.wbr-item.wbr-linked { border-left: 3px solid var(--success); }
.wbr-item.wbr-pending { border-left: 3px solid var(--warning); }
.wbr-item-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 3px; }
.wbr-item-title { font-size: 12px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.wbr-item-score { font-size: 10px; font-family: var(--font-mono); color: var(--accent); flex-shrink: 0; margin-left: 6px; }
.wbr-item-badge { font-size: 9px; color: #fff; padding: 1px 7px; border-radius: var(--radius-full); flex-shrink: 0; margin-left: 6px; }
.wbr-badge-pending { background: var(--warning); color: #fff; }
.wbr-item-meta { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.wbr-rel-pill { display: inline-block; padding: 1px 8px; background: var(--accent-soft); color: var(--accent-strong); border-radius: var(--radius-full); font-size: 9px; font-weight: 500; line-height: 1.5; }
.wbr-evidence { display: block; margin-top: 2px; color: var(--text-secondary); font-style: italic; }
.wbr-match-type { color: var(--accent-light); }
.wbr-item-actions { display: flex; gap: 4px; align-items: center; }
.wbr-confirmed { font-size: 10px; color: var(--success); font-weight: 500; }
.wbr-btn { padding: 2px 10px; border: 1px solid var(--border-light); background: var(--bg-secondary); color: var(--text-secondary); font-size: 10px; border-radius: var(--radius-full); cursor: pointer; transition: all var(--dur-fast) var(--ease-out); }
.wbr-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border); }
.wbr-btn:active { transform: scale(0.95); }
.wbr-btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.wbr-btn-primary:hover { background: var(--accent-strong); color: #fff; border-color: var(--accent-strong); }
.wbr-btn-danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 30%, transparent); }
.wbr-btn-danger:hover { background: var(--danger-soft); color: var(--danger); border-color: color-mix(in srgb, var(--danger) 45%, transparent); }
.wbr-recommend-item { position: relative; background: var(--bg-secondary); border: 1px solid color-mix(in srgb, var(--apricot) 35%, transparent); border-left: 3px solid var(--apricot); border-radius: 12px; padding: 9px 11px; margin-top: 6px; box-shadow: var(--shadow-sm); transition: box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out); }
.wbr-recommend-item:hover { box-shadow: var(--shadow-card-hover); transform: translateY(-1px); }
.wbr-recommend-text { font-size: 11px; color: var(--text-primary); line-height: 1.5; margin-bottom: 5px; }
.wbr-recommend-text b { color: var(--accent-strong); }
.wbr-recommend-reason { color: var(--text-muted); font-size: 10px; }
.wbr-issue { position: relative; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: 12px; padding: 7px 9px 7px 22px; margin-top: 6px; box-shadow: var(--shadow-sm); transition: box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out); }
.wbr-issue:hover { box-shadow: var(--shadow-card-hover); transform: translateY(-1px); }
.wbr-issue::before { content: ''; position: absolute; left: 9px; top: 13px; width: 7px; height: 7px; border-radius: 50%; }
.wbr-issue-error::before { background: var(--danger); box-shadow: 0 0 0 3px var(--danger-soft); }
.wbr-issue-warn::before { background: var(--warning); box-shadow: 0 0 0 3px var(--warning-soft); }
.wbr-issue-type { display: inline-block; font-size: 9px; padding: 1px 8px; border-radius: var(--radius-full); margin-bottom: 3px; font-weight: 500; }
.wbr-type-error { background: var(--danger-soft); color: var(--danger); }
.wbr-type-warn { background: var(--warning-soft); color: var(--warning); }
.wbr-issue-text { font-size: 11px; color: var(--text-primary); margin-bottom: 2px; }
.wbr-issue-desc { font-size: 10px; color: var(--text-secondary); }
.wbr-issue-fix { font-size: 10px; color: var(--accent-light); margin: 3px 0; }
.wbr-issue-actions { display: flex; gap: 4px; margin-top: 4px; }
.wbr-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); backdrop-filter: blur(4px); z-index: 1100; display: flex; align-items: center; justify-content: center; }
.wbr-dialog { background: var(--bg-primary); border: 1px solid var(--border-light); border-radius: var(--radius-lg); padding: 18px; min-width: 300px; max-width: 420px; box-shadow: var(--shadow-lg); }
.wbr-dialog h4 { font-size: 14px; color: var(--text-primary); margin: 0 0 6px; }
.wbr-dialog-hint { font-size: 11px; color: var(--text-muted); margin-bottom: 10px; }
.wbr-dialog-list { max-height: 200px; overflow-y: auto; margin-bottom: 10px; }
.wbr-dialog-item { display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: var(--radius); border: 1px solid transparent; cursor: pointer; font-size: 12px; color: var(--text-primary); margin-bottom: 3px; transition: all var(--dur-fast) var(--ease-out); }
.wbr-dialog-item:hover { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 25%, transparent); }
.wbr-dialog-item-selected { background: var(--accent-soft); border-color: var(--accent); }
.wbr-dialog-item:active { transform: scale(0.98); }
.wbr-dialog-item:has(+ .wbr-dialog-item) { border-bottom-color: var(--border-light); }
.wbr-dialog-level { font-size: 9px; color: var(--text-muted); }
.wbr-dialog-rel { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); margin-bottom: 10px; }
.wbr-select { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-primary); font-size: 11px; padding: 3px 8px; outline: none; transition: border-color var(--dur-fast) var(--ease-out); }
.wbr-select:focus { border-color: var(--accent); }
.wbr-dialog-actions { display: flex; gap: 6px; justify-content: flex-end; }
</style>
