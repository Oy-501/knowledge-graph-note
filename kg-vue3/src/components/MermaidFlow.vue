<template>
  <div class="mflow">
    <div v-if="error" class="mflow-error">
      <div class="mfe-title">流程图渲染失败</div>
      <div class="mfe-msg">{{ error }}</div>
      <div class="mfe-hint">源码在下方「AI 可读源码」中，可直接粘贴到支持 Mermaid 的编辑器查看。</div>
    </div>
    <div v-else-if="rendering" class="mflow-loading">正在绘制流程图…</div>
    <div v-show="!error && !rendering" ref="hostRef" class="mflow-host" :style="{ transform: `scale(${zoom})` }"></div>
  </div>
</template>

<script setup>
/**
 * MermaidFlow.vue
 * 渲染 Mermaid 流程图。mermaid 体积较大，用动态 import 按需加载（不进主包）。
 * 同一份 mermaid 源码既是"给人看的流程图"，也是"给 AI 读的结构化描述"。
 */
import { ref, watch, onMounted, nextTick } from 'vue'
import { mermaidThemeVars } from '@/utils/palette'
import { useSettingsStore } from '@/store/settingsStore'

const props = defineProps({
  code: { type: String, default: '' },
  zoom: { type: Number, default: 1 }
})

const settingsStore = useSettingsStore()
const hostRef = ref(null)
const rendering = ref(false)
const error = ref('')
let mermaidMod = null

/**
 * 主题跟随应用。
 * 为什么必须做：mermaid 的 themeVariables 一旦固化，深色页面上就会渲染出
 * 一整块白底流程图，非常刺眼；而且它是通过 innerHTML 注入的独立 SVG，
 * 没法用 CSS 变量覆盖内部填充色（SVG 里的 fill 是内联属性，优先级更高）。
 * 所以唯一正确的做法是在渲染时按当前主题传入。
 */
function initMermaid(isDark) {
  mermaidMod.initialize({
    startOnLoad: false,
    // 安全等级必须是 'strict'。
    // 这里的图源码来自知识图谱的节点标题，而节点标题来自**用户上传的文档**，
    // 属于不可信输入。'loose' 会放行标签内的 HTML 与部分可执行语法，
    // 渲染结果又通过 innerHTML 注入页面 —— 组合起来就是一条存储型 XSS 通路。
    // strict 会净化 / 拒绝危险标签，且不影响正常流程图的显示效果。
    securityLevel: 'strict',
    theme: 'base',
    fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    flowchart: { htmlLabels: false, curve: 'basis', nodeSpacing: 34, rankSpacing: 46 },
    themeVariables: {
      fontSize: '12px',
      ...mermaidThemeVars(isDark),
    }
  })
}

async function getMermaid() {
  if (!mermaidMod) {
    const mod = await import('mermaid')
    mermaidMod = mod.default
    initMermaid(settingsStore.isDark)
  }
  return mermaidMod
}

let seq = 0

async function render() {
  const code = (props.code || '').trim()
  if (!code) {
    error.value = ''
    if (hostRef.value) hostRef.value.innerHTML = ''
    return
  }
  rendering.value = true
  error.value = ''
  try {
    const mermaid = await getMermaid()
    // 主题变了要重新 initialize 再渲染，否则沿用第一次的配色
    initMermaid(settingsStore.isDark)
    const { svg } = await mermaid.render(`mflow-${Date.now()}-${seq++}`, code)
    await nextTick()
    if (hostRef.value) hostRef.value.innerHTML = svg
  } catch (e) {
    error.value = e?.message || String(e)
    console.error('[MermaidFlow] render failed', e)
  } finally {
    rendering.value = false
  }
}

onMounted(render)
watch(() => props.code, render)
// 切换亮/暗主题后重绘，否则流程图会停留在上一次主题的配色
watch(() => settingsStore.settings.theme, render)
</script>

<style scoped>
.mflow {
  width: 100%;
  overflow: auto;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 12px;
  min-height: 180px;
}
.mflow-host {
  transform-origin: top left;
  transition: transform 0.15s var(--ease-out);
}
.mflow-host :deep(svg) {
  max-width: 100%;
  height: auto;
}
.mflow-loading {
  color: var(--text-muted);
  font-size: var(--fs-sm);
  padding: 30px 0;
  text-align: center;
}
.mflow-error {
  color: var(--danger);
  font-size: var(--fs-sm);
  line-height: 1.7;
  padding: 6px 4px;
}
.mfe-title { font-weight: 600; }
.mfe-msg { color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--fs-xs); }
.mfe-hint { color: var(--text-muted); }
</style>
