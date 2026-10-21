<!--
  Mermaid 流程图：把图谱总结的 mermaid 源码渲染成图。
  安全等级必须是 'strict'（图源来自用户上传的文档标题，属不可信输入，
  否则会经 innerHTML 形成存储型 XSS）。主题跟随应用亮/暗。
-->
<template>
  <div class="mflow-wrap">
  <div ref="frameRef" class="mflow">
    <div v-if="error" class="mflow-error">
      <div class="mfe-title">流程图渲染失败</div>
      <div class="mfe-msg">{{ error }}</div>
      <div class="mfe-hint">源码在下方「AI 可读源码」中，可直接粘贴到支持 Mermaid 的编辑器查看。</div>
    </div>
    <div v-else-if="rendering" class="mflow-loading">正在绘制流程图…</div>
    <!--
      两层结构：
        .mflow-sizer 负责**占位尺寸**（= 原图尺寸 × 缩放），让滚动条与实际内容一致；
        .mflow-host  保持原图尺寸，只做 transform 缩放。
      只写 transform 而不改占位尺寸时，130% 的右下角会滚不到（被布局裁掉），
      「适应」时又会拖出几千像素的空滚动条。
    -->
    <div v-show="!error && !rendering" class="mflow-sizer" :style="sizerStyle">
      <div ref="hostRef" class="mflow-host" :style="hostStyle"></div>
    </div>
  </div>
  <!-- 比例角标放在滚动容器**外面**：放里面会跟着内容一起滚，也会被 overflow 裁掉 -->
  <span v-if="zoom === 'fit' && svgReady" class="mflow-zoomtag">
    概览 {{ Math.round(effectiveZoom * 100) }}%
  </span>
  </div>
</template>

<script setup>
/**
 * MermaidFlow.vue
 * 渲染 Mermaid 流程图。mermaid 体积较大，用动态 import 按需加载（不进主包）。
 * 同一份 mermaid 源码既是"给人看的流程图"，也是"给 AI 读的结构化描述"。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { mermaidThemeVars } from '@/utils/palette'
import { useSettingsStore } from '@/store/settingsStore'

const props = defineProps({
  code: { type: String, default: '' },
  // 数值 = 固定缩放；'fit' = 按框的可用宽高等比缩到整图可见。
  // 为什么需要 'fit'：总结图是 TD 布局的稠密大图（实测固有尺寸可达数千像素），
  // 固定 100% 时框里只能看到左上角一小块，而且那一块常常是空的子图容器 ——
  // 「渲染成功」但第一眼什么也看不出来。'fit' 负责先给全貌，读细节再用固定档。
  zoom: { type: [Number, String], default: 1 }
})

const settingsStore = useSettingsStore()
const frameRef = ref(null)
const hostRef = ref(null)
const fitScale = ref(1)
// svg 的固有尺寸（viewBox）。记下来是为了把宿主的**布局尺寸**也按缩放改小 ——
// 只写 transform 的话布局尺寸仍是原图大小，130% 时右侧与底部会滚不到（被布局裁掉），
// 「适应」时又会拖出一条长达几千像素的空滚动条。
const natural = ref({ w: 0, h: 0 })
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
    flowchart: {
      htmlLabels: false, curve: 'basis', nodeSpacing: 34, rankSpacing: 46,
      // 必须关掉 useMaxWidth（默认 true）。开着的时候 Mermaid 给 svg 套 max-width
      // 让它「自适应容器宽」：6632px 宽的图会被等比压进 593px 的容器（8.6%），
      // 12px 的节点文字只剩 2px —— 渲染「成功」了但完全不可读。
      // 关掉后按自然尺寸出图，大图靠 .mflow 的 overflow:auto 滚动看，
      // 需要整体概览时用页面上的 75% / 100% / 130% 缩放，而不是自动缩到看不见。
      useMaxWidth: false,
    },
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

const effectiveZoom = computed(() => (
  props.zoom === 'fit' ? fitScale.value : (Number(props.zoom) || 1)
))

const svgReady = computed(() => natural.value.w > 0)

// 占位尺寸 = 原图 × 缩放
const sizerStyle = computed(() => {
  const s = effectiveZoom.value
  const { w, h } = natural.value
  return { width: `${w * s}px`, height: `${h * s}px` }
})

// 内容尺寸永远是原图，缩放只作用在 transform 上（避免二次缩放）
const hostStyle = computed(() => {
  const { w, h } = natural.value
  return {
    width: w ? `${w}px` : 'auto',
    height: h ? `${h}px` : 'auto',
    transform: `scale(${effectiveZoom.value})`,
  }
})

/** 按框的可用宽高把整张图缩到可见（不放大，最大 1） */
function computeFit() {
  const frame = frameRef.value
  const svg = hostRef.value?.querySelector('svg')
  if (!frame || !svg) return
  // 用 viewBox 的固有尺寸，而不是 getBoundingClientRect：
  // 后者会带上当前 transform 的缩放，算出的是「上次的缩放」，会越算越小。
  const w = natural.value.w
  const h = natural.value.h
  if (!w || !h) return
  const pad = 26   // 留一点内边距，图不要贴着边框
  const s = Math.min((frame.clientWidth - pad) / w, (frame.clientHeight - pad) / h)
  fitScale.value = Math.max(0.08, Math.min(1, s))
}

/**
 * 固定缩放时把视口滚到**节点质心**。
 * 不能滚到包围盒中心：这张图（TD + 按层级分组的子图）的包围盒被几个空的子图容器
 * 撑得极大（实测约 4900×5300），几何中心落在空白里 —— 打开看到一片空框，
 * 像渲染失败。按 g.node 的 bbox 求平均位置，才落在真正有内容的地方。
 */
function centerFrame() {
  const f = frameRef.value
  if (!f) return
  const svg = hostRef.value?.querySelector('svg')
  const s = effectiveZoom.value
  const nodes = svg ? [...svg.querySelectorAll('g.node')] : []
  let cx = f.scrollWidth / 2
  let cy = f.scrollHeight / 2
  if (nodes.length) {
    // 必须用 getCTM 把 bbox 换算到 svg 坐标系：
    // Mermaid 的每个 g.node 自带 translate，getBBox() 返回的是**节点自身**坐标系，
    // 中心恒为 (0,0) —— 直接平均会得到 (0,0)，滚回左上角。
    let sx = 0, sy = 0, ok = 0
    for (const n of nodes) {
      const b = n.getBBox()
      const m = n.getCTM()
      if (!m) continue
      const px = b.x + b.width / 2
      const py = b.y + b.height / 2
      sx += m.a * px + m.c * py + m.e
      sy += m.b * px + m.d * py + m.f
      ok++
    }
    if (ok) {
      cx = (sx / ok) * s
      cy = (sy / ok) * s
    }
  }
  f.scrollLeft = Math.max(0, cx - f.clientWidth / 2)
  f.scrollTop = Math.max(0, cy - f.clientHeight / 2)
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
    if (hostRef.value) {
      hostRef.value.innerHTML = svg
      const el = hostRef.value.querySelector('svg')
      const vb = el?.viewBox?.baseVal
      natural.value = {
        w: vb?.width || el?.getBoundingClientRect().width || 0,
        h: vb?.height || el?.getBoundingClientRect().height || 0,
      }
    }
  } catch (e) {
    error.value = e?.message || String(e)
    console.error('[MermaidFlow] render failed', e)
  } finally {
    // 必须在 rendering 置回 false 之后才量尺寸 / 滚动：
    // 渲染过程中宿主是 v-show=false（display:none），此时 scrollWidth 恒为 0，
    // 滚到质心会算成 0 —— 表现为「设置了滚动但画面没动」。
    rendering.value = false
    await nextTick()
    if (props.zoom === 'fit') computeFit()
    else centerFrame()
  }
}

let resizeObs = null
onMounted(() => {
  render()
  // 窗口/侧栏宽度变化后 'fit' 要重算，否则会停在旧比例上
  if (typeof ResizeObserver !== 'undefined' && frameRef.value) {
    resizeObs = new ResizeObserver(() => { if (props.zoom === 'fit') computeFit() })
    resizeObs.observe(frameRef.value)
  }
})
onBeforeUnmount(() => { resizeObs?.disconnect(); resizeObs = null })
watch(() => props.code, render)
watch(() => props.zoom, async z => {
  await nextTick()
  if (z === 'fit') computeFit()
  else centerFrame()
})
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
  /* 图比框小时居中；比框大时 margin:auto 会退化成 0，不会把左上角裁掉
     （flex 居中 + overflow 的经典坑，见 LoginView 里的同类说明） */
  display: flex;
}
/* flex: none 必须写：.mflow 是 flex 容器（为了居中），sizer 作为 flex 项
   默认 flex-shrink:1，放大到 130% 时会被压回 min-content（= 原图宽），
   于是占位宽度不再跟随缩放 —— 表现就是「放大后滚动范围没变」。 */
.mflow-sizer { position: relative; margin: auto; flex: 0 0 auto; }
.mflow-wrap { position: relative; width: 100%; min-width: 0; }
.mflow-zoomtag {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 1px 6px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--bg-tertiary) 88%, transparent);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  letter-spacing: 0.06em;
  color: var(--text-muted);
  white-space: nowrap;
  pointer-events: none;
}
.mflow-host {
  transform-origin: top left;
  transition: transform 0.15s var(--ease-out);
}
.mflow-host :deep(svg) {
  /*
    不要写 max-width:100% / height:auto —— 那会把整张图等比压回容器宽，
    正好抵消 flowchart.useMaxWidth:false（见 initMermaid 里的说明）。
    出图已带明确的宽高属性，保持自然尺寸，由 .mflow 滚动承载。
  */
  display: block;
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
