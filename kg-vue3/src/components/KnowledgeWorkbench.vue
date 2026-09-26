<template>
  <div ref="wbRoot" class="kw-workbench" :class="{ 'kw-fullscreen': isFullscreen }" :style="backgroundStyle">
    <!-- 背景层 -->
    <div v-if="hasBackground" class="kw-bg-layer" :style="bgOverlayStyle"></div>

    <!-- 左侧面板：知识库导航（320px，全屏时隐藏） -->
    <aside v-if="!isFullscreen" class="kw-left">
      <WorkbenchLeftPanel
        :current-note-id="noteStore.currentNoteId"
        @select-note="onSelectNote"
        @new-note="onNewNote"
        @open-note-manage="onOpenNoteManage"
        @select-folder-note="onSelectFolderNote"
      />
    </aside>

    <!-- 中间：笔记编辑器 -->
    <main class="kw-center">
      <!-- 笔记管理视图（嵌入模式） -->
      <NoteManageView
        v-if="showNoteManage && !isFullscreen"
        @edit-note="onEditNoteFromManage"
        @new-note="onNewNote"
        @close="showNoteManage = false"
      />

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
      <!-- 底部迷你图谱（全屏时隐藏） -->
      <WorkbenchMiniGraph
        v-if="!isFullscreen"
        :linked-node-ids="linkedNodeIds"
        :linked-file-ids="linkedFileIds"
        :current-note-title="editorTitle || '当前笔记'"
        :matched-node-ids="matchedNodeIds"
        @node-click="onMiniGraphNodeClick"
      />
    </main>

    <!-- 右侧面板：关联信息（360px，全屏时隐藏） -->
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

    <!-- 背景选择器（全局弹窗） -->
    <BackgroundSelector
      :visible="showBgSelector"
      @close="showBgSelector = false"
    />

    <!-- 全屏迷你图谱（可折叠面板） -->
    <div v-if="isFullscreen" class="kw-fullscreen-minigraph" :class="{ expanded: miniGraphExpanded }">
      <div class="kw-minigraph-toggle" @click="miniGraphExpanded = !miniGraphExpanded">
        <span>🕸️ 知识网络</span>
        <span class="kw-minigraph-arrow">{{ miniGraphExpanded ? '▼' : '▲' }}</span>
      </div>
      <div v-if="miniGraphExpanded" class="kw-minigraph-body">
        <WorkbenchMiniGraph
          :linked-node-ids="linkedNodeIds"
          :linked-file-ids="linkedFileIds"
          :current-note-title="editorTitle || '当前笔记'"
          :matched-node-ids="matchedNodeIds"
          @node-click="onMiniGraphNodeClick"
        />
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

/** 编辑器数据源：note=在线笔记（后端+IndexedDB）｜folder=本地文件夹工作区 */
const editMode = ref('note')

// 编辑器状态
const editorTitle = ref('')
const editorContent = ref('')
const editorTags = ref([])

// 全屏模式
const isFullscreen = ref(false)
const showBgSelector = ref(false)
const showNoteManage = ref(false)
const miniGraphExpanded = ref(false)

// 背景计算
const hasBackground = computed(() => {
  const bg = settingsStore.currentBackground
  return bg.type !== 'preset' || bg.value !== 'dark_night'
})

const backgroundStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const scope = bg.scope || 'editor'
  if (scope === 'global' || scope === 'workbench') {
    return {
      '--editor-bg': settingsStore.backgroundCSS
    }
  }
  return {}
})

const bgOverlayStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const scope = bg.scope || 'editor'
  if (scope === 'global' || scope === 'workbench') {
    return {
      opacity: bg.opacity ?? 0.8,
      filter: bg.blur ? `blur(${bg.blur}px)` : 'none'
    }
  }
  return {}
})

// 实时校验（v2 内核由 noteValidator.validateText 输出，含全文偏移）
const validationIssues = ref([])

// 智能连接推荐（写笔记时根据内容/标题推荐可关联的已有知识点）
const recommendations = ref([])

// 匹配到的术语和节点
const matchedTerms = ref([])
const matchedNodeIds = computed(() => matchedTerms.value.map(m => m.node.id))
const matchedNodes = computed(() => matchedTerms.value)

// 已关联的节点和文件（本地文件夹模式无在线关联）
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

// 编辑器来源标识 / 外部保存状态（传给 WorkbenchEditor 的 pill）
const editorSourceLabel = computed(() => {
  if (editMode.value === 'folder') return folderStore.currentOpenNote ? '本地文件' : ''
  return noteStore.currentNoteId ? '在线笔记' : ''
})
const editorSaveState = computed(() => {
  return editMode.value === 'folder' ? folderStore.saveState : 'clean'
})
/** 本地文件入库徽标（模块1 · 双写）：currentOpenNote.backendFileId / syncError 驱动 */
const editorLibState = computed(() => {
  if (editMode.value !== 'folder') return ''
  const n = folderStore.currentOpenNote
  if (!n) return ''
  if (n.syncError) return 'err'
  return n.backendFileId ? 'ok' : 'none'
})

// 节点关系映射
const nodeRelations = ref({})

// 初始化
onMounted(async () => {
  await noteStore.loadNotes()
  // 如果有笔记，自动选择第一个
  if (noteStore.sortedNotes.length > 0) {
    onSelectNote(noteStore.sortedNotes[0].id)
  }
  // 本地文件夹工作区：探测能力 + 恢复已授权目录句柄（不阻塞界面）
  folderStore.init().then(r => {
    if (r?.ok && r.count > 0) {
      console.info('[workbench] 已恢复本地文件夹工作区:', r.count)
    }
  })
})

/** 由 noteStore.currentNote 同步编辑器（在线笔记） */
function syncEditorFromNote() {
  const note = noteStore.currentNote
  if (note) {
    editorTitle.value = note.title
    editorContent.value = note.content || ''
    editorTags.value = note.tags || []
    nodeRelations.value = note._nodeRelations || {}
    // 后端 GET /notes 列表只返回 content 前 200 字，首次载入先拉全文，
    // 防止编辑器载入截断内容后被自动保存覆盖后端全文（数据丢失）
    ensureFullContent(note)
  }
}

/** 首次打开笔记时拉取后端全文（note._fullLoaded 防重复请求） */
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
    // 用户尚未在截断内容上继续输入时，把编辑器同步为全文
    if (noteStore.currentNoteId === note.id && editorContent.value === stale) {
      editorContent.value = full.content
    }
  } catch (e) {
    console.warn('[workbench] 拉取笔记全文失败:', e?.message)
  }
}

/** 由 folderStore.currentOpenNote 同步编辑器（本地文件） */
function syncEditorFromFolder() {
  const n = folderStore.currentOpenNote
  if (!n) { clearEditor(); return }
  editorTitle.value = n.title || ''
  editorContent.value = n.content || ''
  editorTags.value = n.tags || []
  nodeRelations.value = {}
  // 本地文件同样做术语匹配 + 实时校验（无在线关联）
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

/** 清空待执行保存并落地当前草稿（切换编辑源前调用，防止脏数据丢失） */
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
    await noteStore.saveNote(noteStore.currentNoteId, {
      title: editorTitle.value,
      content: editorContent.value,
      tags: editorTags.value,
      _nodeRelations: nodeRelations.value
    })
  }
}

// 监听当前在线笔记变化，同步编辑器并切回在线模式
watch(() => noteStore.currentNote, note => {
  if (note) {
    editMode.value = 'note'
    syncEditorFromNote()
  } else {
    clearEditor()
  }
}, { immediate: true })

// 监听本地文件打开/关闭：本地文件被关闭（删除/切工作区）时清空编辑器并撤销待执行防抖
watch(() => folderStore.currentOpenNote, note => {
  if (editMode.value !== 'folder') return
  if (note) {
    syncEditorFromFolder()
  } else {
    // 笔记已关闭（含 FolderWorkspacePanel.onCloseNote 已先行落盘），撤销残留防抖
    //（debounce 若尚未挂 .cancel()，可选调用跳过；残留回调会因无打开笔记而安全空转）
    debouncedFolderSave.cancel?.()
    debouncedTitle.cancel?.()
    clearEditor()
  }
})

// 选择在线笔记（切换到在线模式，先落地文件夹模式脏草稿）
async function onSelectNote(noteId) {
  showNoteManage.value = false
  if (editMode.value !== 'note' || noteStore.currentNoteId !== noteId) {
    await flushDrafts()
  }
  noteStore.setCurrentNote(noteId)
  editMode.value = 'note'
  syncEditorFromNote()
}

// 选择 / 打开本地文件夹笔记（本地为源，切换到文件夹模式）
async function onSelectFolderNote(relPath) {
  showNoteManage.value = false
  if (!folderStore.currentWorkspace) return
  if (editMode.value !== 'folder') await flushDrafts()
  editMode.value = 'folder'
  const r = await folderStore.openNote(relPath)
  if (r?.ok) syncEditorFromFolder()
  else if (r?.msg) ElMessage.warning(r.msg)
}

// 新建在线笔记
async function onNewNote() {
  showNoteManage.value = false
  if (editMode.value === 'folder') await flushDrafts()
  await noteStore.createNote('未命名笔记', '')
  editorRef.value?.focus()
}

// 编辑器输入（update:content 实时）
function onContentInput(content) {
  editorContent.value = content
  if (editMode.value === 'folder' && folderStore.currentOpenNote) {
    folderStore.setDraft(content)
  }
}

// ===== 防抖统一（utils/resilience.debounce：重复调用自动重置计时；.flush()/.cancel() 由该模块提供） =====
// 本地文件夹模式：标题元数据 / 术语匹配 / 自动保存
const debouncedTitle = debounce(() => folderStore.updateTitle(editorTitle.value), 600)
const debouncedFolderMatch = debounce(content => runMatching(content), 400)
const debouncedFolderSave = debounce(() => folderStore.saveNote(), 800)
// 在线笔记模式：匹配 + 自动保存
const debouncedNoteMatch = debounce(content => {
  runMatching(content)
  debouncedAutoSave()
}, 500)
const debouncedAutoSave = debounce(async () => {
  if (editMode.value !== 'note' || !noteStore.currentNoteId) return
  await noteStore.saveNote(noteStore.currentNoteId, {
    title: editorTitle.value,
    content: editorContent.value,
    tags: editorTags.value,
    _nodeRelations: nodeRelations.value
  })
}, 2000)

// 标题变化（本地文件模式：防抖写回 kg.json 元数据）
function onTitleChange(title) {
  editorTitle.value = title
  if (editMode.value === 'folder' && folderStore.currentOpenNote) {
    debouncedTitle()
  }
}

// 标签变化
function onTagsChange(tags) {
  editorTags.value = tags
  if (editMode.value === 'folder' && folderStore.currentOpenNote) {
    folderStore.currentOpenNote.tags = [...tags]
    debouncedFolderSave()
  }
}

// 内容变化：实时匹配 + 校验（按编辑源路由自动保存）
function onContentChange(content) {
  // ---- 本地文件夹模式：双写（本地权威）+ 术语匹配 ----
  if (editMode.value === 'folder') {
    if (!folderStore.currentOpenNote) return
    debouncedFolderMatch(content)
    debouncedFolderSave()
    return
  }
  // ---- 在线笔记模式 ----
  if (!noteStore.currentNoteId) return
  debouncedNoteMatch(content)
}

/** 统一执行术语匹配 + 实时校验（两种编辑源共用） */
function runMatching(content) {
  // 1. 提取术语并匹配
  const terms = extractTerms(content)
  const matched = matchGraphNodes(terms, graphStore.nodes)
  matchedTerms.value = matched

  // 2. 实时校验（v2 内核：全文一次出结果，带 start/end 全文偏移供编辑区波浪线定位）
  const issues = validateText(content)
  validationIssues.value = issues

  // 3. 智能连接推荐：根据当前内容+标题推荐可关联的已有知识点
  recommendations.value = recommendConnections(
    content, editorTitle.value, graphStore.nodes, linkedNodeIds.value
  )
}

// 自动保存（在线笔记）已统一为上方 debouncedAutoSave

// 手动保存
async function saveNote() {
  // ---- 本地文件夹：写盘 + kg.json ----
  if (editMode.value === 'folder') {
    if (!folderStore.currentOpenNote) return
    debouncedFolderSave.cancel?.()
    const r = await folderStore.saveNote()
    if (r?.ok) ElMessage.success('本地笔记已保存')
    else ElMessage.warning(r?.msg || '保存失败')
    return
  }
  // ---- 在线笔记 ----
  if (!noteStore.currentNoteId) return
  // 先本地预校验（含跨节点冲突），生成 v2 报告后随保存一并落库
  const assertions = editorContent.value.split(/[。！？\n]+/).filter(s => s.trim().length > 5)
  const result = await preSaveValidation(assertions.map(t => ({ text: t })), graphStore.nodes)

  const base = {
    title: editorTitle.value,
    content: editorContent.value,
    tags: editorTags.value,
    _nodeRelations: nodeRelations.value,
    validationReport: result,
    accuracyScore: result.summary.accuracy,
    verified: result.summary.accuracy >= 80 && result.errors.length === 0
  }

  if (result.errors.length > 0) {
    try {
      await ElMessageBox.confirm(
        `笔记中存在 ${result.errors.length} 个错误，${result.warnings.length} 个警告。是否仍然保存？`,
        '知识校验未通过',
        { type: 'warning', confirmButtonText: '强制保存', cancelButtonText: '返回修改' }
      )
    } catch (_) {
      return
    }
    await noteStore.saveNote(noteStore.currentNoteId, base)
    ElMessage.warning('已强制保存，笔记标记为待审查')
  } else {
    await noteStore.saveNote(noteStore.currentNoteId, base)
    ElMessage.success('笔记已保存')
  }
}

/** 在线笔记模式守卫：本地文件夹模式下的关联/写入操作需先切换到在线笔记 */
function requireOnlineNote(action = '该操作') {
  if (editMode.value !== 'note' || !noteStore.currentNoteId) {
    ElMessage.info(action + '需要在线笔记；本地文件的知识关联将在「导入知识库」后开放（模块1 Stage D）')
    return false
  }
  return true
}

// 选中文字 → 关联到知识点
function onAssociateSelection(text, extraData) {
  if (!requireOnlineNote('关联到知识点')) return

  // 如果是从拖拽来的，直接关联
  if (extraData && extraData.type === 'node') {
    onLinkNode(extraData.id, text)
    return
  }
  if (extraData && extraData.type === 'file') {
    onLinkFile(extraData.id)
    return
  }

  // 弹出候选节点列表
  const candidates = graphStore.nodes
    .filter(n => n.validate?.status !== 'discarded')
    .slice(0, 20)

  rightPanelRef.value?.openLinkDialog(candidates, (node, relationType) => {
    onLinkNode(node.id, text, relationType)
  })
}

// 从选中文字创建知识点
function onCreateNodeFromSelection(text) {
  ElMessage.info(`创建知识点: ${text}`)
  // 可以通过 graphStore 创建新节点
}

// 关联节点
async function onLinkNode(nodeId, evidence = '', relationType = 'related') {
  if (!requireOnlineNote('关联知识点')) return
  await noteStore.linkNode(noteStore.currentNoteId, nodeId)
  nodeRelations.value[nodeId] = {
    label: relationType,
    evidence,
    confirmed: false
  }
  ElMessage.success('已关联知识点')
}

// 解除关联节点
async function onUnlinkNode(nodeId) {
  if (!requireOnlineNote('解除关联')) return
  await noteStore.unlinkNode(noteStore.currentNoteId, nodeId)
  delete nodeRelations.value[nodeId]
  ElMessage.success('已解除关联')
}

// 确认关联
function onConfirmLink(nodeId) {
  if (!requireOnlineNote('确认关联')) return
  if (nodeRelations.value[nodeId]) {
    nodeRelations.value[nodeId].confirmed = true
    ElMessage.success('已确认关联')
  }
}

// 修改关系类型
async function onEditRelation(nodeId) {
  if (!requireOnlineNote('修改关系')) return
  const current = nodeRelations.value[nodeId]?.label || 'related'
  const { value } = await ElMessageBox.prompt('请输入关系类型', '修改关系', {
    inputValue: current,
    inputPlaceholder: '包含/依赖/对比/扩展/实现/基于/相关'
  })
  if (value && nodeRelations.value[nodeId]) {
    nodeRelations.value[nodeId].label = value
    ElMessage.success('关系已更新')
  }
}

// 关联文件
async function onLinkFile(fileId) {
  if (!requireOnlineNote('关联文件')) return
  await noteStore.linkFile(noteStore.currentNoteId, fileId)
  ElMessage.success('已关联文件')
}

// 解除关联文件
async function onUnlinkFile(fileId) {
  if (!requireOnlineNote('解除文件关联')) return
  await noteStore.unlinkFile(noteStore.currentNoteId, fileId)
  ElMessage.success('已解除文件关联')
}

// 打开文件
function onOpenFile(fileId) {
  ElMessage.info('打开文件: ' + fileId)
}

// 创建知识点
function onCreateNode(term) {
  ElMessage.info(`创建知识点: ${term}`)
}

// 忽略节点
function onIgnoreNode(nodeId) {
  matchedTerms.value = matchedTerms.value.filter(m => m.node.id !== nodeId)
}

// 接受校验修正
function onAcceptFix(idx) {
  const issue = validationIssues.value[idx]
  if (issue && issue.correction) {
    // 在编辑器中替换
    const next = editorContent.value.replace(issue.text, issue.correction)
    editorContent.value = next
    validationIssues.value.splice(idx, 1)
    // 本地文件夹模式：同步草稿并防抖落盘
    if (editMode.value === 'folder' && folderStore.currentOpenNote) {
      folderStore.setDraft(next)
      debouncedFolderSave()
    }
    ElMessage.success('已修正')
  }
}

// 忽略校验问题
function onIgnoreFix(idx) {
  validationIssues.value.splice(idx, 1)
  ElMessage.info('已忽略')
}

// 迷你图谱点击
function onMiniGraphNodeClick(nodeId) {
  ElMessage.info('点击节点: ' + nodeId)
}

// ===== 全屏模式 =====
const wbRoot = ref(null)
// 原生全屏：Esc 原生退出；失败（iframe/无授权）时回退为内部布局态
const { isFullscreen: nativeFs, toggle: toggleNativeFs } = useFullscreen(wbRoot)
watch(nativeFs, v => {
  isFullscreen.value = v
  if (!v) miniGraphExpanded.value = false
})

async function onToggleFullscreen() {
  const entering = !isFullscreen.value
  try {
    await toggleNativeFs()
    // requestFullscreen 在受限环境会抛错或静默失败 → 回退
    if (entering && !document.fullscreenElement && !nativeFs.value) {
      isFullscreen.value = true
    }
  } catch (_) {
    isFullscreen.value = entering
  }
  if (isFullscreen.value) {
    miniGraphExpanded.value = false
  }
}

function onToggleBg() {
  showBgSelector.value = !showBgSelector.value
}

// ===== 笔记管理 =====
function onOpenNoteManage() {
  showNoteManage.value = !showNoteManage.value
}

function onEditNoteFromManage(noteId) {
  onSelectNote(noteId)
  showNoteManage.value = false
}

// ===== 来自全屏编辑器的关联 =====
function onLinkNodeFromEditor(nodeId, relationType = 'related') {
  onLinkNode(nodeId, '', relationType)
}

// ===== [[ 双向链接：正文中的 [[知识点]] 自动同步为图谱关联 =====
let _wlNotified = false
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
  if (added > 0) {
    ElMessage.success(`已通过 [[ 链接自动关联 ${added} 个知识点`)
  }
}

// 暴露保存方法给父组件
defineExpose({ saveNote })
</script>

<style scoped>
.kw-workbench {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-primary);
  position: relative;
}

/* 背景层 */
.kw-bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: var(--editor-bg, var(--bg-primary));
}
.kw-left,
.kw-center,
.kw-right {
  position: relative;
  z-index: 1;
}

.kw-left {
  width: 320px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-light);
  background: var(--bg-glass);
  backdrop-filter: blur(20px) saturate(1.2);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  overflow-y: auto;
  transition: width var(--dur-base) var(--ease-out);
}

.kw-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.kw-right {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-light);
  background: var(--bg-glass);
  backdrop-filter: blur(20px) saturate(1.2);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  overflow-y: auto;
  transition: width var(--dur-base) var(--ease-out);
}

/* ===== 全屏模式 ===== */
.kw-workbench.kw-fullscreen {
  background: var(--editor-bg, var(--bg-primary));
}
.kw-workbench.kw-fullscreen .kw-center {
  background: transparent;
}

/* ===== 响应式（三栏 → 收窄 → 单栏图谱优先） ===== */
@media (max-width: 1400px) {
  .kw-left { width: 288px; }
  .kw-right { width: 328px; }
}
@media (max-width: 1024px) {
  .kw-left { width: 252px; }
  .kw-right { width: 296px; }
}
@media (max-width: 768px) {
  .kw-left, .kw-right { display: none; }
  .kw-center { width: 100%; }
}

/* 全屏迷你图谱（底部可折叠面板） */
.kw-fullscreen-minigraph {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 1060;
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
  box-shadow: 0 -4px 12px rgba(0,0,0,0.3);
  transition: all 0.3s ease;
}
.kw-minigraph-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
  user-select: none;
}
.kw-minigraph-toggle:hover {
  color: var(--text-primary);
}
.kw-minigraph-arrow {
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.kw-minigraph-body {
  height: 160px;
}
</style>