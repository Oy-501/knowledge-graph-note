<template>
  <div ref="wbRoot" class="kw-workbench" :class="{ 'kw-fullscreen': isFullscreen }" :style="backgroundStyle">
    <div v-if="hasBackground" class="kw-bg-layer" :style="bgOverlayStyle"></div>
    <aside v-if="!isFullscreen" class="kw-left">
      <WorkbenchLeftPanel
        :current-note-id="noteStore.currentNoteId"
        @select-note="onSelectNote"
        @new-note="onNewNote"
        @open-note-manage="onOpenNoteManage"
        @select-folder-note="onSelectFolderNote"
      />
    </aside>
    <main class="kw-center">
      <NoteManageView v-if="showNoteManage && !isFullscreen" @edit-note="onEditNoteFromManage" @new-note="onNewNote" @close="showNoteManage = false" />
      <WorkbenchEditor
        v-show="!showNoteManage || isFullscreen"
        ref="editorRef"
        :title="editorTitle"
        :content="editorContent"
        :tags="editorTags"
        :matched-terms="matchedTerms"
        :is-fullscreen="isFullscreen"
        :linked-node-ids="linkedNodeIds"
        :mode-tag="editorSourceLabel"
        :mode-state="editorSaveState"
        :lib-state="editorLibState"
        @update:title="onTitleChange"
        @update:content="onContentInput"
        @update:tags="onTagsChange"
        @content-change="onContentChange"
        @associate-selection="onAssociateSelection"
        @create-node-from-selection="onCreateNodeFromSelection"
        @toggle-fullscreen="onToggleFullscreen"
        @toggle-bg="onToggleBg"
        @save-note="saveNote"
        @link-node="onLinkNodeFromEditor"
        @wikilink-sync="onWikilinkSync"
      />
      <WorkbenchMiniGraph v-if="!isFullscreen" :linked-node-ids="linkedNodeIds" :linked-file-ids="linkedFileIds" :current-note-title="editorTitle || '当前笔记'" :matched-node-ids="matchedNodeIds" @node-click="onMiniGraphNodeClick" />
    </main>
    <aside v-if="!isFullscreen" class="kw-right">
      <WorkbenchRightPanel
        ref="rightPanelRef"
        :linked-node-ids="linkedNodeIds"
        :linked-file-ids="linkedFileIds"
        :matched-nodes="matchedNodes"
        :validation-issues="validationIssues"
        :node-relations="nodeRelations"
        :recommendations="recommendations"
        @open-file="onOpenFile"
        @unlink-file="onUnlinkFile"
        @unlink-node="onUnlinkNode"
        @link-node="onLinkNode"
        @create-node="onCreateNode"
        @ignore-node="onIgnoreNode"
        @confirm-link="onConfirmLink"
        @edit-relation="onEditRelation"
        @accept-fix="onAcceptFix"
        @ignore-fix="onIgnoreFix"
      />
    </aside>
    <BackgroundSelector :visible="showBgSelector" @close="showBgSelector = false" />
    <div v-if="isFullscreen" class="kw-fullscreen-minigraph" :class="{ expanded: miniGraphExpanded }">
      <div class="kw-minigraph-toggle" @click="miniGraphExpanded = !miniGraphExpanded">
        <span>🕸️ 知识网络</span>
        <span class="kw-minigraph-arrow">{{ miniGraphExpanded ? '▼' : '▲' }}</span>
      </div>
      <div v-if="miniGraphExpanded" class="kw-minigraph-body">
        <WorkbenchMiniGraph :linked-node-ids="linkedNodeIds" :linked-file-ids="linkedFileIds" :current-note-title="editorTitle || '当前笔记'" :matched-node-ids="matchedNodeIds" @node-click="onMiniGraphNodeClick" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFullscreen } from '@vueuse/core'
import WorkbenchLeftPanel from './WorkbenchLeftPanel.vue'
import WorkbenchEditor from './WorkbenchEditor.vue'
import WorkbenchRightPanel from './WorkbenchRightPanel.vue'
import WorkbenchMiniGraph from './WorkbenchMiniGraph.vue'
import BackgroundSelector from './BackgroundSelector.vue'
import NoteManageView from './NoteManageView.vue'
import { useNoteStore } from '@/store/noteStore'
import { useGraphStore } from '@/store/graphStore'
import { useFileStore } from '@/store/fileStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useFolderStore } from '@/store/folderStore'
import { noteAPI } from '@/api'
import { extractTerms, matchGraphNodes, extractRelations } from '@/utils/noteParser'
import { validateText, preSaveValidation } from '@/utils/noteValidator'
import { recommendConnections } from '@/services/recommender'
import { debounce } from '@/utils/resilience'

const noteStore = useNoteStore()
const graphStore = useGraphStore()
const fileStore = useFileStore()
const settingsStore = useSettingsStore()
const folderStore = useFolderStore()

const editorRef = ref(null)
const rightPanelRef = ref(null)
const editMode = ref('note')
const editorTitle = ref('')
const editorContent = ref('')
const editorTags = ref([])
const isFullscreen = ref(false)
const showBgSelector = ref(false)
const showNoteManage = ref(false)
const miniGraphExpanded = ref(false)

const hasBackground = computed(() => {
  const bg = settingsStore.currentBackground
  return bg.type !== 'preset' || bg.value !== 'dark_night'
})
const backgroundStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const scope = bg.scope || 'editor'
  if (scope === 'global' || scope === 'workbench') return { '--editor-bg': settingsStore.backgroundCSS }
  return {}
})
const bgOverlayStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const scope = bg.scope || 'editor'
  if (scope === 'global' || scope === 'workbench') return { opacity: bg.opacity ?? 0.8, filter: bg.blur ? `blur(${bg.blur}px)` : 'none' }
  return {}
})

const validationIssues = ref([])
const recommendations = ref([])
const matchedTerms = ref([])
const matchedNodeIds = computed(() => matchedTerms.value.map(m => m.node.id))
const matchedNodes = computed(() => matchedTerms.value)
const linkedNodeIds = computed(() => {
  if (editMode.value !== 'note') return []
  const note = noteStore.currentNote
  return note ? note.linkedNodes || [] : []
})
const linkedFileIds = computed(() => {
  if (editMode.value !== 'note') return []
  const note = noteStore.currentNote
  return note ? note.linkedFiles || [] : []
})
const editorSourceLabel = computed(() => {
  if (editMode.value === 'folder') return folderStore.currentOpenNote ? '本地文件' : ''
  return noteStore.currentNoteId ? '在线笔记' : ''
})
const editorSaveState = computed(() => (editMode.value === 'folder' ? folderStore.saveState : 'clean'))
const editorLibState = computed(() => {
  if (editMode.value !== 'folder') return ''
  const n = folderStore.currentOpenNote
  if (!n) return ''
  if (n.syncError) return 'err'
  return n.backendFileId ? 'ok' : 'none'
})
const nodeRelations = ref({})

onMounted(async () => {
  await noteStore.loadNotes()
  if (noteStore.sortedNotes.length > 0) onSelectNote(noteStore.sortedNotes[0].id)
  folderStore.init().then(r => { if (r?.ok && r.count > 0) console.info('[workbench] 已恢复本地文件夹工作区:', r.count) })
})

function syncEditorFromNote() {
  const note = noteStore.currentNote
  if (note) {
    editorTitle.value = note.title
    editorContent.value = note.content || ''
    editorTags.value = note.tags || []
    nodeRelations.value = note._nodeRelations || {}
    ensureFullContent(note)
  }
}

async function ensureFullContent(note) {
  if (!note || note._fullLoaded) return
  note._fullLoaded = true
  if (!noteStore._backendReady) return
  const stale = note.content || ''
  try {
    const res = await noteAPI.get(note.id)
    const full = res?.note || res
    if (typeof full?.content !== 'string' || full.content === stale) return
    note.content = full.content
    if (noteStore.currentNoteId === note.id && editorContent.value === stale) editorContent.value = full.content
  } catch (e) {
    console.warn('[workbench] 拉取笔记全文失败:', e?.message)
  }
}

function syncEditorFromFolder() {
  const n = folderStore.currentOpenNote
  if (!n) { clearEditor(); return }
  editorTitle.value = n.title || ''
  editorContent.value = n.content || ''
  editorTags.value = n.tags || []
  nodeRelations.value = {}
  runMatching(editorContent.value)
}

function clearEditor() {
  editorTitle.value = ''
  editorContent.value = ''
  editorTags.value = []
  nodeRelations.value = {}
  matchedTerms.value = []
  validationIssues.value = []
  recommendations.value = []
}

async function flushDrafts() {
  if (editMode.value === 'folder') {
    if (folderStore.currentOpenNote && folderStore.saveState === 'dirty') {
      debouncedFolderSave.cancel?.()
      await folderStore.saveNote()
    }
    return
  }
  if (noteStore.currentNoteId) {
    debouncedAutoSave.cancel?.()
    await noteStore.saveNote(noteStore.currentNoteId, { title: editorTitle.value, content: editorContent.value, tags: editorTags.value, _nodeRelations: nodeRelations.value })
  }
}

watch(() => noteStore.currentNote, note => {
  if (note) { editMode.value = 'note'; syncEditorFromNote() }
  else clearEditor()
}, { immediate: true })

watch(() => folderStore.currentOpenNote, note => {
  if (editMode.value !== 'folder') return
  if (note) syncEditorFromFolder()
  else { debouncedFolderSave.cancel?.(); debouncedTitle.cancel?.(); clearEditor() }
})

async function onSelectNote(noteId) {
  showNoteManage.value = false
  if (editMode.value !== 'note' || noteStore.currentNoteId !== noteId) await flushDrafts()
  noteStore.setCurrentNote(noteId)
  editMode.value = 'note'
  syncEditorFromNote()
}

async function onSelectFolderNote(relPath) {
  showNoteManage.value = false
  if (!folderStore.currentWorkspace) return
  if (editMode.value !== 'folder') await flushDrafts()
  editMode.value = 'folder'
  const r = await folderStore.openNote(relPath)
  if (r?.ok) syncEditorFromFolder()
  else if (r?.msg) ElMessage.warning(r.msg)
}

async function onNewNote() {
  showNoteManage.value = false
  if (editMode.value === 'folder') await flushDrafts()
  await noteStore.createNote('未命名笔记', '')
  editorRef.value?.focus()
}

function onContentInput(content) {
  editorContent.value = content
  if (editMode.value === 'folder' && folderStore.currentOpenNote) folderStore.setDraft(content)
}

const debouncedTitle = debounce(() => folderStore.updateTitle(editorTitle.value), 600)
const debouncedFolderMatch = debounce(content => runMatching(content), 400)
const debouncedFolderSave = debounce(() => folderStore.saveNote(), 800)
const debouncedNoteMatch = debounce(content => { runMatching(content); debouncedAutoSave() }, 500)
const debouncedAutoSave = debounce(async () => {
  if (editMode.value !== 'note' || !noteStore.currentNoteId) return
  await noteStore.saveNote(noteStore.currentNoteId, { title: editorTitle.value, content: editorContent.value, tags: editorTags.value, _nodeRelations: nodeRelations.value })
}, 2000)

function onTitleChange(title) {
  editorTitle.value = title
  if (editMode.value === 'folder' && folderStore.currentOpenNote) debouncedTitle()
}

function onTagsChange(tags) {
  editorTags.value = tags
  if (editMode.value === 'folder' && folderStore.currentOpenNote) {
    folderStore.currentOpenNote.tags = [...tags]
    debouncedFolderSave()
  }
}

function onContentChange(content) {
  if (editMode.value === 'folder') {
    if (!folderStore.currentOpenNote) return
    debouncedFolderMatch(content)
    debouncedFolderSave()
    return
  }
  if (!noteStore.currentNoteId) return
  debouncedNoteMatch(content)
}

function runMatching(content) {
  const terms = extractTerms(content)
  const matched = matchGraphNodes(terms, graphStore.nodes)
  matchedTerms.value = matched
  const issues = validateText(content)
  validationIssues.value = issues
  recommendations.value = recommendConnections(content, editorTitle.value, graphStore.nodes, linkedNodeIds.value)
}

async function saveNote() {
  if (editMode.value === 'folder') {
    if (!folderStore.currentOpenNote) return
    debouncedFolderSave.cancel?.()
    const r = await folderStore.saveNote()
    if (r?.ok) ElMessage.success('本地笔记已保存')
    else ElMessage.warning(r?.msg || '保存失败')
    return
  }
  if (!noteStore.currentNoteId) return
  const assertions = editorContent.value.split(/[。！？\n]+/).filter(s => s.trim().length > 5)
  const result = await preSaveValidation(assertions.map(t => ({ text: t })), graphStore.nodes)
  const base = { title: editorTitle.value, content: editorContent.value, tags: editorTags.value, _nodeRelations: nodeRelations.value, validationReport: result, accuracyScore: result.summary.accuracy, verified: result.summary.accuracy >= 80 && result.errors.length === 0 }
  if (result.errors.length > 0) {
    try {
      await ElMessageBox.confirm(`笔记中存在 ${result.errors.length} 个错误，${result.warnings.length} 个警告。是否仍然保存？`, '知识校验未通过', { type: 'warning', confirmButtonText: '强制保存', cancelButtonText: '返回修改' })
    } catch (_) { return }
    await noteStore.saveNote(noteStore.currentNoteId, base)
    ElMessage.warning('已强制保存，笔记标记为待审查')
  } else {
    await noteStore.saveNote(noteStore.currentNoteId, base)
    ElMessage.success('笔记已保存')
  }
}

function requireOnlineNote(action = '该操作') {
  if (editMode.value !== 'note' || !noteStore.currentNoteId) {
    ElMessage.info(action + '需要在线笔记；本地文件的知识关联将在「导入知识库」后开放（模块1 Stage D）')
    return false
  }
  return true
}

function onAssociateSelection(text, extraData) {
  if (!requireOnlineNote('关联到知识点')) return
  if (extraData && extraData.type === 'node') { onLinkNode(extraData.id, text); return }
  if (extraData && extraData.type === 'file') { onLinkFile(extraData.id); return }
  const candidates = graphStore.nodes.filter(n => n.validate?.status !== 'discarded').slice(0, 20)
  rightPanelRef.value?.openLinkDialog(candidates, (node, relationType) => { onLinkNode(node.id, text, relationType) })
}

function onCreateNodeFromSelection(text) {
  ElMessage.info(`创建知识点: ${text}`)
}

async function onLinkNode(nodeId, evidence = '', relationType = 'related') {
  if (!requireOnlineNote('关联知识点')) return
  await noteStore.linkNode(noteStore.currentNoteId, nodeId)
  nodeRelations.value[nodeId] = { label: relationType, evidence, confirmed: false }
  ElMessage.success('已关联知识点')
}

async function onUnlinkNode(nodeId) {
  if (!requireOnlineNote('解除关联')) return
  await noteStore.unlinkNode(noteStore.currentNoteId, nodeId)
  delete nodeRelations.value[nodeId]
  ElMessage.success('已解除关联')
}

function onConfirmLink(nodeId) {
  if (!requireOnlineNote('确认关联')) return
  if (nodeRelations.value[nodeId]) {
    nodeRelations.value[nodeId].confirmed = true
    ElMessage.success('已确认关联')
  }
}

async function onEditRelation(nodeId) {
  if (!requireOnlineNote('修改关系')) return
  const current = nodeRelations.value[nodeId]?.label || 'related'
  const { value } = await ElMessageBox.prompt('请输入关系类型', '修改关系', { inputValue: current, inputPlaceholder: '包含/依赖/对比/扩展/实现/基于/相关' })
  if (value && nodeRelations.value[nodeId]) {
    nodeRelations.value[nodeId].label = value
    ElMessage.success('关系已更新')
  }
}

async function onLinkFile(fileId) {
  if (!requireOnlineNote('关联文件')) return
  await noteStore.linkFile(noteStore.currentNoteId, fileId)
  ElMessage.success('已关联文件')
}

async function onUnlinkFile(fileId) {
  if (!requireOnlineNote('解除文件关联')) return
  await noteStore.unlinkFile(noteStore.currentNoteId, fileId)
  ElMessage.success('已解除文件关联')
}

function onOpenFile(fileId) { ElMessage.info('打开文件: ' + fileId) }
function onCreateNode(term) { ElMessage.info(`创建知识点: ${term}`) }
function onIgnoreNode(nodeId) { matchedTerms.value = matchedTerms.value.filter(m => m.node.id !== nodeId) }
function onAcceptFix(idx) {
  const issue = validationIssues.value[idx]
  if (issue && issue.correction) {
    const next = editorContent.value.replace(issue.text, issue.correction)
    editorContent.value = next
    validationIssues.value.splice(idx, 1)
    if (editMode.value === 'folder' && folderStore.currentOpenNote) {
      folderStore.setDraft(next)
      debouncedFolderSave()
    }
    ElMessage.success('已修正')
  }
}
function onIgnoreFix(idx) {
  validationIssues.value.splice(idx, 1)
  ElMessage.info('已忽略')
}
function onMiniGraphNodeClick(nodeId) { ElMessage.info('点击节点: ' + nodeId) }

const wbRoot = ref(null)
const { isFullscreen: nativeFs, toggle: toggleNativeFs } = useFullscreen(wbRoot)
watch(nativeFs, v => {
  isFullscreen.value = v
  if (!v) miniGraphExpanded.value = false
})
async function onToggleFullscreen() {
  const entering = !isFullscreen.value
  try {
    await toggleNativeFs()
    if (entering && !document.fullscreenElement && !nativeFs.value) isFullscreen.value = true
  } catch (_) { isFullscreen.value = entering }
  if (isFullscreen.value) miniGraphExpanded.value = false
}
function onToggleBg() { showBgSelector.value = !showBgSelector.value }
function onOpenNoteManage() { showNoteManage.value = !showNoteManage.value }
function onEditNoteFromManage(noteId) { onSelectNote(noteId); showNoteManage.value = false }
function onLinkNodeFromEditor(nodeId, relationType = 'related') { onLinkNode(nodeId, '', relationType) }
function onWikilinkSync(nodeIds) {
  if (editMode.value !== 'note' || !noteStore.currentNoteId) return
  const current = new Set(linkedNodeIds.value)
  let added = 0
  for (const id of nodeIds || []) {
    if (current.has(id)) continue
    noteStore.linkNode(noteStore.currentNoteId, id)
    nodeRelations.value[id] = { label: 'related', evidence: '[[双向链接]]', confirmed: true }
    added++
  }
  if (added > 0) ElMessage.success(`已通过 [[ 链接自动关联 ${added} 个知识点`)
}

defineExpose({ saveNote })
</script>

<style scoped>
.kw-workbench { display: flex; height: 100vh; overflow: hidden; background: var(--bg-primary); position: relative; }
.kw-bg-layer { position: absolute; inset: 0; z-index: 0; pointer-events: none; background: var(--editor-bg, var(--bg-primary)); }
.kw-left, .kw-center, .kw-right { position: relative; z-index: 1; }
.kw-left { width: 320px; flex-shrink: 0; border-right: 1px solid var(--border-light); background: var(--bg-glass); backdrop-filter: blur(20px) saturate(1.2); -webkit-backdrop-filter: blur(20px) saturate(1.2); overflow-y: auto; transition: width var(--dur-base) var(--ease-out); }
.kw-center { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
.kw-right { width: 360px; flex-shrink: 0; border-left: 1px solid var(--border-light); background: var(--bg-glass); backdrop-filter: blur(20px) saturate(1.2); -webkit-backdrop-filter: blur(20px) saturate(1.2); overflow-y: auto; transition: width var(--dur-base) var(--ease-out); }
.kw-workbench.kw-fullscreen { background: var(--editor-bg, var(--bg-primary)); }
.kw-workbench.kw-fullscreen .kw-center { background: transparent; }
@media (max-width: 1400px) { .kw-left { width: 288px; } .kw-right { width: 328px; } }
@media (max-width: 1024px) { .kw-left { width: 252px; } .kw-right { width: 296px; } }
@media (max-width: 768px) { .kw-left, .kw-right { display: none; } .kw-center { width: 100%; } }
.kw-fullscreen-minigraph { position: fixed; bottom: 0; left: 0; right: 0; z-index: 1060; background: var(--bg-primary); border-top: 1px solid var(--border); box-shadow: 0 -4px 12px rgba(0,0,0,0.3); transition: all 0.3s ease; }
.kw-minigraph-toggle { display: flex; align-items: center; justify-content: space-between; padding: 6px 16px; font-size: 11px; color: var(--text-secondary); cursor: pointer; background: var(--bg-secondary); border-bottom: 1px solid var(--border-light); user-select: none; }
.kw-minigraph-toggle:hover { color: var(--text-primary); }
.kw-minigraph-arrow { font-size: 9px; color: var(--text-muted); }
.kw-minigraph-body { height: 160px; }
</style>
