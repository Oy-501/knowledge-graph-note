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

const props = defineProps({
  code: { type: String, default: '' },
  zoom: { type: Number, default: 1 }
})

const hostRef = ref(null)
const rendering = ref(false)
const error = ref('')
let mermaidMod = null

async function getMermaid() {
  if (mermaidMod) return mermaidMod
  const mod = await import('mermaid')
  mermaidMod = mod.default
  mermaidMod.initialize({
    startOnLoad: false,
    securityLevel: 'loose',
    theme: 'base',
    fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    flowchart: { htmlLabels: false, curve: 'basis', nodeSpacing: 34, rankSpacing: 46 },
    themeVariables: {
      fontSize: '12px',
      primaryColor: '#FFFFFF',
      primaryTextColor: '#2C3E4F',
      primaryBorderColor: '#4F6F8F',
      lineColor: '#8A93B0',
      tertiaryColor: '#F5F0EB',
      clusterBkg: '#F7F3EE',
      clusterBorder: '#D9D0C6'
    }
  })
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
  font-size: 12.5px;
  padding: 30px 0;
  text-align: center;
}
.mflow-error {
  color: var(--danger);
  font-size: 12px;
  line-height: 1.7;
  padding: 6px 4px;
}
.mfe-title { font-weight: 600; }
.mfe-msg { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.mfe-hint { color: var(--text-muted); }
</style>
