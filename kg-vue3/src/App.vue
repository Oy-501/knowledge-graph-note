<template>
  <div class="app-shell" :style="appStyle">
    <nav class="app-nav">
      <div class="app-nav-brand">知识图谱笔记</div>
      <div class="app-nav-tabs">
        <button type="button" class="nav-tab" :class="{ active: currentView === 'graph' }" @click="currentView = 'graph'">知识图谱</button>
        <button type="button" class="nav-tab" :class="{ active: currentView === 'workbench' }" @click="currentView = 'workbench'">知识工作台</button>
        <button type="button" class="nav-tab" :class="{ active: currentView === 'kb' }" @click="currentView = 'kb'">知识库</button>
      </div>
      <div class="app-nav-actions">
        <button type="button" class="nav-theme-btn click-scale" :title="settingsStore.isDark ? '切换到亮色模式' : '切换到暗色模式'" @click="settingsStore.toggleTheme()">
          <el-icon :size="15"><Sunny v-if="!settingsStore.isDark" /><Moon v-else /></el-icon>
        </button>
        <button type="button" v-if="currentView === 'workbench'" class="nav-btn nav-btn-save" @click="onSaveWorkbench">保存</button>
      </div>
    </nav>

    <div v-if="globalBg" class="app-global-bg" :style="globalBgStyle"></div>

    <div v-show="currentView === 'graph'" class="app-view graph-view">
      <aside class="control-panel">
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

        <el-collapse v-model="leftSections" class="panel-collapse">
          <el-collapse-item name="files" title="文件管理"><FileUploader /></el-collapse-item>
          <el-collapse-item name="control" title="控制面板"><ControlPanel /></el-collapse-item>
          <el-collapse-item name="analytics" title="图谱分析"><KnowledgeAnalytics /></el-collapse-item>
          <el-collapse-item name="review" title="每日回顾"><KnowledgeReview /></el-collapse-item>
          <el-collapse-item name="qa" title="知识问答"><KnowledgeQA /></el-collapse-item>
        </el-collapse>

        <footer class="panel-foot">
          <span class="pf-dot"></span>知识校验 v2 · 已就绪
          <span class="pf-ver">SEV 4级</span>
        </footer>
      </aside>
      <GraphCanvas />
    </div>

    <div v-show="currentView === 'workbench'" class="app-view workbench-view">
      <KnowledgeWorkbench v-if="workbenchMounted" ref="workbenchRef" />
    </div>

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

const KnowledgeWorkbench = defineAsyncComponent(() => import('@/components/KnowledgeWorkbench.vue'))
const workbenchMounted = ref(false)

const KnowledgeBaseView = defineAsyncComponent(() => import('@/components/KnowledgeBaseView.vue'))
const kbMounted = ref(false)

watch(currentView, v => {
  if (v === 'workbench') workbenchMounted.value = true
  if (v === 'kb') kbMounted.value = true
})

const leftSections = useLocalStorage('kg-left-sections', ['files', 'control', 'analytics', 'review', 'qa'])

setGraphStoreRef(graphStore)

const globalBg = computed(() => settingsStore.currentBackground.scope === 'global')

const globalBgStyle = computed(() => {
  const bg = settingsStore.currentBackground
  const css = settingsStore.backgroundCSS
  return { background: css || 'var(--bg-deep)', opacity: bg.opacity ?? 0.8, filter: bg.blur ? `blur(${bg.blur}px)` : 'none' }
})

const appStyle = computed(() => {
  const bg = settingsStore.currentBackground
  if (bg.scope === 'global' && bg.type === 'color') return { background: bg.value }
  return {}
})

onMounted(async () => {
  await settingsStore.load()
  await fileStore.loadPersisted()
  graphStore.refreshOrphanCount()
  if (graphStore.nodeCount > 0) {
    ElMessage.success(`已恢复 ${graphStore.nodeCount} 节点 / ${graphStore.linkCount} 连线`)
  }
})

function onSaveWorkbench() {
  workbenchRef.value?.saveNote()
}
</script>
