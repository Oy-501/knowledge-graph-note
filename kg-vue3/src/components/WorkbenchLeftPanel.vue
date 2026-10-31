<!-- 工作台左栏：文件树与上传入口。 -->
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
        <p v-if="file.parseNote" class="wbl-item-note" :class="{ 'is-busy': isBusy(file) }">
          {{ file.parseNote }}
        </p>
        <div class="wbl-item-actions">
          <button class="wbl-cand-link" @click.stop="openCandidates(file)">判断知识点</button>
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

    <!-- 候选判断：只影响自己的图谱，不写公共知识库 -->
    <el-dialog v-model="candVisible" append-to-body
               :title="`候选知识点 · ${candFile?.name || ''}`" width="720px">
      <div v-loading="candLoading" class="cand-list">
        <p v-if="!candItems.length && !candLoading" class="cand-empty">
          暂无候选。文件解析完成后会自动生成。
        </p>
        <div v-for="c in candItems" :key="c.id" class="cand-item">
          <div class="cand-head">
            <strong>{{ c.entity }}</strong>
            <span class="cand-score">判定 {{ (c.score || 0).toFixed(2) }}</span>
            <span class="cand-decision" :class="c.decision">{{ c.decision }}</span>
          </div>
          <p class="cand-desc">{{ c.description || '（无描述）' }}</p>

          <!-- 判定时的联网来源：直接可点 -->
          <div v-if="c.sources && c.sources.length" class="cand-sources">
            <span class="cand-label">判断来源</span>
            <a v-for="(s, i) in c.sources" :key="i" :href="s.url" target="_blank"
               rel="noopener" class="cand-link" :title="s.title">{{ hostOf(s.url) }}{{ s.tier === 'authority' ? ' ·权威' : '' }}</a>
          </div>

          <!-- 更多来源与视频：按需展开 -->
          <div v-if="c._extra" class="cand-extra">
            <div v-if="c._extra.references && c._extra.references.length" class="cand-sources">
              <span class="cand-label">权威入口</span>
              <a v-for="(r, i) in c._extra.references" :key="'r' + i" :href="r.url"
                 target="_blank" rel="noopener" class="cand-link">{{ r.title }}</a>
            </div>
            <div v-if="c._extra.videos && c._extra.videos.length" class="cand-sources">
              <span class="cand-label">视频讲解</span>
              <a v-for="(v, i) in c._extra.videos" :key="'v' + i" :href="v.url"
                 target="_blank" rel="noopener" class="cand-link">{{ v.title }}</a>
            </div>
            <div v-if="c._extra.video_search && c._extra.video_search.length" class="cand-sources">
              <span class="cand-label">视频搜索</span>
              <a v-for="(v, i) in c._extra.video_search" :key="'s' + i" :href="v.url"
                 target="_blank" rel="noopener" class="cand-link">{{ v.site }}</a>
            </div>
            <div v-if="c._extra.reading && c._extra.reading.length" class="cand-sources">
              <span class="cand-label">延伸阅读</span>
              <a v-for="(r, i) in c._extra.reading" :key="'rd' + i" :href="r.url"
                 target="_blank" rel="noopener" class="cand-link" :title="r.title">
                {{ r.title_zh || r.title }}
              </a>
            </div>
            <p v-if="c._extra.message" class="cand-msg">{{ c._extra.message }}</p>
          </div>

          <div class="cand-actions">
            <el-button v-if="!c._extra" size="small" :loading="c._loading"
                       @click="loadExtra(c)">更多来源 / 视频</el-button>
            <el-button size="small" type="primary" @click="decide(c, 'accept')">采纳</el-button>
            <el-button size="small" @click="decide(c, 'reject')">驳回</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { scoreColor } from '@/utils/palette'
import { ref, computed, watch, onUnmounted } from 'vue'
import { useNoteStore } from '@/store/noteStore'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'
import FolderWorkspacePanel from './FolderWorkspacePanel.vue'
import { getLevelColor } from '@/utils/mdParser'
import { formatAgo } from '@/utils/format'
import { fileAPI, knowledgeAPI } from '@/api'
import { ElMessage } from 'element-plus'

/** 链接显示成域名，比整段标题更适合放在一行 */
function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

const candVisible = ref(false)
const candLoading = ref(false)
const candItems = ref([])
const candFile = ref(null)

/** 文件是否还在处理（解析中，或大文件的后台补齐） */
function isBusy(file) {
  return file.status === 'parsing' || /后台计算/.test(file.parseNote || '')
}

/** 打开自己文件的候选列表（后端按会话校验归属） */
async function openCandidates(file) {
  candFile.value = file
  candVisible.value = true
  candLoading.value = true
  try {
    const data = await fileAPI.candidates(file.id)
    candItems.value = data.items || []
  } catch (err) {
    candItems.value = []
    ElMessage.error(err.fullMessage || err.message || '候选加载失败')
  } finally {
    candLoading.value = false
  }
}

/** 展开该知识点的更多来源与视频讲解（按需请求，不拖慢解析） */
async function loadExtra(cand) {
  cand._loading = true
  try {
    cand._extra = await knowledgeAPI.sources(cand.entity)
  } catch (err) {
    cand._extra = { message: err.fullMessage || err.message || '来源加载失败' }
  } finally {
    cand._loading = false
  }
}

/** 采纳或驳回：只改自己的候选状态，不入公共知识库 */
async function decide(cand, action) {
  try {
    await fileAPI.verdict(candFile.value.id, cand.id, action)
    cand.decision = action
    cand.status = action === 'accept' ? 'accepted' : action === 'reject' ? 'rejected' : 'open'
    ElMessage.success(action === 'accept' ? '已采纳' : '已驳回')
  } catch (err) {
    ElMessage.error(err.fullMessage || err.message || '操作失败')
  }
}

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

// 有文件在处理时轮询列表：后台补齐完成后统计自动更新，不用手动刷新页面。
// 放在文件 store 初始化之后，避免 setup 期引用未初始化的变量。
const busyCount = computed(() =>
  (fileStore.uploadedFiles || []).filter(f => isBusy(f)).length)

let pollTimer = null
watch(busyCount, (n) => {
  if (n > 0 && !pollTimer) {
    pollTimer = setInterval(async () => {
      await fileStore.refreshList()
      if (busyCount.value === 0) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }, 4000)
  }
}, { immediate: true })

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
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

.wbl-item-actions { display: flex; justify-content: flex-end; margin-top: 4px; }
.wbl-item-note {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin: 4px 0 0; font-size: 11px; line-height: 1.5;
  color: var(--text-muted);
}
.wbl-item-note.is-busy { color: var(--accent, #1677ff); }
.wbl-cand-link {
  border: 0; background: transparent; padding: 0; cursor: pointer;
  color: var(--accent, #1677ff); font-size: 12px;
}
.cand-list { max-height: 60vh; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.cand-empty { padding: 24px; text-align: center; color: var(--text-secondary); }
.cand-item { padding: 12px; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; }
.cand-head { display: flex; align-items: center; gap: 10px; }
.cand-score { color: var(--text-secondary); font-size: 12px; }
.cand-decision { padding: 1px 6px; border-radius: 4px; font-size: 12px; background: rgba(0, 0, 0, 0.06); }
.cand-decision.accept { color: #0a7d32; background: rgba(10, 125, 50, 0.12); }
.cand-decision.reject { color: #b8362a; background: rgba(184, 54, 42, 0.12); }
.cand-desc { margin: 6px 0; color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.cand-actions { display: flex; justify-content: flex-end; gap: 8px; }
.cand-sources { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; }
.cand-label { font-size: 12px; color: var(--text-muted); }
.cand-link {
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 12px; color: var(--accent, #1677ff); text-decoration: none;
}
.cand-link:hover { text-decoration: underline; }
.cand-extra { display: flex; flex-direction: column; gap: 2px; }
.cand-msg { margin: 4px 0 0; font-size: 12px; color: var(--text-secondary); }
</style>