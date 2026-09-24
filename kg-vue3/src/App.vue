<template>
  <div class="app-shell" :style="appStyle">
    <!-- 顶部导航栏 -->
    <nav class="app-nav">
      <div class="app-nav-brand">知识图谱笔记</div>
      <div class="app-nav-tabs">
        <button type="button"
          class="nav-tab"
          :class="{ active: currentView === 'graph' }"
          @click="currentView = 'graph'"
        >知识图谱</button>
        <button type="button"
          class="nav-tab"
          :class="{ active: currentView === 'workbench' }"
          @click="currentView = 'workbench'"
        >知识工作台</button>
        <button type="button"
          class="nav-tab"
          :class="{ active: currentView === 'kb' }"
          @click="currentView = 'kb'"
        >知识库</button>
      </div>
      <div class="app-nav-actions">
        <button type="button"
          class="nav-theme-btn click-scale"
          :title="settingsStore.isDark ? '切换到亮色模式' : '切换到暗色模式'"
          @click="settingsStore.toggleTheme()"
        >
          <el-icon :size="15"><Sunny v-if="!settingsStore.isDark" /><Moon v-else /></el-icon>
        </button>
        <button type="button"
          v-if="currentView === 'workbench'"
          class="nav-btn nav-btn-save"
          @click="onSaveWorkbench"
        >保存</button>
      </div>
    </nav>

    <!-- 全局背景层 -->
    <div v-if="globalBg" class="app-global-bg" :style="globalBgStyle"></div>

    <!-- 图谱视图 -->
    <div v-show="currentView === 'graph'" class="app-view graph-view">
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
      <GraphCanvas />
    </div>

    <!-- 工作台视图（懒加载：首次切换时才挂载，之后保持状态） -->
    <div v-show="currentView === 'workbench'" class="app-view workbench-view">
      <KnowledgeWorkbench v-if="workbenchMounted" ref="workbenchRef" />
    </div>

    <!-- 知识库视图（懒加载：知识库是图谱关联的知识权威源） -->
    <div v-show="currentView === 'kb'" class="app-view kb-view-wrap">
      <KnowledgeBaseView v-if="kbMounted" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, defineAsyncComponent } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import FileUploader from '@/components/FileUploader.vue'
import ControlPanel from '@/components/ControlPanel.vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import KnowledgeAnalytics from '@/components/KnowledgeAnalytics.vue'
import KnowledgeReview from '@/components/KnowledgeReview.vue'
import KnowledgeQA from '@/components/KnowledgeQA.vue'
import { useFileStore } from '@/store/fileStore'
import { useGraphStore } from '@/store/graphStore'
import { useConfigStore } from '@/store/configStore'
import { useSettingsStore } from '@/store/settingsStore'
import { setGraphStoreRef } from '@/store/groupStore'

const fileStore = useFileStore()
const graphStore = useGraphStore()
const cfg = useConfigStore()
const settingsStore = useSettingsStore()

const currentView = ref('graph')
const workbenchRef = ref(null)

// 工作台懒加载：首次切到该视图时才异步加载并挂载（拆 chunk），之后常驻保持编辑状态
const KnowledgeWorkbench = defineAsyncComponent(() => import('@/components/KnowledgeWorkbench.vue'))
const workbenchMounted = ref(false)

// 知识库视图同样懒加载
const KnowledgeBaseView = defineAsyncComponent(() => import('@/components/KnowledgeBaseView.vue'))
const kbMounted = ref(false)

watch(currentView, v => {
  if (v === 'workbench') workbenchMounted.value = true
  if (v === 'kb') kbMounted.value = true
})

// 左侧面板折叠区块状态（localStorage 持久化）
const leftSections = useLocalStorage('kg-left-sections', ['files', 'control', 'analytics', 'review', 'qa'])

// 设置 groupStore 的 graphStore 引用
setGraphStoreRef(graphStore)

// 全局背景
const globalBg = computed(() => {
  return settingsStore.currentBackground.scope === 'global'
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

onMounted(async () => {
  // 加载用户设置
  await settingsStore.load()

  // 恢复持久化数据
  await fileStore.loadPersisted()
  // 自动触发孤儿校验
  graphStore.refreshOrphanCount()
  if (graphStore.nodeCount > 0) {
    ElMessage.success(`已恢复 ${graphStore.nodeCount} 节点 / ${graphStore.linkCount} 连线`)
  }
})

function onSaveWorkbench() {
  workbenchRef.value?.saveNote()
}
</script>
