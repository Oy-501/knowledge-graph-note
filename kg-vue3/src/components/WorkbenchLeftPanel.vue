<template>
  <div class="wbl-panel">
    <!-- 搜索 -->
    <div v-if="activeTab !== 'folders'" class="wbl-search">
      <input
        v-model="searchQuery"
        class="wbl-search-input"
        placeholder="搜索知识库..."
        @input="onSearch"
      />
    </div>

    <!-- 新建笔记按钮 -->
    <button type="button"
      v-if="activeTab !== 'folders'"
      class="wbl-btn-new"
      @click="$emit('new-note')"
    >
      + 新建笔记
    </button>

    <!-- 笔记管理入口 -->
    <button type="button"
      v-if="activeTab !== 'folders'"
      class="wbl-btn-manage"
      @click="$emit('open-note-manage')"
    >
      📝 笔记管理
    </button>

    <!-- 标签切换 -->
    <div class="wbl-tabs">
      <button type="button"
        class="wbl-tab"
        :class="{ active: activeTab === 'notes' }"
        @click="activeTab = 'notes'"
      >📝 笔记</button>
      <button type="button"
        class="wbl-tab"
        :class="{ active: activeTab === 'files' }"
        @click="activeTab = 'files'"
      >📁 文件</button>
      <button type="button"
        class="wbl-tab"
        :class="{ active: activeTab === 'nodes' }"
        @click="activeTab = 'nodes'"
      >🧩 知识点</button>
      <button type="button"
        class="wbl-tab"
        :class="{ active: activeTab === 'folders' }"
        @click="activeTab = 'folders'"
      >🗂 文件夹</button>
    </div>

    <!-- ===== 文件夹工作区（本地 .md 为源 + .kg_meta 双写） ===== -->
    <div v-if="activeTab === 'folders'" class="wbl-folder-host">
      <FolderWorkspacePanel
        @select-folder-note="$emit('select-folder-note', $event)"
        @focus-online="activeTab = 'notes'"
      />
    </div>

    <!-- ===== 笔记列表 ===== -->
    <div v-if="activeTab === 'notes'" class="wbl-list">
      <div v-if="filteredNotes.length === 0" class="wbl-empty">
        <el-icon class="wbl-empty-icon" :size="28"><Document /></el-icon>
        <p class="wbl-empty-text">暂无笔记</p>
        <p class="wbl-empty-hint">创建第一篇笔记，开始构建知识库</p>
        <button type="button" class="wbl-empty-btn" @click="$emit('new-note')">+ 新建笔记</button>
      </div>
      <div
        v-for="note in filteredNotes"
        :key="note.id"
        class="wbl-item"
        :class="{ active: currentNoteId === note.id }"
        @click="$emit('select-note', note.id)"
        draggable="true"
        @dragstart="onDragStart($event, { type: 'note', id: note.id, title: note.title })"
      >
        <div class="wbl-item-header">
          <span class="wbl-item-title">📄 {{ note.title }}</span>
          <span
            class="wbl-item-status"
            :style="{ color: scoreColor(note.accuracyScore) }"
          >
            {{ note.accuracyScore || 0 }}%
          </span>
        </div>
        <div class="wbl-item-meta">
          <span>🔗 {{ (note.linkedFiles?.length || 0) + (note.linkedNodes?.length || 0) }} 关联</span>
          <span>{{ formatAgo(note.updatedAt) }}</span>
        </div>
      </div>
    </div>

    <!-- ===== 文件列表 ===== -->
    <div v-if="activeTab === 'files'" class="wbl-list">
      <div v-if="filteredFiles.length === 0" class="wbl-empty">
        <el-icon class="wbl-empty-icon" :size="28"><FolderOpened /></el-icon>
        <p class="wbl-empty-text">暂无文件</p>
        <p class="wbl-empty-hint">上传文档后可自动抽取知识点</p>
      </div>
      <div
        v-for="file in filteredFiles"
        :key="file.id"
        class="wbl-item"
        draggable="true"
        @dragstart="onDragStart($event, { type: 'file', id: file.id, title: file.name })"
      >
        <div class="wbl-item-header">
          <span class="wbl-item-title">📁 {{ file.name }}</span>
          <span class="wbl-item-tag">{{ file.status }}</span>
        </div>
        <div class="wbl-item-meta">
          <span>🧩 {{ file.kpCount || 0 }} 知识点</span>
          <span>{{ formatAgo(file.parsedAt) }}</span>
        </div>
      </div>
    </div>

    <!-- ===== 知识点列表 ===== -->
    <div v-if="activeTab === 'nodes'" class="wbl-list">
      <div v-if="filteredNodes.length === 0" class="wbl-empty">
        <el-icon class="wbl-empty-icon" :size="28"><Connection /></el-icon>
        <p class="wbl-empty-text">{{ searchQuery ? '无匹配知识点' : '暂无知识点' }}</p>
        <p class="wbl-empty-hint">{{ searchQuery ? '换个关键词试试' : '上传文件后自动生成知识图谱' }}</p>
      </div>
      <div
        v-for="node in filteredNodes"
        :key="node.id"
        class="wbl-item"
        draggable="true"
        @dragstart="onDragStart($event, { type: 'node', id: node.id, title: node.title })"
      >
        <div class="wbl-item-header">
          <span class="wbl-item-title">{{ node.title }}</span>
          <span class="wbl-item-level" :style="{ background: getLevelColor(node.level) }">
            L{{ node.level || 3 }}
          </span>
        </div>
        <div class="wbl-item-meta">
          <span>{{ node.description?.slice(0, 40) || '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { scoreColor } from '@/utils/palette'
import { ref, computed } from 'vue'
import { useNoteStore } from '@/store/noteStore'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'
import FolderWorkspacePanel from './FolderWorkspacePanel.vue'
import { getLevelColor } from '@/utils/mdParser'
import { formatAgo } from '@/utils/format'

const props = defineProps({
  currentNoteId: { type: String, default: null }
})

defineEmits(['select-note', 'new-note', 'drag-start', 'open-note-manage', 'select-folder-note'])

const noteStore = useNoteStore()
const fileStore = useFileStore()
const graphStore = useGraphStore()

const activeTab = ref('notes')
const searchQuery = ref('')

const filteredNotes = computed(() => {
  let notes = noteStore.sortedNotes
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    notes = notes.filter(n =>
      n.title.toLowerCase().includes(q)
      || (n.content || '').toLowerCase().includes(q)
    )
  }
  return notes
})

const filteredFiles = computed(() => {
  let files = fileStore.uploadedFiles || []
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    files = files.filter(f => f.name.toLowerCase().includes(q))
  }
  return files
})

const filteredNodes = computed(() => {
  let nodes = graphStore.nodes.filter(n => n.validate?.status !== 'discarded')
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    nodes = nodes.filter(n =>
      n.title.toLowerCase().includes(q)
      || (n.description || '').toLowerCase().includes(q)
    )
  }
  return nodes.slice(0, 50)
})

function onSearch() {}
function onDragStart(ev, data) {
  ev.dataTransfer.setData('application/json', JSON.stringify(data))
  ev.dataTransfer.effectAllowed = 'link'
}
</script>

<style scoped>
.wbl-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.wbl-search {
  padding: 8px 10px;
  flex-shrink: 0;
}
.wbl-search-input {
  width: 100%;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-full);
  color: var(--text-primary);
  font-size: var(--fs-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.wbl-search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.wbl-btn-new {
  margin: 0 10px 8px;
  padding: 7px 0;
  background: var(--accent-fill);
  color: var(--on-accent);
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition:
    background var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
  flex-shrink: 0;
}
.wbl-btn-new:hover {
  background: var(--accent-strong);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.wbl-btn-new:active {
  transform: scale(0.97);
}
.wbl-btn-manage {
  margin: 0 10px 8px;
  padding: 6px 0;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
  flex-shrink: 0;
}
.wbl-btn-manage:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent);
}
.wbl-btn-manage:active {
  transform: scale(0.97);
}
.wbl-tabs {
  display: flex;
  padding: 0 10px;
  gap: 2px;
  flex-shrink: 0;
  margin-bottom: 8px;
}
.wbl-tab {
  flex: 1;
  padding: 4px 0;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: var(--fs-xs);
  cursor: pointer;
  border-radius: var(--radius-full);
  transition: all var(--dur-fast) var(--ease-out);
  white-space: nowrap;
}
.wbl-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.wbl-tab.active {
  color: var(--accent-strong);
  background: var(--accent-soft);
  font-weight: 600;
}
/* 文件夹工作区占满剩余高度，内部自行滚动 */
.wbl-folder-host {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  display: flex;
}
.wbl-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}
.wbl-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 36px 16px;
  gap: 2px;
}
.wbl-empty-icon {
  color: var(--text-muted);
  opacity: 0.7;
  margin-bottom: 8px;
}
.wbl-empty-text {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 2px;
}
.wbl-empty-hint {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin: 0 0 10px;
}
.wbl-empty-btn {
  padding: 5px 16px;
  background: var(--accent-fill);
  color: var(--on-accent);
  border: none;
  border-radius: var(--radius-full);
  font-size: var(--fs-xs);
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.wbl-empty-btn:hover {
  background: var(--accent-strong);
}
.wbl-empty-btn:active {
  transform: scale(0.95);
}
.wbl-item {
  padding: 9px 11px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
  margin-bottom: 6px;
  box-shadow: var(--shadow-sm);
}
.wbl-item:hover {
  background: var(--bg-secondary);
  border-color: var(--border);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.wbl-item:active {
  transform: scale(0.97);
}
.wbl-item.active {
  background: var(--accent-soft);
  border-color: var(--accent);
  border-left: 3px solid var(--accent);
}
.wbl-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}
.wbl-item-title {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 6px;
}
.wbl-item-status {
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  font-weight: 600;
  flex-shrink: 0;
}
.wbl-item-tag {
  font-size: var(--fs-xs);
  background: var(--accent-soft);
  color: var(--text-secondary);
  padding: 1px 7px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}
.wbl-item-level {
  font-size: var(--fs-xs);
  color: #fff;
  padding: 1px 7px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}
.wbl-item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
</style>