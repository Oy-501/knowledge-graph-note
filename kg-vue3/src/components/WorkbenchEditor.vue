<template>
  <div class="wbe-editor" :class="{ 'wbe-fullscreen': isFullscreen }">
    <!-- 标题栏 -->
    <div class="wbe-titlebar">
      <input
        v-model="localTitle"
        class="wbe-title-input"
        placeholder="笔记标题"
        @input="onTitleChange"
      />
      <div class="wbe-tags">
        <span
          v-if="modeTag"
          class="wbe-mode-pill"
          :class="'wbe-mode-' + modeState"
          :title="'来源：' + modeTag"
        >
          <span class="wbe-mode-dot"></span>{{ modeTag }} · {{ modeStateText }}
        </span>
        <span
          v-if="libState"
          class="wbe-lib-pill"
          :class="'wbe-lib-' + libState"
          :title="libTitle"
        >{{ libText }}</span>
        <span v-for="tag in localTags" :key="tag" class="wbe-tag">
          #{{ tag }}
          <button type="button" class="wbe-tag-remove" @click="removeTag(tag)">×</button>
        </span>
        <button type="button" class="wbe-add-tag" @click="showAddTag = !showAddTag">+ 添加标签</button>
        <div v-if="showAddTag" class="wbe-tag-input-wrap">
          <input
            ref="tagInput"
            v-model="newTag"
            class="wbe-tag-input"
            placeholder="输入标签"
            @keyup.enter="addTag"
            @blur="addTag"
          />
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="wbe-toolbar">
      <div class="wbe-toolbar-left">
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('**', '**')" title="粗体">B</button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('*', '*')" title="斜体"><i>I</i></button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('`', '`')" title="代码">&lt;/&gt;</button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('\n## ', '')" title="标题">H</button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('\n- ', '')" title="列表">≡</button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('\n> ', '')" title="引用">❝</button>
        <button type="button" class="wbe-tool-btn" @click="insertMarkdown('\n```\n', '\n```')" title="代码块">{ }</button>
      </div>
      <div class="wbe-toolbar-right">
        <button
          type="button"
          class="wbe-tool-btn"
          :class="{ active: previewMode === 'edit' }"
          @click="previewMode = 'edit'"
        >编辑</button>
        <button
          type="button"
          class="wbe-tool-btn"
          :class="{ active: previewMode === 'split' }"
          @click="previewMode = 'split'"
        >分屏</button>
        <button
          type="button"
          class="wbe-tool-btn"
          :class="{ active: previewMode === 'preview' }"
          @click="previewMode = 'preview'"
        >预览</button>
        <span class="wbe-toolbar-sep"></span>
        <button type="button" class="wbe-tool-btn" @click="onToggleBg" title="背景主题">🎨</button>
        <button type="button"
          class="wbe-tool-btn wbe-tool-btn-fullscreen"
          :class="{ active: isFullscreen }"
          @click="onToggleFullscreen"
          :title="isFullscreen ? '退出全屏' : '全屏沉浸'"
        >{{ isFullscreen ? '⊠' : '⛶' }}</button>
      </div>
    </div>

    <!-- 编辑/预览区 -->
    <div class="wbe-content" :class="'wbe-mode-' + previewMode">
      <!-- 编辑区 -->
      <div v-show="previewMode !== 'preview'" class="wbe-edit-wrap" :style="editAreaStyle">
        <!-- 校验波浪线校准层（与 textarea 同字体度量，scroll 联动，不可交互） -->
        <div ref="ghostRef" class="wbe-edit-ghost" aria-hidden="true">
          <div ref="ghostInnerRef" class="wbe-ghost-inner" v-html="ghostHtml"></div>
        </div>
        <textarea
          ref="editorRef"
          v-model="localContent"
          class="wbe-textarea"
          placeholder="在此输入笔记内容...&#10;&#10;支持 Markdown 语法&#10;匹配到的术语会在右侧面板显示&#10;⚠ 校验问题将以彩色波浪线标出（红=严重 橙=主要 黄=次要 蓝=提示）"
          spellcheck="false"
          @input="onContentChange"
          @scroll="onEditorScroll"
          @drop.prevent="onDrop"
          @dragover.prevent
          @contextmenu="onContextMenu"
          @keydown="onWlKeydown"
        ></textarea>
        <!-- 内联关联提示 -->
        <div
          v-for="hint in inlineHints"
          :key="hint.term"
          class="wbe-inline-hint"
          :style="getHintStyle(hint)"
          @click="onHintClick(hint)"
        >
          🔗 {{ hint.term }}
        </div>
        <!-- [[ 双向链接补全弹窗 -->
        <div
          v-if="wlOpen"
          class="wbe-wl-popup"
          :style="wlPopupStyle"
        >
          <div class="wbe-wl-list">
            <div
              v-for="(c, i) in wlCandidates"
              :key="c.id"
              class="wbe-wl-item"
              :class="{ active: i === wlIndex }"
              @mousedown.prevent="wlCommit(c)"
              @mouseenter="wlIndex = i"
            >
              <span class="wbe-wl-title">{{ c.title }}</span>
              <span class="wbe-wl-type">{{ c.type === 'note' ? '笔记' : '知识点' }}</span>
            </div>
            <div v-if="wlCandidates.length === 0" class="wbe-wl-empty">
              未找到匹配，继续输入或按 Esc 关闭
            </div>
          </div>
        </div>
      </div>

      <!-- 分屏拖拽调整条（全屏模式下显示） -->
      <div
        v-if="isFullscreen && previewMode === 'split'"
        class="wbe-split-handle"
        @mousedown="onSplitDragStart"
      ></div>

      <!-- 预览区 -->
      <div
        v-show="previewMode !== 'edit'"
        class="wbe-preview"
        ref="previewRef"
        @scroll="onPreviewScroll"
        :style="previewAreaStyle"
      >
        <div class="wbe-preview-content markdown-body" v-html="renderedHtml"></div>
      </div>
    </div>

    <!-- 全屏底部状态栏 -->
    <div v-if="isFullscreen" class="wbe-statusbar">
      <span class="wbe-status-title" @click="onEditTitle" :title="'点击修改标题'">
        📝 {{ localTitle || '未命名笔记' }}
      </span>
      <span class="wbe-status-info">
        <span class="wbe-status-stat">字数: {{ wordCount.toLocaleString() }}</span>
        <span class="wbe-status-sep">|</span>
        <span class="wbe-status-save" :class="saveStatusClass">{{ saveStatusText }}</span>
        <span class="wbe-status-sep">|</span>
        <span class="wbe-status-stat">🔗 关联 {{ linkedCount }} 知识点</span>
      </span>
      <div class="wbe-status-actions">
        <button type="button" class="wbe-status-btn" @click="onToggleBg" title="背景主题">🎨</button>
        <button type="button" class="wbe-status-btn" @click="onOpenAssociate" title="关联知识点">🔗</button>
        <button type="button" class="wbe-status-btn" @click="onSave" title="保存">💾</button>
        <button type="button" class="wbe-status-btn wbe-status-exit" @click="onToggleFullscreen" title="退出全屏 (Esc)">
          退出全屏
        </button>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div v-if="contextMenu.visible" class="wbe-context-menu" :style="contextMenu.style">
      <div class="wbe-cm-item" @click="onContextAssociate">🔗 关联到知识点</div>
      <div class="wbe-cm-item" @click="onContextCreateNode">🆕 创建知识点</div>
      <div class="wbe-cm-divider"></div>
      <div class="wbe-cm-item" @click="contextMenu.visible = false">✕ 关闭</div>
    </div>

    <!-- 全屏关联浮窗 -->
    <div v-if="associateDialog.visible" class="wbe-overlay" @click.self="associateDialog.visible = false">
      <div class="wbe-dialog">
        <div class="wbe-dialog-header">
          <h4>🔗 关联知识点</h4>
          <button type="button" class="wbe-dialog-close" @click="associateDialog.visible = false">✕</button>
        </div>
        <div class="wbe-dialog-body">
          <div class="wbe-dialog-section">
            <h5>🔍 搜索已有知识点</h5>
            <input
              v-model="associateDialog.searchQuery"
              class="wbe-dialog-search"
              placeholder="搜索知识点..."
              @input="onAssociateSearch"
            />
          </div>
          <div v-if="associateDialog.recommendations.length > 0" class="wbe-dialog-section">
            <h5>📌 系统推荐关联 ({{ associateDialog.recommendations.length }})</h5>
            <div v-for="rec in associateDialog.recommendations" :key="rec.node.id" class="wbe-dialog-candidate">
              <span class="wbe-dialog-cand-name">{{ rec.node.title }}</span>
              <select v-model="rec.relationType" class="wbe-dialog-select">
                <option value="contains">包含关系</option>
                <option value="depends">依赖关系</option>
                <option value="implements">实现关系</option>
                <option value="related">相关关系</option>
              </select>
              <button type="button" class="wbe-dialog-link-btn" @click="onConfirmAssociate(rec)">＋ 关联</button>
            </div>
          </div>
          <div v-else class="wbe-dialog-empty">暂无推荐知识点</div>
        </div>
        <div class="wbe-dialog-footer">
          <button type="button" class="wbe-dialog-btn" @click="associateDialog.visible = false">完成</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { extractTerms } from '@/utils/noteParser'
import { useGraphStore } from '@/store/graphStore'

const props = defineProps({
  title: { type: String, default: '' },
  content: { type: String, default: '' },
  tags: { type: Array, default: () => [] },
  matchedTerms: { type: Array, default: () => [] },
  isFullscreen: { type: Boolean, default: false },
  linkedNodeIds: { type: Array, default: () => [] },
  /** 编辑来源标识（如「在线笔记」「本地文件」），为空则不显示 */
  modeTag: { type: String, default: '' },
  /** 外部保存状态：clean | dirty | saving | error */
  modeState: { type: String, default: 'clean' },
  /** 本地文件入库状态：'' 不显示 | 'ok' 已入库 | 'none' 待入库 | 'err' 同步失败 */
  libState: { type: String, default: '' },
  /** 校验问题（模块2 · v2 口径）：{ type, severity, description, correction, text, start, end, line }[]，start/end 为全文偏移 */
  validationIssues: { type: Array, default: () => [] }
})

const emit = defineEmits([
  'update:title', 'update:content', 'update:tags',
  'content-change', 'associate-selection', 'create-node-from-selection',
  'toggle-fullscreen', 'toggle-bg', 'save-note', 'link-node', 'wikilink-sync'
])

const editorRef = ref(null)
const previewRef = ref(null)
const tagInput = ref(null)

const localTitle = ref(props.title)
const localContent = ref(props.content)
const localTags = ref([...props.tags])
const previewMode = ref('split')
const showAddTag = ref(false)
const newTag = ref('')

const contextMenu = ref({
  visible: false,
  style: {},
  selectedText: ''
})

// 全屏模式相关状态
const graphStore = useGraphStore()
const splitRatio = ref(50) // 分屏比例 (0-100, 编辑区占比)
const saveStatus = ref('saved') // 'saved' | 'saving' | 'unsaved'
const isDraggingSplit = ref(false)
const associateDialog = ref({
  visible: false,
  searchQuery: '',
  recommendations: []
})

// ===== [[ 双向链接补全状态 =====
const wlOpen = ref(false)
const wlQuery = ref('')
const wlStart = ref(0)
const wlCandidates = ref([])
const wlIndex = ref(0)
const wlPopupStyle = ref({})

// 字数统计
const wordCount = computed(() => {
  const text = localContent.value || ''
  // 中文字数+英文单词数
  const cnMatch = text.match(/[\u4e00-\u9fa5]/g)
  const enMatch = text.match(/[a-zA-Z]+/g)
  return (cnMatch ? cnMatch.length : 0) + (enMatch ? enMatch.length : 0)
})

// 关联知识点计数
const linkedCount = computed(() => {
  return (props.linkedNodeIds || []).length
})

// 保存状态文本
const saveStatusText = computed(() => {
  switch (saveStatus.value) {
    case 'saved': return '已自动保存'
    case 'saving': return '保存中...'
    case 'unsaved': return '未保存'
    default: return ''
  }
})

const saveStatusClass = computed(() => {
  return 'wbe-status-' + saveStatus.value
})

// 外部保存状态文本（本地文件模式使用，颜色与 pill 点联动）
const modeStateText = computed(() => ({
  clean: '已保存',
  dirty: '未保存',
  saving: '保存中…',
  error: '保存出错'
}[props.modeState] || '已保存'))

/** 本地文件入库徽标（模块1 · 双写状态提示） */
const libText = computed(() => ({
  ok: '🗄 已入库',
  none: '☁ 待入库',
  err: '⚠ 入库失败'
}[props.libState] || ''))
const libTitle = computed(() => {
  if (props.libState === 'ok') return '内容已双写知识库；删除本地笔记时知识节点保留'
  if (props.libState === 'err') return '后端不可达，本地保存不受影响；后端恢复后再次保存将自动重试'
  return '离线可用；首次保存将登记入知识库并抽取知识节点'
})

// 全屏模式下编辑区/预览区宽度百分比
const editAreaStyle = computed(() => {
  if (!props.isFullscreen || previewMode.value !== 'split') return {}
  return { flex: `0 0 ${splitRatio.value}%` }
})

const previewAreaStyle = computed(() => {
  if (!props.isFullscreen || previewMode.value !== 'split') return {}
  return { flex: `0 0 ${100 - splitRatio.value}%` }
})

// 内联关联提示
const inlineHints = ref([])
const editorScrollTop = ref(0)

// 监听外部内容变化
watch(() => props.title, v => { localTitle.value = v })
watch(() => props.content, v => { localContent.value = v })
watch(() => props.tags, v => { localTags.value = [...v] })

// ==================== 校验问题 → 波浪线 ====================
// 严重度标签/颜色（与 noteValidator.SEVERITIES 对齐；编辑器波浪线用 CSS class 上色）
const sevLabel = s => ({
  critical: '严重', major: '主要', minor: '次要', info: '提示'
}[s] || s)
const sevTitle = issue => {
  const parts = []
  if (issue.description) parts.push(issue.description)
  if (issue.correction) parts.push('建议：' + issue.correction)
  if (issue.evidence) parts.push('依据：' + issue.evidence)
  return `[${sevLabel(issue.severity)} · ${issue.type}] ${parts.join('\n')}`
}
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const ghostRef = ref(null)
const ghostInnerRef = ref(null)

/** 编辑区校准层 HTML：全文转义 + 按 issue [start,end) 包波浪线 span */
const ghostHtml = computed(() => {
  const src = localContent.value || ''
  const issues = (props.validationIssues || []).filter(i => Number.isFinite(i.start) && i.start < i.end)
  if (!issues.length) return ''
  const sorted = [...issues].sort((a, b) => a.start - b.start)
  let html = ''
  let pos = 0
  for (const issue of sorted) {
    const s = Math.max(pos, Math.max(0, issue.start))
    const e = Math.min(src.length, issue.end)
    if (e <= s || s < pos) continue // 越界/重叠则跳过
    html += escapeHtml(src.slice(pos, s))
    html += `<span class="wbe-wavy sev-${issue.severity}" data-sev="${issue.severity}"`
    html += ` data-start="${s}" data-end="${e}" title="${escapeHtml(sevTitle(issue))}">`
    html += escapeHtml(src.slice(s, e))
    html += '</span>'
    pos = e
  }
  html += escapeHtml(src.slice(pos))
  return html
})

/** textarea 滚动条实际占宽（classic 滚动条下右侧多出 ~15px），让 ghost 右缩同量保证 soft-wrap 断行一致 */
function syncGhostMetrics() {
  const ta = editorRef.value
  const ghost = ghostRef.value
  if (ta && ghost) {
    ghost.style.setProperty('--wbe-sb', (ta.offsetWidth - ta.clientWidth) + 'px')
  }
}

/** 编辑器滚动 → ghost 同步位移（垂直滚动；soft wrap 无水平滚动） */
function onEditorScroll() {
  const ta = editorRef.value
  const inner = ghostInnerRef.value
  if (ta && inner) {
    inner.style.transform = `translateY(${-ta.scrollTop}px)`
  }
  editorScrollTop.value = ta ? ta.scrollTop : 0
}
/** 内容/校验更新落库后统一校准：滚动位移 + 滚动条宽度 + DOM 尺寸 */
function syncGhostLayout() {
  syncGhostMetrics()
  onEditorScroll()
}
watch(() => props.validationIssues, () => { nextTick(syncGhostLayout) })
watch(() => props.content, () => { nextTick(syncGhostLayout) })
watch(() => localContent.value, () => { nextTick(syncGhostLayout) })

/** 源文本按 issue 包高亮 span（预览用；跳过代码块段，交给原 md 流水线继续处理） */
function wrapPreviewIssues(source, issues) {
  const list = (issues || []).filter(i => Number.isFinite(i.start) && i.start < i.end)
  if (!list.length) return source
  // 代码块范围（fence 内的内容不做 md 高亮，避免破坏 <pre>）
  const fenceRe = /```[\w]*\n[\s\S]*?```/g
  const fences = []
  let m
  while ((m = fenceRe.exec(source))) fences.push([m.index, m.index + m[0].length])
  const sorted = [...list].sort((a, b) => a.start - b.start)
  let out = ''
  let pos = 0
  for (const issue of sorted) {
    const s = Math.max(pos, Math.max(0, issue.start))
    const e = Math.min(source.length, issue.end)
    if (e <= s || s < pos) continue
    const inFence = fences.some(([fs, fe]) => s < fe && e > fs)
    if (inFence) continue
    out += source.slice(pos, s)
    out += `<span class="wbe-pv wbe-pv-${issue.severity}" data-sev="${issue.severity}" title="${escapeHtml(sevTitle(issue))}">`
    out += source.slice(s, e)
    out += '</span>'
    pos = e
  }
  out += source.slice(pos)
  return out
}

// 简单 Markdown 渲染
const renderedHtml = computed(() => {
  let html = wrapPreviewIssues(localContent.value || '', props.validationIssues)
  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 标题
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // 粗体/斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
  // 引用
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
  // 段落
  html = html.split('\n\n').map(p => {
    if (!p.trim()) return ''
    if (/^<(h[1-4]|ul|pre|blockquote)/.test(p.trim())) return p
    return '<p>' + p.replace(/\n/g, '<br>') + '</p>'
  }).join('')
  // 链接
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')

  return html
})

// 内容变化处理
let _debounceTimer = null
function onContentChange() {
  emit('update:content', localContent.value)
  detectWikilink()

  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => {
    emit('content-change', localContent.value)
    updateInlineHints()
    scheduleWikilinkSync()
  }, 300)
}

function onTitleChange() {
  emit('update:title', localTitle.value)
}

// ==================== [[ 双向链接补全 ====================
/** 用镜像 div 精确计算 textarea 内光标像素坐标（与 ghost 层同字体度量，软换行兼容） */
function getCaretPixel() {
  const ta = editorRef.value
  if (!ta) return { x: 16, y: 16 }
  const pos = ta.selectionStart
  const text = ta.value
  const cs = getComputedStyle(ta)
  const mirror = document.createElement('div')
  const ms = mirror.style
  ms.position = 'absolute'
  ms.visibility = 'hidden'
  ms.whiteSpace = 'pre-wrap'
  ms.wordBreak = 'break-word'
  ms.overflowWrap = 'anywhere'
  ms.fontFamily = cs.fontFamily
  ms.fontSize = cs.fontSize
  ms.lineHeight = cs.lineHeight
  ms.padding = cs.padding
  ms.border = cs.border
  ms.boxSizing = cs.boxSizing
  ms.letterSpacing = cs.letterSpacing
  const pl = parseFloat(cs.paddingLeft) || 0
  const pr = parseFloat(cs.paddingRight) || 0
  ms.width = (ta.clientWidth - pl - pr) + 'px'
  mirror.textContent = text.slice(0, pos)
  const marker = document.createElement('span')
  marker.textContent = '\u200b'
  mirror.appendChild(marker)
  document.body.appendChild(mirror)
  const r = marker.getBoundingClientRect()
  const tr = ta.getBoundingClientRect()
  document.body.removeChild(mirror)
  return { x: r.left - tr.left, y: r.top - tr.top }
}

function computeWlCandidates(q) {
  const list = graphStore.nodes.filter(n => n.status !== 'discarded')
  const ql = q.toLowerCase()
  let res = list
  if (ql) {
    res = list.filter(n =>
      (n.title || '').toLowerCase().includes(ql) ||
      (n.keywords || []).some(k => k.toLowerCase().includes(ql)) ||
      (n.entities || []).some(e => e.toLowerCase().includes(ql))
    )
  }
  return res.slice(0, 8)
}

/** 检测光标是否处于未闭合的 [[ 内，是则弹出补全 */
function detectWikilink() {
  const ta = editorRef.value
  if (!ta) return
  const pos = ta.selectionStart
  const before = localContent.value.slice(0, pos)
  const openIdx = before.lastIndexOf('[[')
  if (openIdx === -1) { closeWikilink(); return }
  const between = before.slice(openIdx + 2)
  if (between.includes(']]') || between.includes('\n') || between.includes('\r')) {
    closeWikilink(); return
  }
  wlQuery.value = between
  wlStart.value = openIdx
  wlCandidates.value = computeWlCandidates(between)
  wlIndex.value = 0
  wlOpen.value = true
  const px = getCaretPixel()
  wlPopupStyle.value = {
    top: Math.min(px.y + 24, 400) + 'px',
    left: Math.max(8, Math.min(px.x, 460)) + 'px'
  }
}

function closeWikilink() {
  wlOpen.value = false
  wlQuery.value = ''
  wlCandidates.value = []
  wlIndex.value = 0
}

function wlCommit(candidate) {
  const ta = editorRef.value
  const title = candidate.title
  const start = wlStart.value
  const end = ta ? ta.selectionStart : start + wlQuery.value.length
  const before = localContent.value.slice(0, start)
  const after = localContent.value.slice(end)
  localContent.value = before + '[[' + title + ']]' + after
  closeWikilink()
  nextTick(() => {
    if (ta) {
      ta.focus()
      const caret = start + title.length + 4
      ta.setSelectionRange(caret, caret)
    }
    emit('update:content', localContent.value)
    scheduleWikilinkSync()
  })
}

function onWlKeydown(ev) {
  if (!wlOpen.value) return
  if (ev.key === 'ArrowDown') {
    ev.preventDefault()
    wlIndex.value = (wlIndex.value + 1) % Math.max(wlCandidates.value.length, 1)
  } else if (ev.key === 'ArrowUp') {
    ev.preventDefault()
    wlIndex.value = (wlIndex.value - 1 + wlCandidates.value.length) % Math.max(wlCandidates.value.length, 1)
  } else if (ev.key === 'Enter' || ev.key === 'Tab') {
    ev.preventDefault()
    ev.stopPropagation()
    const c = wlCandidates.value[wlIndex.value]
    if (c) wlCommit(c)
  } else if (ev.key === 'Escape') {
    ev.preventDefault()
    ev.stopPropagation()
    closeWikilink()
  }
}

/** 解析正文中 [[...]] 标题 → 节点 id，上抛给父组件同步图谱关联 */
function scheduleWikilinkSync() {
  const text = localContent.value || ''
  const re = /\[\[([^\]\n]+)\]\]/g
  const ids = []
  let m
  while ((m = re.exec(text)) !== null) {
    const title = m[1].trim()
    if (!title) continue
    const node = graphStore.nodes.find(n => (n.title || '').trim() === title)
    if (node) ids.push(node.id)
  }
  emit('wikilink-sync', ids)
}

// 更新内联关联提示
function updateInlineHints() {
  const text = localContent.value
  if (!text) { inlineHints.value = []; return }

  const terms = extractTerms(text)
  const matched = props.matchedTerms || []
  const matchedTermNames = new Set(matched.map(m => m.term?.toLowerCase()))

  const hints = []
  for (const { term, position, length } of terms) {
    if (matchedTermNames.has(term.toLowerCase())) {
      hints.push({ term, position, length })
    }
  }
  inlineHints.value = hints
}

function getHintStyle(hint) {
  // 计算相对于编辑器的位置
  const textarea = editorRef.value
  if (!textarea) return { display: 'none' }

  const text = localContent.value
  const before = text.slice(0, hint.position)
  const lines = before.split('\n')
  const line = lines.length - 1
  const col = lines[lines.length - 1].length

  const lineHeight = 20
  const charWidth = 8
  const top = line * lineHeight - editorScrollTop.value + 4
  const left = col * charWidth + 8

  return {
    top: top + 'px',
    left: left + 'px',
    display: top < 0 ? 'none' : 'block'
  }
}

function onPreviewScroll() {
  // 同步滚动（简化）
}

function onHintClick(hint) {
  emit('associate-selection', hint.term, hint)
}

// 插入 Markdown 语法
function insertMarkdown(before, after) {
  const textarea = editorRef.value
  if (!textarea) return
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selected = localContent.value.slice(start, end)
  const newText = localContent.value.slice(0, start) + before + selected + after + localContent.value.slice(end)
  localContent.value = newText
  nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(start + before.length, start + before.length + selected.length)
  })
}

// 标签管理
function addTag() {
  const tag = newTag.value.trim()
  if (tag && !localTags.value.includes(tag)) {
    localTags.value.push(tag)
    emit('update:tags', [...localTags.value])
  }
  newTag.value = ''
  showAddTag.value = false
}

function removeTag(tag) {
  localTags.value = localTags.value.filter(t => t !== tag)
  emit('update:tags', [...localTags.value])
}

// 右键菜单
function onContextMenu(ev) {
  const textarea = editorRef.value
  if (!textarea) return
  const selected = localContent.value.slice(textarea.selectionStart, textarea.selectionEnd)
  if (!selected.trim()) return

  ev.preventDefault()
  contextMenu.value = {
    visible: true,
    style: { top: ev.clientY + 'px', left: ev.clientX + 'px' },
    selectedText: selected.trim()
  }
}

function onContextAssociate() {
  emit('associate-selection', contextMenu.value.selectedText)
  contextMenu.value.visible = false
}

function onContextCreateNode() {
  emit('create-node-from-selection', contextMenu.value.selectedText)
  contextMenu.value.visible = false
}

// ===== 全屏模式相关方法 =====

function onToggleFullscreen() {
  emit('toggle-fullscreen')
}

// Esc 键退出全屏
function onKeydown(ev) {
  if (ev.key === 'Escape' && props.isFullscreen) {
    emit('toggle-fullscreen')
  }
}

// 分屏拖拽调整
function onSplitDragStart(ev) {
  isDraggingSplit.value = true
  const startX = ev.clientX
  const startRatio = splitRatio.value
  const container = ev.target.parentElement
  const containerWidth = container ? container.clientWidth : window.innerWidth

  const onMouseMove = (e) => {
    if (!isDraggingSplit.value) return
    const dx = e.clientX - startX
    const newRatio = startRatio + (dx / containerWidth) * 100
    splitRatio.value = Math.max(20, Math.min(80, Math.round(newRatio)))
  }

  const onMouseUp = () => {
    isDraggingSplit.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function onToggleBg() {
  emit('toggle-bg')
}

function onSave() {
  saveStatus.value = 'saving'
  emit('save-note')
  setTimeout(() => {
    saveStatus.value = 'saved'
  }, 500)
}

function onEditTitle() {
  // 聚焦标题输入框
  const titleInput = document.querySelector('.wbe-title-input')
  if (titleInput) {
    titleInput.focus()
    titleInput.select()
  }
}

// 关联浮窗
function onOpenAssociate() {
  // 获取推荐节点
  const candidates = graphStore.nodes
    .filter(n => n.status !== 'discarded')
    .slice(0, 10)
    .map(n => ({
      node: n,
      relationType: 'related'
    }))
  associateDialog.value = {
    visible: true,
    searchQuery: '',
    recommendations: candidates
  }
}

function onAssociateSearch() {
  const q = (associateDialog.value.searchQuery || '').toLowerCase()
  const candidates = graphStore.nodes
    .filter(n => n.status !== 'discarded')
    .filter(n => !q || n.title.toLowerCase().includes(q))
    .slice(0, 10)
    .map(n => ({
      node: n,
      relationType: 'related'
    }))
  associateDialog.value.recommendations = candidates
}

function onConfirmAssociate(rec) {
  emit('link-node', rec.node.id, rec.relationType)
  ElMessage.success(`已关联到知识点: ${rec.node.title}`)
}

// 挂载/卸载 Esc 监听
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  syncGhostLayout()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})

// 拖拽到编辑器
function onDrop(ev) {
  try {
    const data = JSON.parse(ev.dataTransfer.getData('application/json'))
    if (data) {
      emit('associate-selection', data.title || data.id, data)
    }
  } catch (e) {
    // 不是 JSON 数据，忽略
  }
}

// 暴露方法
function focus() {
  editorRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.wbe-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 标题栏 */
.wbe-titlebar {
  padding: 12px 16px 8px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}
.wbe-title-input {
  width: 100%;
  padding: 6px 0;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
  outline: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.15s;
}
.wbe-title-input:focus {
  border-bottom-color: var(--accent);
}
.wbe-title-input::placeholder {
  color: var(--text-muted);
  font-weight: 400;
}
.wbe-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.wbe-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  background: var(--bg-tertiary);
  color: var(--accent-light);
  padding: 2px 8px;
  border-radius: 10px;
}
/* 编辑来源标识 pill（本地文件 / 在线笔记） */
.wbe-mode-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border);
}
.wbe-mode-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success, #4caf50);
}
.wbe-mode-dirty .wbe-mode-dot {
  background: var(--warning, #e8a020);
}
.wbe-mode-saving .wbe-mode-dot {
  background: var(--warning, #e8a020);
  animation: wbe-mode-blink 0.8s infinite;
}
.wbe-mode-error .wbe-mode-dot {
  background: var(--danger, #e84c4c);
}
.wbe-mode-error {
  color: var(--danger, #e84c4c);
}
@keyframes wbe-mode-blink {
  50% { opacity: 0.3; }
}
.wbe-lib-pill {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  white-space: nowrap;
}
.wbe-lib-ok {
  color: var(--success, #4caf50);
  border-color: color-mix(in srgb, var(--success, #4caf50) 35%, transparent);
}
.wbe-lib-err {
  color: var(--danger, #e84c4c);
  border-color: color-mix(in srgb, var(--danger, #e84c4c) 35%, transparent);
}
.wbe-tag-remove {
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  line-height: 1;
}
.wbe-add-tag {
  font-size: 10px;
  background: none;
  border: 1px dashed var(--border);
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: 10px;
  cursor: pointer;
}
.wbe-tag-input-wrap {
  display: inline-block;
}
.wbe-tag-input {
  width: 80px;
  padding: 2px 6px;
  font-size: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--accent);
  border-radius: 4px;
  color: var(--text-primary);
  outline: none;
}

/* 工具栏 */
.wbe-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
  background: var(--bg-secondary);
}
.wbe-toolbar-left,
.wbe-toolbar-right {
  display: flex;
  gap: 2px;
}
.wbe-tool-btn {
  padding: 3px 8px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.wbe-tool-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.wbe-tool-btn.active {
  background: var(--accent);
  color: #fff;
}

/* 内容区 */
.wbe-content {
  flex: 1;
  overflow: hidden;
  display: flex;
}
.wbe-mode-edit .wbe-edit-wrap { flex: 1; }
.wbe-mode-preview .wbe-preview { flex: 1; }
.wbe-mode-split .wbe-edit-wrap,
.wbe-mode-split .wbe-preview {
  flex: 1;
}

.wbe-edit-wrap {
  position: relative;
  overflow: hidden;
}
.wbe-textarea {
  width: 100%;
  height: 100%;
  padding: 16px;
  border: none;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
  resize: none;
  outline: none;
  font-family: var(--font-mono);
}
.wbe-textarea::placeholder {
  color: var(--text-muted);
}

/* ===== 校验波浪线校准层（模块2 · 编辑区）=====
   ghost 覆盖于 textarea 之上，同字体度量逐字符对齐；
   文字透明仅透出 textarea 真实文本，问题片段以 wavy 下划线着色。
   right 依据 textarea 滚动条占宽收缩，保证 soft-wrap 断行一致。 */
.wbe-edit-ghost {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: var(--wbe-sb, 0px);
  overflow: hidden;
  pointer-events: none;
  z-index: 3;
}
.wbe-ghost-inner {
  box-sizing: border-box;
  width: 100%;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.7;
  color: transparent;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  will-change: transform;
}
.wbe-ghost-inner :deep(.wbe-wavy) {
  text-decoration: underline;
  text-decoration-style: wavy;
  text-decoration-color: transparent;
  text-decoration-skip-ink: none;
}
.wbe-ghost-inner :deep(.wbe-wavy.sev-critical) { text-decoration-color: #ff3b30; }
.wbe-ghost-inner :deep(.wbe-wavy.sev-major)   { text-decoration-color: #ff8c1a; }
.wbe-ghost-inner :deep(.wbe-wavy.sev-minor)   { text-decoration-color: #d99a00; }
.wbe-ghost-inner :deep(.wbe-wavy.sev-info)    { text-decoration-color: #2f8fe0; }

/* ===== 校验高亮（模块2 · 预览区）=====
   淡色底 + 底部彩线标识问题片段，悬浮 title 展示 v2 口径描述 */
.wbe-preview-content :deep(.wbe-pv) {
  cursor: help;
  border-radius: 2px;
  padding: 0 1px;
}
.wbe-preview-content :deep(.wbe-pv.sev-critical) {
  background: rgba(255, 59, 48, 0.13);
  box-shadow: inset 0 -1.5px 0 rgba(255, 59, 48, 0.75);
}
.wbe-preview-content :deep(.wbe-pv.sev-major) {
  background: rgba(255, 140, 26, 0.15);
  box-shadow: inset 0 -1.5px 0 rgba(255, 140, 26, 0.75);
}
.wbe-preview-content :deep(.wbe-pv.sev-minor) {
  background: rgba(217, 154, 0, 0.15);
  box-shadow: inset 0 -1.5px 0 rgba(217, 154, 0, 0.75);
}
.wbe-preview-content :deep(.wbe-pv.sev-info) {
  background: rgba(47, 143, 224, 0.15);
  box-shadow: inset 0 -1.5px 0 rgba(47, 143, 224, 0.75);
}

.wbe-preview {
  overflow-y: auto;
  border-left: 1px solid var(--border-light);
}
.wbe-preview-content {
  padding: 16px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}

/* 内联关联提示 */
.wbe-inline-hint {
  position: absolute;
  font-size: 10px;
  background: rgba(126, 176, 255, 0.15);
  color: var(--accent-light);
  padding: 1px 6px;
  border-radius: 3px;
  cursor: pointer;
  z-index: 10;
  white-space: nowrap;
  border: 1px solid rgba(126, 176, 255, 0.3);
  pointer-events: auto;
}
.wbe-inline-hint:hover {
  background: rgba(126, 176, 255, 0.3);
}

/* 右键菜单 */
.wbe-context-menu {
  position: fixed;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  z-index: 1100;
  min-width: 160px;
  padding: 4px;
}
.wbe-cm-item {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.1s;
}
.wbe-cm-item:hover {
  background: var(--bg-hover);
}
.wbe-cm-divider {
  height: 1px;
  background: var(--border-light);
  margin: 4px 0;
}

/* Markdown 预览样式 */
.markdown-body :deep(h1) { font-size: 1.5em; margin: 0.5em 0; }
.markdown-body :deep(h2) { font-size: 1.3em; margin: 0.5em 0; }
.markdown-body :deep(h3) { font-size: 1.1em; margin: 0.4em 0; }
.markdown-body :deep(h4) { font-size: 1em; margin: 0.3em 0; }
.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(ul) { padding-left: 1.5em; }
.markdown-body :deep(code) {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: var(--bg-tertiary);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 0.5em 0;
}
.markdown-body :deep(strong) { font-weight: 600; }
.markdown-body :deep(em) { font-style: italic; }

/* ===== 全屏模式 ===== */
.wbe-editor.wbe-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1050;
  background: var(--editor-bg, var(--bg-primary));
}

/* 工具栏分隔 */
.wbe-toolbar-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
  margin: 0 4px;
}
.wbe-tool-btn-fullscreen {
  font-weight: 600;
}

/* 分屏拖拽调整条 */
.wbe-split-handle {
  width: 6px;
  cursor: col-resize;
  background: var(--border);
  flex-shrink: 0;
  transition: background 0.15s;
  position: relative;
}
.wbe-split-handle:hover {
  background: var(--accent);
}
.wbe-split-handle::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 24px;
  background: var(--text-muted);
  border-radius: 1px;
}

/* 全屏状态栏 */
.wbe-statusbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  font-size: 11px;
  z-index: 10;
}
.wbe-status-title {
  color: var(--text-primary);
  font-weight: 500;
  cursor: pointer;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.15s;
}
.wbe-status-title:hover {
  color: var(--accent-light);
}
.wbe-status-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
}
.wbe-status-stat {
  font-size: 11px;
}
.wbe-status-sep {
  color: var(--border);
}
.wbe-status-save {
  font-size: 11px;
  font-weight: 500;
}
.wbe-status-saved { color: var(--success); }
.wbe-status-saving { color: var(--warning); }
.wbe-status-unsaved { color: var(--danger); }
.wbe-status-actions {
  display: flex;
  gap: 4px;
}
.wbe-status-btn {
  padding: 3px 8px;
  border: 1px solid var(--border);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 11px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.wbe-status-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.wbe-status-exit {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 500;
  padding: 3px 12px;
}
.wbe-status-exit:hover {
  opacity: 0.9;
}

/* 全屏关联浮窗 */
.wbe-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
}
.wbe-dialog {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 440px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}
.wbe-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
}
.wbe-dialog-header h4 {
  font-size: 14px;
  color: var(--text-primary);
  margin: 0;
}
.wbe-dialog-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.wbe-dialog-body {
  padding: 14px 16px;
  overflow-y: auto;
  flex: 1;
}
.wbe-dialog-section {
  margin-bottom: 12px;
}
.wbe-dialog-section h5 {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 6px;
}
.wbe-dialog-search {
  width: 100%;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
}
.wbe-dialog-search:focus {
  border-color: var(--accent);
}
.wbe-dialog-candidate {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-bottom: 4px;
}
.wbe-dialog-cand-name {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wbe-dialog-select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 10px;
  padding: 2px 4px;
  outline: none;
  cursor: pointer;
}
.wbe-dialog-link-btn {
  padding: 3px 10px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 10px;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}
.wbe-dialog-link-btn:hover {
  opacity: 0.9;
}
.wbe-dialog-empty {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  padding: 16px;
}
.wbe-dialog-footer {
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
  display: flex;
  justify-content: flex-end;
}
.wbe-dialog-btn {
  padding: 5px 16px;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 11px;
  border-radius: 6px;
  cursor: pointer;
}
.wbe-dialog-btn:hover {
  background: var(--bg-hover);
}
</style>

<style scoped>
/* ============================================================
   UI 美化打磨层（不改 textarea 字体度量，ghost 校准层保持同步）
   双主题通过 main.css 的设计 token 自适应
   ============================================================ */
.wbe-editor {
  background: var(--bg-secondary);
}
.wbe-titlebar {
  padding: 14px 20px 10px;
  background: linear-gradient(180deg, var(--bg-glass-strong), var(--bg-glass));
  border-bottom: 1px solid var(--border-light);
}
.wbe-title-input {
  font-size: 19px;
  letter-spacing: 0.2px;
}
.wbe-tag,
.wbe-mode-pill,
.wbe-lib-pill {
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
}
.wbe-toolbar {
  padding: 6px 14px;
  background: var(--bg-secondary);
}
.wbe-tool-btn {
  padding: 4px 10px;
  border-radius: 6px;
  color: var(--text-secondary);
  transition: background-color var(--dur-fast), color var(--dur-fast), transform 0.12s var(--ease-out);
}
.wbe-tool-btn:hover {
  background: var(--accent-soft);
  color: var(--accent);
}
.wbe-tool-btn:active { transform: scale(0.94); }
.wbe-tool-btn.active {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 6px var(--accent-soft);
}
.wbe-textarea {
  caret-color: var(--accent);
}
.wbe-textarea::selection,
.wbe-preview-content ::selection { background: var(--accent-soft); }

/* 标题输入获得焦点的高亮底边 */
.wbe-title-input:focus { border-bottom-color: var(--mint); }

/* 右键菜单 / 关联浮窗 更柔和 */
.wbe-context-menu,
.wbe-dialog {
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--border-light);
  background: var(--bg-glass-strong);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
}
.wbe-cm-item { border-radius: 6px; }
.wbe-cm-item:hover { background: var(--accent-soft); color: var(--accent); }
.wbe-overlay { background-color: rgba(0, 0, 0, 0.4); }

/* 全屏状态栏毛玻璃 */
.wbe-editor.wbe-fullscreen .wbe-statusbar {
  backdrop-filter: blur(14px) saturate(1.3);
  -webkit-backdrop-filter: blur(14px) saturate(1.3);
}

/* ===== [[ 双向链接补全弹窗 ===== */
.wbe-wl-popup {
  position: absolute;
  z-index: 40;
  min-width: 200px;
  max-width: 320px;
  background: var(--bg-glass-strong);
  backdrop-filter: blur(16px) saturate(1.3);
  -webkit-backdrop-filter: blur(16px) saturate(1.3);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.wbe-wl-list {
  max-height: 200px;
  overflow-y: auto;
  padding: 4px;
}
.wbe-wl-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-primary);
  transition: background-color var(--dur-fast), color var(--dur-fast);
}
.wbe-wl-item:hover,
.wbe-wl-item.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}
.wbe-wl-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wbe-wl-type {
  font-size: 9px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.wbe-wl-empty {
  padding: 10px 12px;
  font-size: 11px;
  color: var(--text-muted);
}
</style>