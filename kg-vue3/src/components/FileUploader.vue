<template>
  <div class="panel-section">
    <h3>文件上传 <span class="count">{{ fileStore.uploadedFiles.length }}</span></h3>
    <div class="dropzone" :class="{ dragover: isDragging }" @click="triggerPick" @dragover.prevent="onDragOver" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
      <div class="dz-icon">📄</div>
      <div class="dz-text">拖拽 .md / .txt 到此处，或点击选择</div>
      <div class="dz-text" style="opacity:0.7">支持多选批量上传</div>
      <input ref="inputRef" type="file" multiple accept=".md,.markdown,.txt,text/*" hidden @change="onInputChange" />
    </div>
  </div>

  <div class="panel-section" v-if="fileStore.uploadedFiles.length">
    <h3>文件列表 <span class="count">{{ fileStore.indexedCount }} 已索引</span></h3>
    <div class="file-list">
      <div v-for="f in fileStore.uploadedFiles" :key="f.id" class="file-item">
        <span class="fi-name" :title="f.name">{{ f.name }}</span>
        <span class="fi-badge" v-if="f.status === 'indexed'">已索引 · {{ f.kpCount }}</span>
        <span class="fi-badge" v-else-if="f.status === 'parsing'" style="background:var(--warning-soft);color:var(--warning);border-color:transparent">解析中</span>
        <span class="fi-badge" v-else-if="f.status === 'failed'" style="background:var(--danger-soft);color:var(--danger);border-color:transparent">失败</span>
        <button type="button" class="fi-del" title="删除" @click="onDelete(f)">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'

const fileStore = useFileStore(); const graphStore = useGraphStore()
const inputRef = ref(null); const isDragging = ref(false)
function triggerPick() { inputRef.value?.click() }
function onInputChange(e) { handleFiles(e.target.files); e.target.value = '' }
function onDragOver() { isDragging.value = true }
function onDragLeave() { isDragging.value = false }
function onDrop(e) { isDragging.value = false; handleFiles(e.dataTransfer.files) }
async function handleFiles(files) {
  if (!files || files.length === 0) { ElMessage.warning('未选择文件'); return }
  const valid = Array.from(files).filter(f => /\.(md|txt|markdown)$/i.test(f.name) || (f.type && f.type.startsWith('text')))
  if (valid.length === 0) { ElMessage.warning('只支持 .md / .txt 文本文件'); return }
  ElMessage.info('开始上传 ' + valid.length + ' 个文件...')
  const res = await fileStore.uploadFiles(valid)
  if (res.ok > 0) ElMessage.success(res.msg)
  else ElMessage.error(res.msg || '上传失败')
}
async function onDelete(f) {
  try { await ElMessageBox.confirm(`确认删除「${f.name}」？将同步清除该文件所有节点、连线与缓存，操作不可撤销。`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }) } catch { return }
  ElMessage.info('正在删除...')
  const res = await fileStore.deleteFile(f.id)
  if (res.ok) ElMessage.success('已彻底删除：节点 / 连线 / DOM / 缓存 已全部清除')
  else ElMessage.error('删除失败：' + (res.msg || ''))
}
</script>

<style scoped>
.panel-section h3 { letter-spacing: 0.8px; padding-bottom: 7px; margin-bottom: 10px; border-bottom: 1px solid var(--border-light); }
.panel-section h3 .count { background: var(--accent-soft); color: var(--accent-strong); font-family: var(--font-mono); font-weight: 600; padding: 1px 8px; }
.dropzone { position: relative; border: 1.5px dashed var(--accent); border-radius: var(--radius); background: radial-gradient(120% 90% at 50% 0%, var(--accent-soft) 0%, transparent 70%), var(--bg-secondary); box-shadow: var(--shadow-sm); padding: 20px 16px; transition: border-color var(--dur-fast) var(--ease-out), background-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out); }
.dropzone:hover, .dropzone.dragover { border-color: var(--accent); background: var(--accent-soft); box-shadow: var(--shadow-md); transform: translateY(-1px); }
.dropzone .dz-icon { width: 48px; height: 48px; margin: 0 auto 10px; display: flex; align-items: center; justify-content: center; font-size: 26px; background: var(--bg-secondary); border-radius: 14px; box-shadow: var(--shadow-sm); transition: transform var(--dur-fast) var(--ease-out); }
.dropzone:hover .dz-icon, .dropzone.dragover .dz-icon { transform: translateY(-2px) scale(1.06); }
.dropzone .dz-text { font-weight: 500; }
.file-list { gap: 7px; }
.file-item { border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 8px 10px; transition: border-color var(--dur-fast), box-shadow var(--dur-fast), transform var(--dur-fast) var(--ease-out); }
.file-item:hover { background: var(--bg-secondary); border-color: var(--accent); box-shadow: var(--shadow-card); transform: translateY(-1px); }
.file-item .fi-name { font-weight: 500; }
.file-item .fi-badge { border-radius: var(--radius-full); background: var(--success-soft); color: var(--success); border: 1px solid transparent; font-family: var(--font-mono); font-weight: 600; padding: 1px 8px; }
.file-item .fi-del { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); transition: opacity var(--dur-fast), background-color var(--dur-fast), color var(--dur-fast); }
.file-item .fi-del:hover { opacity: 1; color: var(--danger); background: var(--danger-soft); }
</style>
