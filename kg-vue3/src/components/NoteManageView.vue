<template>
  <div class="nmv-panel" :class="{ 'nmv-fullscreen': isFullscreen }">
    <!-- 顶部操作栏 -->
    <div class="nmv-header">
      <div class="nmv-header-left">
        <h3 class="nmv-title">笔记管理</h3>
        <span class="nmv-count">共 {{ filteredNotes.length }} 篇笔记</span>
      </div>
      <div class="nmv-header-right">
        <button type="button" class="nmv-btn nmv-btn-new" @click="onNewNote">
          <span>+</span> 新建笔记
        </button>
        <button type="button" v-if="showBatchBar" class="nmv-btn" @click="exitBatchMode">取消选择</button>
      </div>
    </div>

    <!-- 搜索与筛选栏 -->
    <div class="nmv-toolbar">
      <div class="nmv-search-wrap">
        <span class="nmv-search-icon">🔍</span>
        <input
          v-model="searchQuery"
          class="nmv-search"
          placeholder="搜索笔记标题或内容..."
          @input="onSearch"
        />
        <button type="button" v-if="searchQuery" class="nmv-search-clear" @click="searchQuery = ''">✕</button>
      </div>
      <div class="nmv-filter-row">
        <button type="button"
          class="nmv-filter-btn"
          :class="{ active: currentFilter === 'all' }"
          @click="currentFilter = 'all'"
        >全部 ({{ noteStore.noteCount }})</button>
        <button type="button"
          class="nmv-filter-btn"
          :class="{ active: currentFilter === 'today' }"
          @click="currentFilter = 'today'"
        >今日 ({{ todayCount }})</button>
        <button type="button"
          class="nmv-filter-btn"
          :class="{ active: currentFilter === 'pending' }"
          @click="currentFilter = 'pending'"
        >待关联 ({{ pendingCount }})</button>
        <button type="button"
          class="nmv-filter-btn"
          :class="{ active: currentFilter === 'archived' }"
          @click="currentFilter = 'archived'"
        >已归档 ({{ archivedCount }})</button>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="showBatchBar" class="nmv-batch-bar">
      <span class="nmv-batch-label">已选 {{ selectedIds.size }} 篇</span>
      <div class="nmv-batch-actions">
        <button type="button" class="nmv-btn nmv-btn-sm" @click="batchArchive">批量归档</button>
        <button type="button" class="nmv-btn nmv-btn-sm nmv-btn-danger" @click="batchDelete">批量删除</button>
        <button type="button" class="nmv-btn nmv-btn-sm" @click="batchExport">批量导出</button>
      </div>
    </div>

    <!-- 笔记列表 -->
    <div class="nmv-list">
      <div v-if="filteredNotes.length === 0" class="nmv-empty">
        <span class="nmv-empty-icon">📝</span>
        <p>{{ searchQuery ? '未找到匹配的笔记' : '暂无笔记' }}</p>
        <p class="nmv-empty-hint">{{ searchQuery ? '换个关键词，或清空搜索条件' : '创建第一篇笔记，开始构建知识库' }}</p>
        <button type="button" v-if="!searchQuery" class="nmv-btn nmv-btn-new" @click="onNewNote"><span>+</span> 新建笔记</button>
      </div>

      <div
        v-for="note in filteredNotes"
        :key="note.id"
        class="nmv-item"
        :class="{
          'nmv-selected': selectedIds.has(note.id),
          'nmv-archived': note.archived
        }"
        @click="onItemClick(note)"
      >
        <!-- 选择框 -->
        <div class="nmv-checkbox" @click.stop="toggleSelect(note.id)">
          <span v-if="selectedIds.has(note.id)" class="nmv-checked">✓</span>
        </div>

        <!-- 笔记信息 -->
        <div class="nmv-item-body">
          <div class="nmv-item-header">
            <span class="nmv-item-title">📄 {{ note.title || '未命名笔记' }}</span>
            <span
              v-if="note.accuracyScore !== undefined"
              class="nmv-item-badge"
              :class="{
                'nmv-badge-ok': note.accuracyScore >= 80,
                'nmv-badge-warn': note.accuracyScore >= 50 && note.accuracyScore < 80,
                'nmv-badge-err': note.accuracyScore < 50
              }"
            >
              {{ note.verified ? '✅' : '⚠️' }} {{ note.accuracyScore || 0 }}%
            </span>
          </div>
          <div class="nmv-item-meta">
            <span class="nmv-item-links">
              🔗 {{ (note.linkedFiles?.length || 0) + (note.linkedNodes?.length || 0) }} 关联
            </span>
            <span v-if="note.tags && note.tags.length > 0" class="nmv-item-tags">
              <span v-for="tag in note.tags" :key="tag" class="nmv-tag">🏷️ {{ tag }}</span>
            </span>
            <span class="nmv-item-time">{{ formatAgo(note.updatedAt) }}</span>
          </div>
          <div v-if="note.content" class="nmv-item-preview">
            {{ note.content.slice(0, 100) }}{{ note.content.length > 100 ? '...' : '' }}
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="nmv-item-actions" @click.stop>
          <button type="button" class="nmv-btn nmv-btn-sm" @click="onEdit(note)">编辑</button>
          <button type="button" class="nmv-btn nmv-btn-sm" @click="onViewLinks(note)">查看关联</button>
          <button type="button" v-if="!note.archived" class="nmv-btn nmv-btn-sm" @click="onArchive(note)">归档</button>
          <button type="button" v-else class="nmv-btn nmv-btn-sm" @click="onUnarchive(note)">取消归档</button>
          <button type="button" class="nmv-btn nmv-btn-sm nmv-btn-danger" @click="onDelete(note)">删除</button>
        </div>
      </div>
    </div>

    <!-- 底部状态栏 -->
    <div class="nmv-footer">
      <span>共 {{ filteredNotes.length }} 篇 · 已关联 {{ linkedCount }} 篇 · 待处理 {{ pendingCount }} 篇</span>
      <button type="button" class="nmv-btn nmv-btn-sm" @click="onRefresh">🔄 刷新</button>
    </div>

    <!-- 关联详情弹窗 -->
    <div v-if="linkDialog.visible" class="nmv-overlay" @click.self="linkDialog.visible = false">
      <div class="nmv-dialog">
        <div class="nmv-dialog-header">
          <h4>📄 {{ linkDialog.note?.title }}</h4>
          <button type="button" class="nmv-dialog-close" @click="linkDialog.visible = false">✕</button>
        </div>
        <div class="nmv-dialog-body">
          <div class="nmv-dialog-section">
            <h5>关联文件 ({{ linkDialog.files.length }})</h5>
            <div v-if="linkDialog.files.length === 0" class="nmv-dialog-empty">暂无关联文件</div>
            <div v-for="f in linkDialog.files" :key="f.id" class="nmv-dialog-item">
              <span>📁 {{ f.name }}</span>
              <span class="nmv-dialog-status">{{ f.status }}</span>
            </div>
          </div>
          <div class="nmv-dialog-section">
            <h5>关联知识点 ({{ linkDialog.nodes.length }})</h5>
            <div v-if="linkDialog.nodes.length === 0" class="nmv-dialog-empty">暂无关联知识点</div>
            <div v-for="n in linkDialog.nodes" :key="n.id" class="nmv-dialog-item">
              <span>🧩 {{ n.title }}</span>
              <span class="nmv-dialog-level">L{{ n.level || 3 }}</span>
            </div>
          </div>
        </div>
        <div class="nmv-dialog-footer">
          <button type="button" class="nmv-btn" @click="linkDialog.visible = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useNoteStore } from '@/store/noteStore'
import { useGraphStore } from '@/store/graphStore'
import { useFileStore } from '@/store/fileStore'
import { formatAgo } from '@/utils/format'
import { downloadText } from '@/utils/download'

const props = defineProps({
  isFullscreen: { type: Boolean, default: false },
  isEmbedded: { type: Boolean, default: false }
})

const emit = defineEmits(['edit-note', 'new-note', 'close'])

const noteStore = useNoteStore()
const graphStore = useGraphStore()
const fileStore = useFileStore()

const searchQuery = ref('')
const currentFilter = ref('all')
const selectedIds = ref(new Set())
const showBatchBar = computed(() => selectedIds.value.size > 0)

const linkDialog = ref({
  visible: false,
  note: null,
  files: [],
  nodes: []
})

// 统计计数
const todayCount = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return noteStore.notes.filter(n => n.updatedAt >= today.getTime()).length
})

const pendingCount = computed(() => {
  return noteStore.notes.filter(n =>
    (n.linkedFiles?.length || 0) + (n.linkedNodes?.length || 0) === 0
  ).length
})

const archivedCount = computed(() => {
  return noteStore.notes.filter(n => n.archived).length
})

const linkedCount = computed(() => {
  return noteStore.notes.filter(n =>
    (n.linkedFiles?.length || 0) + (n.linkedNodes?.length || 0) > 0
  ).length
})

// 过滤后的笔记列表
const filteredNotes = computed(() => {
  let notes = [...noteStore.notes]

  // 搜索过滤
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    notes = notes.filter(n =>
      (n.title || '').toLowerCase().includes(q)
        || (n.content || '').toLowerCase().includes(q)
        || (n.tags || []).some(t => t.toLowerCase().includes(q))
    )
  }

  // 状态过滤
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  switch (currentFilter.value) {
    case 'today':
      notes = notes.filter(n => n.updatedAt >= today.getTime())
      break
    case 'pending':
      notes = notes.filter(n =>
        (n.linkedFiles?.length || 0) + (n.linkedNodes?.length || 0) === 0
      )
      break
    case 'archived':
      notes = notes.filter(n => n.archived)
      break
  }

  // 排序：最新在前
  notes.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
  return notes
})

onMounted(async () => {
  await noteStore.loadNotes()
})

function onSearch() {}

function onItemClick(note) {
  if (showBatchBar.value) {
    toggleSelect(note.id)
  } else {
    onEdit(note)
  }
}

function toggleSelect(noteId) {
  const next = new Set(selectedIds.value)
  if (next.has(noteId)) {
    next.delete(noteId)
  } else {
    next.add(noteId)
  }
  selectedIds.value = next
}

function exitBatchMode() {
  selectedIds.value = new Set()
}

async function onNewNote() {
  await noteStore.createNote('未命名笔记', '')
  emit('new-note')
}

function onEdit(note) {
  noteStore.setCurrentNote(note.id)
  emit('edit-note', note.id)
}

function onViewLinks(note) {
  const files = (note.linkedFiles || []).map(fid => {
    const f = fileStore.uploadedFiles?.find(ff => ff.id === fid)
    return { id: fid, name: f?.name || fid, status: f?.status || 'unknown' }
  })
  const nodes = (note.linkedNodes || []).map(nid => {
    const n = graphStore.nodes.find(nn => nn.id === nid)
    return { id: nid, title: n?.title || nid, level: n?.level || 3 }
  })
  linkDialog.value = { visible: true, note, files, nodes }
}

async function onArchive(note) {
  await noteStore.saveNote(note.id, { archived: true })
  ElMessage.success('已归档')
}

async function onUnarchive(note) {
  await noteStore.saveNote(note.id, { archived: false })
  ElMessage.success('已取消归档')
}

async function onDelete(note) {
  try {
    await ElMessageBox.confirm(
      `确定要删除笔记"${note.title}"吗？此操作不可恢复。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await noteStore.deleteNote(note.id)
    selectedIds.value.delete(note.id)
    ElMessage.success('笔记已删除')
  } catch (e) {
    // 用户取消
  }
}

async function batchArchive() {
  for (const id of selectedIds.value) {
    await noteStore.saveNote(id, { archived: true })
  }
  ElMessage.success(`已归档 ${selectedIds.value.size} 篇笔记`)
  selectedIds.value = new Set()
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedIds.value.size} 篇笔记吗？此操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    for (const id of selectedIds.value) {
      await noteStore.deleteNote(id)
    }
    ElMessage.success(`已删除 ${selectedIds.value.size} 篇笔记`)
    selectedIds.value = new Set()
  } catch (e) {
    // 用户取消
  }
}

async function batchExport() {
  const notes = noteStore.notes.filter(n => selectedIds.value.has(n.id))
  for (const note of notes) {
    exportNote(note)
  }
  ElMessage.success(`已导出 ${notes.length} 篇笔记`)
}

function exportNote(note) {
  const tags = (note.tags || []).join(', ')
  const updatedAt = new Date(note.updatedAt).toLocaleString()
  const content = `# ${note.title}\n\n${note.content || ''}\n\n---\n> 标签: ${tags}\n> 更新时间: ${updatedAt}\n`
  const filename = `${note.title.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '_')}.md`
  downloadText(filename, content, 'text/markdown')
}

async function onRefresh() {
  await noteStore.loadNotes()
  ElMessage.success('列表已刷新')
}
</script>

<style scoped>
.nmv-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg-primary);
}

.nmv-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1100;
}

/* 头部 */
.nmv-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-secondary);
}
.nmv-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.nmv-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.nmv-count {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
}
.nmv-header-right {
  display: flex;
  gap: 6px;
}
.nmv-btn {
  padding: 5px 12px;
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.nmv-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border);
}
.nmv-btn:active {
  transform: scale(0.96);
}
.nmv-btn-new {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: var(--accent);
  font-weight: 500;
  box-shadow: var(--shadow-sm);
}
.nmv-btn-new:hover {
  background: var(--accent-strong);
  color: #fff;
  border-color: var(--accent-strong);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.nmv-btn-sm {
  padding: 3px 8px;
  font-size: var(--fs-xs);
}
.nmv-btn-danger {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 30%, transparent);
}
.nmv-btn-danger:hover {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 45%, transparent);
}

/* 工具栏 */
.nmv-toolbar {
  padding: 10px 16px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-light);
}
.nmv-search-wrap {
  position: relative;
  margin-bottom: 8px;
}
.nmv-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--fs-sm);
  color: var(--text-muted);
}
.nmv-search {
  width: 100%;
  padding: 7px 36px 7px 30px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-full);
  color: var(--text-primary);
  font-size: var(--fs-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.nmv-search:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.nmv-search-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--fs-sm);
}
.nmv-filter-row {
  display: flex;
  gap: 4px;
}
.nmv-filter-btn {
  flex: 1;
  padding: 4px 0;
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  color: var(--text-muted);
  font-size: var(--fs-xs);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.nmv-filter-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.nmv-filter-btn.active {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: var(--accent);
  font-weight: 500;
  box-shadow: var(--shadow-sm);
}

/* 批量操作栏 */
.nmv-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--accent-soft);
  border-bottom: 1px solid color-mix(in srgb, var(--accent) 20%, transparent);
  flex-shrink: 0;
}
.nmv-batch-label {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--accent-light);
}
.nmv-batch-actions {
  display: flex;
  gap: 4px;
}

/* 列表 */
.nmv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.nmv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 56px 20px;
  color: var(--text-muted);
  text-align: center;
}
.nmv-empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  font-size: 30px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  opacity: 0.8;
  margin-bottom: 14px;
}
.nmv-empty p {
  font-size: var(--fs-md);
  margin: 0 0 4px;
}
.nmv-empty-hint {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-bottom: 14px !important;
}

.nmv-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
  background: var(--bg-secondary);
  box-shadow: var(--shadow-sm);
}
.nmv-item:hover {
  background: var(--bg-secondary);
  border-color: var(--border);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.nmv-item:active {
  transform: scale(0.98);
}
.nmv-item.nmv-selected {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.nmv-item.nmv-archived {
  opacity: 0.6;
}
.nmv-checkbox {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
  transition: all var(--dur-fast) var(--ease-out);
  cursor: pointer;
}
.nmv-checkbox:hover {
  border-color: var(--accent);
}
.nmv-checked {
  font-size: var(--fs-sm);
  color: var(--accent);
  font-weight: 700;
}
.nmv-item-body {
  flex: 1;
  min-width: 0;
}
.nmv-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.nmv-item-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.nmv-item-badge {
  font-size: var(--fs-xs);
  padding: 1px 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  margin-left: 8px;
  font-weight: 500;
  font-family: var(--font-mono);
}
.nmv-badge-ok {
  background: var(--success-soft);
  color: var(--success);
}
.nmv-badge-warn {
  background: var(--warning-soft);
  color: var(--warning);
}
.nmv-badge-err {
  background: var(--danger-soft);
  color: var(--danger);
}
.nmv-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}
.nmv-item-links {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.nmv-item-tags {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
}
.nmv-tag {
  font-size: var(--fs-xs);
  background: var(--apricot-soft);
  color: var(--apricot-strong);
  padding: 1px 8px;
  border-radius: var(--radius-full);
}
.nmv-item-time {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-left: auto;
}
.nmv-item-preview {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.nmv-item-actions {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex-shrink: 0;
}

/* 底部 */
.nmv-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-top: 1px solid var(--border-light);
  font-size: var(--fs-xs);
  color: var(--text-muted);
  flex-shrink: 0;
}

/* 弹窗 */
.nmv-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.45);
  backdrop-filter: blur(4px);
  z-index: 1150;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nmv-dialog {
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  width: 480px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}
.nmv-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
}
.nmv-dialog-header h4 {
  font-size: var(--fs-base);
  color: var(--text-primary);
  margin: 0;
}
.nmv-dialog-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.nmv-dialog-body {
  padding: 14px 16px;
  overflow-y: auto;
  flex: 1;
}
.nmv-dialog-section {
  margin-bottom: 14px;
}
.nmv-dialog-section h5 {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-muted);
  margin: 0 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.nmv-dialog-empty {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  padding: 10px;
  text-align: center;
}
.nmv-dialog-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  font-size: var(--fs-xs);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  margin-bottom: 4px;
}
.nmv-dialog-status {
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.nmv-dialog-level {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  background: var(--accent-soft);
  padding: 1px 7px;
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
}
.nmv-dialog-footer {
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
  display: flex;
  justify-content: flex-end;
}
</style>