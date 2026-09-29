<template>
  <div class="app-shell" :style="appStyle">
    <!-- 顶部导航栏（未登录时不渲染：登录页自己就是完整一屏） -->
    <nav v-if="authed" class="app-nav">
      <div class="app-nav-brand">知识图谱笔记</div>

      <!-- 导航生成自 NAV_TABS：新增视图只需加一项，键盘快捷键自动跟随 -->
      <div ref="tabsRef" class="app-nav-tabs" role="tablist" aria-label="主导航">
        <button
          v-for="(tab, i) in NAV_TABS"
          :key="tab.key"
          type="button"
          role="tab"
          class="nav-tab"
          :class="{ active: currentView === tab.key }"
          :aria-selected="currentView === tab.key"
          :aria-controls="`view-${tab.key}`"
          :data-tab-key="tab.key"
          :title="`${tab.hint}（快捷键 Ctrl+${i + 1}）`"
          @click="activate(tab.key)"
        >
          <span class="nav-tab-label">{{ tab.label }}</span>
          <kbd class="nav-tab-key">{{ i + 1 }}</kbd>
        </button>
      </div>

      <div class="app-nav-actions">
        <button type="button"
          class="nav-theme-btn click-scale"
          :title="settingsStore.isDark ? '切换到亮色模式' : '切换到暗色模式'"
          :aria-label="settingsStore.isDark ? '切换到亮色模式' : '切换到暗色模式'"
          @click="settingsStore.toggleTheme()"
        >
          <el-icon :size="15"><Sunny v-if="!settingsStore.isDark" /><Moon v-else /></el-icon>
        </button>
        <button type="button"
          v-if="currentView === 'workbench'"
          class="nav-btn nav-btn-save"
          @click="onSaveWorkbench"
        >保存</button>
        <!-- 账号入口：显示当前登录者，并提供改密 / 退出登录。
             没有出口用户就退不出去 —— 那等于登录功能只做了一半。 -->
        <AccountMenu />
      </div>
    </nav>

    <!-- 全局背景层（旧版单层背景：渐变 / 纯色 / 自定义图） -->
    <div v-if="globalBg" class="app-global-bg" :style="globalBgStyle"></div>

    <!--
      素材层：真实纹理与摄影背景
      ------------------------------------------------------------
      三层各自独立，因为三者的不透明度要分开调：
        照片要淡（是氛围，不是内容）
        图案更淡（是质感，不是图案展）
        颗粒几乎不可见（只负责打散色带）
      合在一层里就只能整体调，做不出「照片上浮一层细网格」的效果。

      取值全部来自 :root 上的 --tex-* 槽位变量（由 settingsStore 写入），
      这里不含任何素材路径 —— 换素材不用改这个文件。
    -->
    <div class="app-tex" aria-hidden="true">
      <div class="app-tex-photo"></div>
      <div class="app-tex-pattern"></div>
      <div class="app-tex-grain"></div>
    </div>

    <!--
      登录页
      ------------------------------------------------------------
      放在背景层**之后**、业务视图**之前**：这样登录页也能用上用户自己设置的
      背景与主题，看起来和应用是一体的，而不是另一个系统。

      关键点是业务视图用 `v-if="authed"` 包住而不是只有 v-show：
      视图里的组件（图谱画布、文件列表等）在挂载时就会请求后端，
      只藏起来的话未登录状态下会发出一堆请求然后全被拒 —— 既吵又慢。
    -->
    <LoginView v-if="!authed" />

    <template v-if="authed">

    <!-- 图谱视图 -->
    <div v-show="currentView === 'graph'" id="view-graph" class="app-view graph-view">
      <aside class="control-panel">
        <!-- 面板头：头像占位 + 统计 -->
        <header class="panel-head">
          <div class="ph-avatar">知</div>
          <div class="ph-meta">
            <div class="ph-title">知识图谱工作台</div>
            <div class="ph-stats">
              <span>{{ graphStore.nodeCount }} 个知识点</span>
              <span class="ph-dot">·</span>
              <span>{{ fileStore.fileCount }} 个文件</span>
            </div>
          </div>
        </header>

        <!-- 可折叠功能区块（状态 localStorage 持久化） -->
        <el-collapse v-model="leftSections" class="panel-collapse">
          <el-collapse-item name="files" title="文件管理">
            <FileUploader />
          </el-collapse-item>
          <el-collapse-item name="control" title="控制面板">
            <ControlPanel />
          </el-collapse-item>
          <el-collapse-item name="analytics" title="图谱分析">
            <KnowledgeAnalytics />
          </el-collapse-item>
          <el-collapse-item name="review" title="每日回顾">
            <KnowledgeReview />
          </el-collapse-item>
          <el-collapse-item name="qa" title="知识问答">
            <KnowledgeQA />
          </el-collapse-item>
        </el-collapse>

        <!-- 底部系统状态 -->
        <footer class="panel-foot">
          <span class="pf-dot"></span>知识校验 v2 · 已就绪
          <span class="pf-ver">SEV 4级</span>
        </footer>
      </aside>

      <!-- 错误边界：画布崩溃时左侧面板仍可用，用户能继续操作而不是整页白屏 -->
      <ErrorBoundary name="图谱画布" @recover="activate('graph')">
        <GraphCanvas />
      </ErrorBoundary>
    </div>

    <!-- 工作台视图（懒加载：首次切换时才挂载，之后保持状态） -->
    <div v-show="currentView === 'workbench'" id="view-workbench" class="app-view workbench-view">
      <ErrorBoundary v-if="workbenchMounted" name="知识工作台" @recover="activate('graph')">
        <KnowledgeWorkbench ref="workbenchRef" />
      </ErrorBoundary>
    </div>

    <!-- 知识库视图（懒加载：知识库是图谱关联的知识权威源） -->
    <div v-show="currentView === 'kb'" id="view-kb" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="kbMounted" name="知识库" @recover="activate('graph')">
        <KnowledgeBaseView />
      </ErrorBoundary>
    </div>

    <!-- 图谱总结视图（懒加载：总结 + 流程图 + 导出文档/PPT） -->
    <div v-show="currentView === 'summary'" id="view-summary" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="summaryMounted" name="图谱总结" @recover="activate('graph')">
        <GraphSummaryView />
      </ErrorBoundary>
    </div>

    <!-- 函数图像（懒加载：内含表达式解析库，进页面才加载） -->
    <div v-show="currentView === 'plot'" id="view-plot" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="plotMounted" name="函数图像" @recover="activate('graph')">
        <FunctionPlotView />
      </ErrorBoundary>
    </div>

    <!-- 背景 CSS 生成器（纯前端，不依赖后端） -->
    <div v-show="currentView === 'bgcss'" id="view-bgcss" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="bgcssMounted" name="背景 CSS 生成器" @recover="activate('graph')">
        <BackgroundCssView />
      </ErrorBoundary>
    </div>

    <!-- 个人主页（头像 / 自定义背景 / 我的数据） -->
    <div v-show="currentView === 'profile'" id="view-profile" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="profileMounted" name="个人主页" @recover="activate('graph')">
        <ProfileView @open-admin="activate('admin')" />
      </ErrorBoundary>
    </div>

    <!-- 后台管理（判定依据 / 候选审阅 / 操作审计） -->
    <div v-show="currentView === 'admin'" id="view-admin" class="app-view kb-view-wrap">
      <ErrorBoundary v-if="adminMounted" name="后台管理" @recover="activate('graph')">
        <AdminView />
      </ErrorBoundary>
    </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, defineAsyncComponent } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import FileUploader from '@/components/FileUploader.vue'
import ControlPanel from '@/components/ControlPanel.vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import KnowledgeAnalytics from '@/components/KnowledgeAnalytics.vue'
import KnowledgeReview from '@/components/KnowledgeReview.vue'
import KnowledgeQA from '@/components/KnowledgeQA.vue'
import AccountMenu from '@/components/AccountMenu.vue'
import LoginView from '@/components/LoginView.vue'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'
import { useConfigStore } from '@/store/configStore'
import { useSettingsStore } from '@/store/settingsStore'
import { useAuthStore } from '@/store/authStore'
import { setGraphStoreRef } from '@/store/groupStore'

const fileStore = useFileStore()
const graphStore = useGraphStore()
const cfg = useConfigStore()
const settingsStore = useSettingsStore()
const auth = useAuthStore()

/**
 * 登录门禁。
 *
 * 登录页**不用**懒加载：未登录时它是首屏内容，做成异步 chunk 会先白屏等下载。
 * 它本身很小（纯表单，无第三方库），放主包里代价可以忽略。
 */
const authed = computed(() => auth.isAuthed)

// 导航声明式配置：顺序即快捷键 Ctrl+1..N 的顺序
const NAV_TABS = [
  { key: 'graph', label: '知识图谱', hint: '节点与关联的全景图' },
  { key: 'workbench', label: '知识工作台', hint: '编辑笔记与知识节点' },
  { key: 'kb', label: '知识库', hint: '知识权威源，决定文件关联' },
  { key: 'summary', label: '图谱总结', hint: '结构总结 · 流程图 · 导出文档' },
  { key: 'profile', label: '个人主页', hint: '头像、背景与我的数据' },
  { key: 'admin', label: '后台管理', hint: '候选知识点审阅与操作审计' },
  // 放在最后而不是插在中间：插中间会让后面所有页签的快捷键整体后移，
  // 已有的肌肉记忆会突然失效。新增页签追加在末尾最不打扰。
  { key: 'plot', label: '函数图像', hint: '函数曲线绘制与形成过程' },
  // 同样追加在末尾。规律：新页签永远排最后 —— 插中间会让后面所有页签的
  // Ctrl+N 快捷键整体后移，用了几天养成的肌肉记忆会突然失灵。
  { key: 'bgcss', label: '背景 CSS', hint: '用一句话生成响应式背景代码' },
]

const currentView = ref('graph')
const workbenchRef = ref(null)
const tabsRef = ref(null)

// 工作台懒加载：首次切到该视图时才异步加载并挂载（拆 chunk），之后常驻保持编辑状态
const KnowledgeWorkbench = defineAsyncComponent(() => import('@/components/KnowledgeWorkbench.vue'))
const workbenchMounted = ref(false)

// 知识库视图同样懒加载
const KnowledgeBaseView = defineAsyncComponent(() => import('@/components/KnowledgeBaseView.vue'))
const kbMounted = ref(false)

// 图谱总结视图（含 mermaid 动态加载，必须懒挂载避免拖慢首屏）
const GraphSummaryView = defineAsyncComponent(() => import('@/components/GraphSummaryView.vue'))
const summaryMounted = ref(false)

// 函数图像：内含数学库，必须懒加载，否则拖慢首屏
const FunctionPlotView = defineAsyncComponent(() => import('@/components/plot/FunctionPlotView.vue'))
const plotMounted = ref(false)

// 背景 CSS 生成器：纯前端工具（不依赖后端），同样懒加载
const BackgroundCssView = defineAsyncComponent(() => import('@/components/bgcss/BackgroundCssView.vue'))
const bgcssMounted = ref(false)

// 个人主页 / 后台管理（同样懒加载）
const ProfileView = defineAsyncComponent(() => import('@/components/ProfileView.vue'))
const AdminView = defineAsyncComponent(() => import('@/components/AdminView.vue'))
const profileMounted = ref(false)
const adminMounted = ref(false)

watch(currentView, v => {
  if (v === 'workbench') workbenchMounted.value = true
  if (v === 'kb') kbMounted.value = true
  if (v === 'summary') summaryMounted.value = true
  if (v === 'plot') plotMounted.value = true
  if (v === 'bgcss') bgcssMounted.value = true
  if (v === 'profile') profileMounted.value = true
  if (v === 'admin') adminMounted.value = true
})

/** 切换视图：懒挂载 + 把激活页签滚入可视区（窄窗口下页签可横向滚动） */
function activate(key) {
  if (!NAV_TABS.some(t => t.key === key)) return
  currentView.value = key
  requestAnimationFrame(() => {
    const el = tabsRef.value?.querySelector(`[data-tab-key="${key}"]`)
    // scrollIntoView 在旧浏览器可能缺失，做存在性判断
    el?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  })
}

/** Ctrl/⌘ + 数字键切页签（正在输入时不劫持） */
function onKeydown(e) {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return
  const num = Number(e.key)
  if (!Number.isInteger(num) || num < 1 || num > NAV_TABS.length) return

  const el = document.activeElement
  const tag = (el?.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || el?.isContentEditable) return

  e.preventDefault()
  activate(NAV_TABS[num - 1].key)
}

// 左侧面板折叠区块状态（localStorage 持久化）
const leftSections = useLocalStorage('kg-left-sections', ['files', 'control', 'analytics', 'review', 'qa'])

// 设置 groupStore 的 graphStore 引用
setGraphStoreRef(graphStore)

// 全局背景
/**
 * 是否渲染旧版「整页单层背景」。
 *
 * 素材类背景必须排除掉：
 *  - 素材由 `.app-tex` 三层渲染，这一层只会是一块铺满视口的纯色
 *    （backgroundCSS 对素材返回空串 → 回落到 var(--bg-deep)），白占一次全屏合成；
 *  - 更麻烦的是它和 `.app-tex` **同为 z-index:0**，谁在上面完全靠 DOM 顺序决定。
 *    现在是 .app-tex 写在后面所以在上，但这属于「碰巧对」，
 *    再加一个 z-index:0 的层就可能把素材压下去。宁可不让它渲染。
 */
const globalBg = computed(() => {
  const bg = settingsStore.currentBackground
  return settingsStore.backgroundScope === 'global' && bg.type !== 'asset'
})

const globalBgStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const css = settingsStore.backgroundCSS
  return {
    background: css || 'var(--bg-deep)',
    opacity: bg.opacity ?? 0.8,
    filter: bg.blur ? `blur(${bg.blur}px)` : 'none'
  }
})

const appStyle = computed(() => {
  const bg = settingsStore.currentBackground
  if (bg.scope === 'global' && bg.type === 'color') {
    return { background: bg.value }
  }
  return {}
})

/**
 * 登录成功后才做的加载。
 *
 * 与 onMounted 里的设置加载分开，是因为这两类数据的性质不同：
 * 设置（主题、背景）是**本机**的，登录页也要用，必须无条件加载；
 * 文件与图谱是**服务端**的，未登录时加载只会拿到一串 401。
 */
async function loadWorkspaceData() {
  try {
    await fileStore.loadPersisted()
    graphStore.refreshOrphanCount()
    if (graphStore.nodeCount > 0) {
      ElMessage.success(`已恢复 ${graphStore.nodeCount} 节点 / ${graphStore.linkCount} 连线`)
    }
  } catch (e) {
    // 这里不弹错：fileStore 内部已经有失败提示，重复弹只会刷屏
    console.warn('[App] 工作区数据加载失败：', e?.message || e)
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)

  // 主题与背景是本机设置，先加载 —— 登录页要靠它显示正确的配色与背景
  await settingsStore.load()

  // 探测登录状态；已登录（刷新页面场景）直接进应用，未登录则停在登录页
  await auth.probe()
  if (auth.isAuthed) await loadWorkspaceData()
})

// 登录成功后（含初始化与注册）再加载工作区数据。
// 用 watch 而不是在登录页里回调：登录、初始化、注册、重试四条路径都会改
// isAuthed，一处监听就全覆盖，不必在每个入口各写一遍。
watch(() => auth.isAuthed, (now, before) => {
  if (now && !before) loadWorkspaceData()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

function onSaveWorkbench() {
  workbenchRef.value?.saveNote()
}
</script>
