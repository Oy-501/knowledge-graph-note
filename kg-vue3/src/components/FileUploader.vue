<template>
  <div class="panel-section">
    <h3>文件上传 <span class="count">{{ fileStore.uploadedFiles.length }}</span></h3>
    <div
      class="dropzone"
      :class="{ dragover: isDragging }"
      @click="triggerPick"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <div class="dz-icon">📄</div>
      <div class="dz-text">拖拽 .md / .txt / .csv 到此处，或点击选择</div>
      <div class="dz-text" style="opacity:0.7">支持多选批量上传</div>
      <div class="dz-limit">
        单文件 ≤ {{ fileStore.maxUploadMB }}MB · 超过 {{ fileStore.splitTargetLines }} 行会自动切割解析（内容不丢）· 仅纯文本
      </div>
      <input
        ref="inputRef"
        type="file"
        multiple
        accept=".md,.markdown,.txt,.csv,.tsv,.json,.log,text/*"
        hidden
        @change="onInputChange"
      />
    </div>
  </div>

  <div class="panel-section" v-if="fileStore.uploadedFiles.length">
    <h3>文件列表 <span class="count">{{ fileStore.indexedCount }} 已索引</span></h3>
    <div class="file-list">
      <div
        v-for="f in fileStore.uploadedFiles"
        :key="f.id"
        class="file-item"
      >
        <span class="fi-name" :title="f.name">{{ f.name }}</span>
        <span class="fi-badge" v-if="f.status === 'indexed'">已索引 · {{ f.kpCount }}</span>
        <span
          class="fi-badge"
          v-else-if="f.status === 'parsing'"
          style="background:var(--warning-soft);color:var(--warning);border-color:transparent"
        >解析中</span>
        <span
          class="fi-badge"
          v-else-if="f.status === 'failed'"
          style="background:var(--danger-soft);color:var(--danger);border-color:transparent"
        >失败</span>
        <span
          v-if="f.parseNote"
          class="fi-note"
          :title="f.parseNote"
        >⚠ 已截断</span>
        <button type="button" class="fi-del" title="删除" @click="onDelete(f)">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'
import { fileAPI } from '@/api/index'

const fileStore = useFileStore()
const graphStore = useGraphStore()
const inputRef = ref(null)
const isDragging = ref(false)

// 上传上限以后端为准（提示文案与拦截阈值保持一致）
onMounted(async () => {
  try {
    const limits = await fileAPI.limits()
    if (limits?.max_upload_mb) fileStore.maxUploadMB = limits.max_upload_mb
    if (limits?.split_target_lines) fileStore.splitTargetLines = limits.split_target_lines
  } catch (e) {
    /* 后端不可用时沿用默认值 20MB */
  }
})

function triggerPick() {
  inputRef.value?.click()
}

function onInputChange(e) {
  handleFiles(e.target.files)
  e.target.value = '' // 重置以支持重复选同一文件
}

function onDragOver() { isDragging.value = true }
function onDragLeave() { isDragging.value = false }
function onDrop(e) {
  isDragging.value = false
  handleFiles(e.dataTransfer.files)
}

async function handleFiles(files) {
  if (!files || files.length === 0) {
    ElMessage.warning('未选择文件')
    return
  }
  // 体积/类型校验在 store 内完成（阈值取自后端），避免"先说开始上传、再被拒绝"的误导
  const res = await fileStore.uploadFiles(Array.from(files))
  if (res.ok > 0) {
    ElMessage.success(res.msg)
  } else if (res.msg) {
    ElMessage.error(res.msg)
  }
}

async function onDelete(f) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${f.name}」？将同步清除该文件所有节点、连线与缓存，操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch { return }

  ElMessage.info('正在删除...')
  const res = await fileStore.deleteFile(f.id)
  if (res.ok) {
    ElMessage.success('已彻底删除：节点 / 连线 / DOM / 缓存 已全部清除')
  } else {
    ElMessage.error('删除失败：' + (res.msg || ''))
  }
}
</script>

<style scoped>
/* ============================================================
   文件上传区视觉统一（亮/暗双主题自适应，scoped 不泄漏）
   ============================================================ */

/* 1) 区块小标题：与主面板一致的弱色细分隔 */
.panel-section h3 {
  letter-spacing: 0.8px;
  padding-bottom: 7px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-light);
}
.panel-section h3 .count {
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-family: var(--font-mono);
  font-weight: 600;
  padding: 1px 8px;
}

/* 2) 拖拽上传区：accent 虚线卡片，悬浮/拖入高亮 */
.dropzone {
  position: relative;
  border: 1.5px dashed var(--accent);
  border-radius: var(--radius);
  background:
    radial-gradient(120% 90% at 50% 0%, var(--accent-soft) 0%, transparent 70%),
    var(--bg-secondary);
  box-shadow: var(--shadow-sm);
  padding: 20px 16px;
  transition: border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}
.dropzone:hover,
.dropzone.dragover {
  border-color: var(--accent);
  background: var(--accent-soft);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.dropzone .dz-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  background: var(--bg-secondary);
  border-radius: 14px;
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur-fast) var(--ease-out);
}
.dropzone:hover .dz-icon,
.dropzone.dragover .dz-icon {
  transform: translateY(-2px) scale(1.06);
}
.dropzone .dz-text { font-weight: 500; }

/* 3) 文件列表项：胶囊状态徽章 + hover 上浮 + 删除反馈 */
.file-list { gap: 7px; }
.file-item {
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: 8px 10px;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast),
    transform var(--dur-fast) var(--ease-out);
}
.file-item:hover {
  background: var(--bg-secondary);
  border-color: var(--accent);
  box-shadow: var(--shadow-card);
  transform: translateY(-1px);
}
.file-item .fi-name { font-weight: 500; }
.file-item .fi-badge {
  border-radius: var(--radius-full);
  background: var(--success-soft);
  color: var(--success);
  border: 1px solid transparent;
  font-family: var(--font-mono);
  font-weight: 600;
  padding: 1px 8px;
}
.file-item .fi-del {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transition: opacity var(--dur-fast), background-color var(--dur-fast),
    color var(--dur-fast);
}
.file-item .fi-del:hover {
  opacity: 1;
  color: var(--danger);
  background: var(--danger-soft);
}
</style>

<style scoped>
/* 上传上限提示：弱化但可见，让用户在投喂大文件前就知道边界 */
.dz-limit {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
/* 解析备注（如：文件过大已截断） */
.fi-note {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--warning-soft);
  color: var(--warning);
  cursor: help;
  white-space: nowrap;
}
</style>
