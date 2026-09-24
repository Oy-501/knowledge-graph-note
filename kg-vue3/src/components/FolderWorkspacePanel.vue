<template>
  <div class="fws-panel">
    <div v-if="!folder.supported" class="fws-unsupported">
      <div class="fws-us-icon">🗂</div>
      <p>当前浏览器不支持「本地文件夹工作区」</p>
      <p class="fws-us-sub">本地文件夹笔记需要 File System Access API，请使用最新版 <b>Chrome / Edge</b>，并在 <b>https 或 localhost</b> 环境下打开本应用。</p>
      <button type="button" class="fws-btn" @click="$emit('focus-online')">改用在线笔记</button>
    </div>
    <div v-else-if="folder.workspaceCount === 0" class="fws-empty">
      <div class="fws-empty-icon">🗂️</div>
      <p class="fws-empty-title">把本地文件夹当知识工作区</p>
      <p class="fws-empty-sub">选择任意含 Markdown 笔记的文件夹，系统会：读取本地 <code>.md</code> 为权威数据源、自动写入 <code>.kg_meta/kg.json</code> 元数据、并在右侧编辑器直接编辑。</p>
      <button type="button" class="fws-btn fws-btn-primary" :disabled="folder.loading" @click="onPick">{{ folder.loading ? '加载中…' : '📂 打开本地文件夹' }}</button>
    </div>
    <template v-else>
      <div class="fws-header">
        <div class="fws-header-row">
          <select v-if="folder.workspaceCount > 1" class="fws-ws-select" :value="folder.currentWorkspaceId" title="切换工作区" @change="onSwitchWs">
            <option v-for="ws in folder.workspaces" :key="ws.id" :value="ws.id">{{ ws.rootName }}</option>
          </select>
          <span v-else class="fws-ws-name" :title="folder.currentWorkspace?.rootName">🗂 {{ folder.currentWorkspace?.rootName }}</span>
          <div class="fws-header-ops">
            <button type="button" class="fws-icon-btn" title="重扫目录" :disabled="folder.loading" @click="onRescan">↻</button>
            <button type="button" class="fws-icon-btn" title="移除该工作区（不影响磁盘文件）" @click="onRemoveWs">✕</button>
          </div>
        </div>
        <div v-if="folder.currentOpenNote" class="fws-open-status" :class="'fws-os-' + saveStateKey">
          <span class="fws-os-dot"></span><span class="fws-os-text">{{ saveStateText }}</span>
          <span v-if="folder.isDirty" class="fws-os-hint">（约 1 秒后自动保存）</span>
          <span v-if="syncBadgeText" class="fws-sync-badge" :class="'fws-sync-' + syncBadgeKey" :title="syncBadgeTitle">{{ syncBadgeText }}</span>
          <button type="button" class="fws-os-close" title="关闭当前文件（已保存内容保留）" @click="onCloseNote">✕</button>
        </div>
        <div class="fws-actions">
          <button type="button" class="fws-btn fws-btn-small fws-btn-primary" :disabled="folder.loading" @click="onNewNote">📄 新建笔记</button>
          <span v-if="scanCountText" class="fws-scan-report" :title="folder.lastScanReport?.missing.map(m => m.relPath).join('\n') || ''">{{ scanCountText }}</span>
        </div>
      </div>
      <div v-if="folder.loading" class="fws-loading">扫描目录中…</div>
      <div v-else-if="treeRows.length === 0" class="fws-tree-empty">目录内暂无 Markdown 笔记，点击「新建笔记」开始</div>
      <div v-else class="fws-tree" @scroll.passive>
        <div v-for="row in treeRows" :key="row.relPath" class="fws-row" :class="[row.kind, { 'fws-row-active': isRowActive(row) }]" :style="{ paddingLeft: 6 + row.depth * 14 + 'px' }" @click="row.kind === 'dir' ? onToggleDir(row) : emitOpen(row.relPath)">
          <template v-if="row.kind === 'dir'">
            <span class="fws-chevron" @click.stop="onToggleDir(row)">{{ isDirOpen(row) ? '▾' : '▸' }}</span>
            <span class="fws-row-icon">📁</span><span class="fws-row-name">{{ row.name }}</span><span class="fws-dir-count">{{ row.fileCount }}</span>
            <span class="fws-row-ops" @click.stop><button type="button" class="fws-op" title="重命名目录" @click="onRenameDir(row)">✎</button></span>
          </template>
          <template v-else>
            <span class="fws-chevron fws-chevron-empty"></span>
            <span class="fws-row-icon">{{ rowDirty(row) ? '📝' : '📄' }}</span>
            <span class="fws-row-name" :title="row.relPath">{{ row.name }}<span v-if="rowDirty(row)" class="fws-dirty-dot" title="有未保存修改"></span></span>
            <span class="fws-row-ops" @click.stop>
              <button type="button" class="fws-op" title="重命名" @click="onRenameFile(row)">✎</button>
              <button type="button" class="fws-op fws-op-danger" title="删除（知识点保留）" @click="onDeleteFile(row)">🗑</button>
            </span>
          </template>
        </div>
        <div v-if="treeTruncated" class="fws-tree-more">… 其余条目已省略</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFolderStore } from '@/store/folderStore'
import { renameEntry } from '@/utils/folderFs'

const emit = defineEmits(['select-folder-note', 'focus-online'])
const folder = useFolderStore()
const MAX_ROWS = 300
const expanded = reactive(new Set())
const treeRows = computed(() => {
  const rows = []
  const dirFileCount = node => { let c = 0; const walk = n => { for (const ch of n.children || []) { if (ch.kind === 'dir') walk(ch); else c += 1 } }; walk(node); return c }
  const walk = (node, depth) => {
    if (rows.length >= MAX_ROWS) return
    for (const child of node?.children || []) {
      if (rows.length >= MAX_ROWS) return
      if (child.kind === 'dir') { rows.push({ type: 'dir', kind: 'dir', relPath: child.relPath, name: child.name, depth, fileCount: dirFileCount(child) }); if (expanded.has(child.relPath)) walk(child, depth + 1) }
      else rows.push({ type: 'file', kind: 'file', relPath: child.relPath, name: child.name, depth })
    }
  }
  walk(folder.tree, 0)
  return rows
})
const treeTruncated = computed(() => {
  let count = 0
  const countWalk = node => { for (const child of node?.children || []) { if (count >= MAX_ROWS) return true; count += 1; if (child.kind === 'dir' && expanded.has(child.relPath)) { if (countWalk(child)) return true } } return false }
  return countWalk(folder.tree)
})
const isDirOpen = row => expanded.has(row.relPath)
function onToggleDir(row) { if (expanded.has(row.relPath)) expanded.delete(row.relPath); else expanded.add(row.relPath) }
const openRelPath = computed(() => folder.currentOpenNote?.relPath || null)
function isRowActive(row) { return row.kind === 'file' && row.relPath === openRelPath.value }
function rowDirty(row) { return row.relPath === openRelPath.value && folder.saveState === 'dirty' }
const saveStateKey = computed(() => folder.saveState)
const saveStateText = computed(() => ({ clean: '已保存', dirty: '未保存', saving: '保存中…', error: '保存出错' }[folder.saveState] || ''))
const syncBadgeKey = computed(() => { const n = folder.currentOpenNote; if (!n) return ''; if (n.syncError) return 'err'; return n.backendFileId ? 'ok' : 'none' })
const syncBadgeText = computed(() => { const n = folder.currentOpenNote; if (!n) return ''; if (n.syncError) return '⚠ 知识库同步失败'; return n.backendFileId ? '🗄 已入库' : '☁ 首次保存入库' })
const syncBadgeTitle = computed(() => { const n = folder.currentOpenNote; if (!n) return ''; if (n.syncError) return '后端不可达，保存仍成功；后端恢复后再次保存将自动重试。' + (n.syncError || ''); if (n.backendFileId) return '内容已双写知识库；删除此笔记时知识节点保留'; return '离线可用；首次保存将把本文档登记入知识库并抽取知识节点' })
const scanCountText = computed(() => { const rep = folder.lastScanReport; if (!rep) return ''; const n = (rep.added?.length || 0); return n > 0 ? `发现 ${n} 个未登记文件` : '' })
async function onPick() {
  const r = await folder.pickWorkspace()
  if (r?.ok) { expanded.clear(); ElMessage.success(r.reused ? `已重新打开工作区「${r.workspace.rootName}」` : `已打开工作区「${r.workspace.rootName}」`) }
  else if (r?.msg && r.msg !== '已取消选择') ElMessage.warning(r.msg)
}
async function onSwitchWs(ev) {
  const r = await folder.switchWorkspace(ev.target.value)
  if (r?.ok) { expanded.clear(); ElMessage.success('已切换工作区') }
  else ElMessage.warning(r?.msg || '切换失败')
}
async function onRescan() {
  const r = await folder.rescan()
  if (r?.ok) { expanded.clear(); if ((r.added?.length || 0) === 0 && (r.missing?.length || 0) === 0) ElMessage.success('目录已是最新') }
  else ElMessage.warning(r?.msg || '重扫失败')
}
function onRemoveWs() {
  const ws = folder.currentWorkspace
  if (!ws) return
  ElMessageBox.confirm(`从本应用移除工作区「${ws.rootName}」？`, '移除工作区', { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' }).then(async () => {
    await folder.removeWorkspace(ws.id)
    ElMessage.success('已移除（磁盘文件不受影响）')
  }).catch(() => {})
}
async function onNewNote() {
  let name = ''
  try {
    const { value } = await ElMessageBox.prompt('笔记标题（作为文件名）', '新建本地笔记', { inputValue: '', inputPlaceholder: '未命名笔记', confirmButtonText: '创建', cancelButtonText: '取消' })
    name = (value || '').trim()
  } catch (e) { return }
  const r = await folder.createNote('', name)
  if (r?.ok) { ElMessage.success('已创建本地笔记'); emitOpen(r.relPath) }
  else ElMessage.warning(r?.msg || '创建失败')
}
async function onRenameFile(row) {
  try {
    const { value } = await ElMessageBox.prompt('输入新文件名（含扩展名）', '重命名笔记', { inputValue: row.name, confirmButtonText: '重命名', cancelButtonText: '取消' })
    if (!value || value.trim() === row.name) return
    const r = await folder.renameNote(row.relPath, value.trim())
    if (r?.ok) { ElMessage.success('已重命名'); if (r.relPath !== row.relPath) emitOpen(r.relPath) }
    else ElMessage.warning(r?.msg || '重命名失败')
  } catch (e) { /* 取消 */ }
}
async function onDeleteFile(row) {
  ElMessageBox.confirm(`删除笔记「${row.name}」？\n将删除本地文件；若已入库，知识节点会保留（彻底删除请在后续模块操作）。`, '删除笔记', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }).then(async () => {
    const r = await folder.deleteNote(row.relPath)
    if (r?.ok) ElMessage.success('已删除（知识节点保留）')
    else ElMessage.warning(r?.msg || '删除失败')
  }).catch(() => {})
}
async function onRenameDir(row) {
  try {
    const { value } = await ElMessageBox.prompt('输入新目录名', '重命名目录', { inputValue: row.name, confirmButtonText: '重命名', cancelButtonText: '取消' })
    if (!value || value.trim() === row.name) return
    const ws = folder.currentWorkspace
    if (!ws) return
    const newRel = await renameEntry(ws.handle, row.relPath, value.trim(), 'directory')
    expanded.delete(row.relPath)
    expanded.add(newRel)
    await folder.rescan()
    ElMessage.success('目录已重命名')
  } catch (e) { if (e?.message) ElMessage.warning('重命名失败：' + e.message) }
}
async function onCloseNote() {
  const r = await folder.saveNote()
  if (r?.ok === false && r.msg && r.msg !== '没有打开的笔记') ElMessage.warning(r.msg)
  folder.currentOpenNote = null
  folder.saveState = 'clean'
}
function emitOpen(relPath) { setTimeout(() => emit('select-folder-note', relPath), 0) }
onMounted(async () => {
  if (folder.supported && folder.workspaceCount === 0 && !folder.currentWorkspaceId) await folder.init()
  if (folder.openNote?.relPath) {
    const dirs = folder.openNote.relPath.split('/').slice(0, -1)
    let acc = ''
    for (const d of dirs) { acc = acc ? acc + '/' + d : d; expanded.add(acc) }
  }
})
</script>

<style scoped>
.fws-panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.fws-empty, .fws-unsupported { display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 24px 16px; gap: 6px; height: 100%; }
.fws-empty-icon, .fws-us-icon { display: flex; align-items: center; justify-content: center; width: 60px; height: 60px; font-size: 26px; background: var(--accent-soft); border-radius: var(--radius-full); margin-bottom: 8px; }
.fws-empty-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin: 0; }
.fws-empty-sub, .fws-us-sub { font-size: 11px; color: var(--text-muted); line-height: 1.6; margin: 0; max-width: 240px; }
.fws-empty-sub code, .fws-us-sub code { background: var(--bg-tertiary); padding: 1px 4px; border-radius: 3px; font-size: 10px; }
.fws-btn { margin-top: 10px; padding: 6px 16px; border: 1px solid var(--border-light); background: var(--bg-secondary); color: var(--text-secondary); border-radius: var(--radius-full); font-size: 12px; cursor: pointer; transition: all var(--dur-fast) var(--ease-out); }
.fws-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent); }
.fws-btn:active:not(:disabled) { transform: scale(0.96); }
.fws-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.fws-btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); box-shadow: var(--shadow-sm); }
.fws-btn-primary:hover:not(:disabled) { background: var(--accent-strong); border-color: var(--accent-strong); color: #fff; transform: translateY(-1px); box-shadow: var(--shadow-md); }
.fws-btn-small { margin: 0; padding: 3px 12px; font-size: 11px; }
.fws-header { padding: 8px 8px 6px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.fws-header-row { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.fws-ws-select { flex: 1; min-width: 0; padding: 3px 8px; font-size: 12px; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius-sm); color: var(--text-primary); outline: none; max-width: 150px; transition: border-color var(--dur-fast) var(--ease-out); }
.fws-ws-select:focus { border-color: var(--accent); }
.fws-ws-name { flex: 1; min-width: 0; font-size: 12px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fws-header-ops { display: flex; gap: 2px; flex-shrink: 0; }
.fws-icon-btn { border: none; background: transparent; color: var(--text-muted); font-size: 13px; cursor: pointer; padding: 2px 5px; border-radius: var(--radius-sm); line-height: 1; transition: all var(--dur-fast) var(--ease-out); }
.fws-icon-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.fws-icon-btn:active:not(:disabled) { transform: scale(0.92); }
.fws-open-status { display: flex; align-items: center; gap: 5px; margin-top: 6px; padding: 4px 10px; background: var(--bg-secondary); border: 1px solid var(--border-light); border-radius: var(--radius-full); font-size: 10px; }
.fws-os-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.fws-os-clean .fws-os-dot { background: var(--success, #4caf50); }
.fws-os-dirty .fws-os-dot { background: var(--warning, #e8a020); }
.fws-os-saving .fws-os-dot { background: var(--warning, #e8a020); animation: fws-blink 0.8s infinite; }
.fws-os-error .fws-os-dot { background: var(--danger, #e84c4c); }
.fws-os-text { color: var(--text-secondary); }
.fws-os-hint { color: var(--text-muted); }
.fws-os-close { margin-left: auto; border: none; background: none; color: var(--text-muted); cursor: pointer; font-size: 10px; padding: 0 2px; }
.fws-os-close:hover { color: var(--text-primary); }
@keyframes fws-blink { 50% { opacity: 0.3; } }
.fws-sync-badge { flex-shrink: 0; padding: 1px 6px; border-radius: 8px; font-size: 9px; border: 1px solid transparent; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fws-sync-ok { color: var(--success, #4caf50); border-color: color-mix(in srgb, var(--success, #4caf50) 35%, transparent); background: color-mix(in srgb, var(--success, #4caf50) 12%, transparent); }
.fws-sync-none { color: var(--text-muted); border-color: color-mix(in srgb, var(--text-muted) 30%, transparent); background: color-mix(in srgb, var(--text-muted) 8%, transparent); }
.fws-sync-err { color: var(--danger, #e84c4c); border-color: color-mix(in srgb, var(--danger, #e84c4c) 35%, transparent); background: color-mix(in srgb, var(--danger, #e84c4c) 10%, transparent); }
.fws-actions { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
.fws-scan-report { font-size: 10px; color: var(--warning, #e8a020); }
.fws-loading, .fws-tree-empty { text-align: center; color: var(--text-muted); font-size: 11px; padding: 24px 12px; }
.fws-tree { flex: 1; overflow-y: auto; padding: 4px 0; }
.fws-row { display: flex; align-items: center; gap: 3px; height: 26px; padding-right: 8px; border-radius: var(--radius-sm); border: 1px solid transparent; cursor: pointer; font-size: 12px; color: var(--text-secondary); transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out); margin: 0 4px; }
.fws-row:hover { background: var(--bg-hover); }
.fws-row:active { transform: scale(0.98); }
.fws-row-active { background: var(--accent-soft); color: var(--accent-strong); font-weight: 500; border-color: color-mix(in srgb, var(--accent) 22%, transparent); }
.fws-chevron { width: 14px; flex-shrink: 0; font-size: 9px; color: var(--text-muted); text-align: center; }
.fws-chevron-empty { visibility: hidden; }
.fws-row-icon { flex-shrink: 0; font-size: 11px; }
.fws-row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fws-dir-count { font-size: 9px; color: var(--text-secondary); background: var(--bg-tertiary); padding: 0 6px; border-radius: var(--radius-full); flex-shrink: 0; font-family: var(--font-mono); }
.fws-row-ops { display: none; gap: 1px; flex-shrink: 0; }
.fws-row:hover .fws-row-ops { display: flex; }
.fws-op { border: none; background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; padding: 1px 4px; border-radius: 3px; line-height: 1; }
.fws-op:hover { background: var(--bg-secondary); color: var(--text-primary); }
.fws-op-danger:hover { color: var(--danger, #e84c4c); }
.fws-dirty-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--warning, #e8a020); margin-left: 4px; vertical-align: middle; }
.fws-tree-more { text-align: center; color: var(--text-muted); font-size: 10px; padding: 8px; }
</style>
