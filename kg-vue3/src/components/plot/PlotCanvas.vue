<template>
  <div ref="hostRef" class="plot-host" @wheel.prevent="onWheel" @mousedown="onMouseDown">
    <svg :width="size.w" :height="size.h" class="plot-svg">
      <defs>
        <clipPath :id="clipId">
          <rect :x="pad.l" :y="pad.t" :width="plotW" :height="plotH" />
        </clipPath>
      </defs>

      <!-- 网格 -->
      <g v-if="showGrid" class="layer-grid">
        <line v-for="t in xTicks" :key="'gx' + t"
              :x1="sx(t)" :y1="pad.t" :x2="sx(t)" :y2="pad.t + plotH"
              :class="['grid-line', { major: Math.abs(t) < 1e-9 }]" />
        <line v-for="t in yTicks" :key="'gy' + t"
              :x1="pad.l" :y1="sy(t)" :x2="pad.l + plotW" :y2="sy(t)"
              :class="['grid-line', { major: Math.abs(t) < 1e-9 }]" />
      </g>

      <!-- 竖直渐近线 -->
      <g v-if="showAsymptotes" class="layer-asym">
        <line v-for="(a, i) in allAsymptotes" :key="'as' + i"
              :x1="sx(a.x)" :y1="pad.t" :x2="sx(a.x)" :y2="pad.t + plotH"
              class="asym-line" />
      </g>

      <!-- 坐标轴 -->
      <g class="layer-axis">
        <line :x1="pad.l" :y1="sy(0)" :x2="pad.l + plotW" :y2="sy(0)" class="axis-line" />
        <line :x1="sx(0)" :y1="pad.t" :x2="sx(0)" :y2="pad.t + plotH" class="axis-line" />
        <!-- 轴末端箭头 -->
        <path :d="arrowX" class="axis-arrow" />
        <path :d="arrowY" class="axis-arrow" />
        <!-- 刻度 -->
        <text v-for="t in xTicks" :key="'tx' + t" :x="sx(t)" :y="axisYPos + 15"
              class="tick-label" text-anchor="middle">{{ fmtTick(t) }}</text>
        <text v-for="t in yTicks" :key="'ty' + t" :x="axisXPos - 8" :y="sy(t) + 4"
              class="tick-label" text-anchor="end">{{ fmtTick(t) }}</text>
        <text :x="pad.l + plotW - 4" :y="axisYPos - 8" class="axis-name" text-anchor="end">x</text>
        <text :x="axisXPos + 8" :y="pad.t + 10" class="axis-name">y</text>
        <text v-if="inViewY(0)" :x="axisXPos - 8" :y="axisYPos + 15"
              class="tick-label" text-anchor="end">O</text>
      </g>

      <!-- 曲线 -->
      <g :clip-path="`url(#${clipId})`" class="layer-curves">
        <template v-for="f in functionsWithHead" :key="f.id">
          <template v-if="f.visible !== false && f.sampled">
            <!-- 未描绘部分：淡显，用于对比"还将形成" -->
            <path v-for="(seg, i) in f.sampled.segments" :key="`g${f.id}-${i}`"
                  v-show="animating"
                  :d="pathOf(seg)" :stroke="f.color" class="curve-ghost" />
            <!-- 已描绘部分 -->
            <path v-for="(seg, i) in formedSegments(f)" :key="`c${f.id}-${i}`"
                  :d="pathOf(seg)" :stroke="f.color" class="curve-line" />
            <!-- 描点法：逐个出现的采样点 -->
            <circle v-for="(p, i) in dotPoints(f)" :key="`d${f.id}-${i}`"
                    :cx="sx(p.x)" :cy="sy(p.y)" r="2.2" :fill="f.color" class="curve-dot" />
            <!-- 连续描绘：当前生成点 + 到坐标轴的虚线引导 -->
            <template v-if="animating && f.animHead">
              <line :x1="sx(f.animHead.x)" :y1="sy(f.animHead.y)"
                    :x2="sx(f.animHead.x)" :y2="axisYPos" class="guide-line" :stroke="f.color" />
              <line :x1="sx(f.animHead.x)" :y1="sy(f.animHead.y)"
                    :x2="axisXPos" :y2="sy(f.animHead.y)" class="guide-line" :stroke="f.color" />
              <circle :cx="sx(f.animHead.x)" :cy="sy(f.animHead.y)" r="4.5"
                      :fill="f.color" class="head-dot" />
            </template>
          </template>
        </template>
      </g>

      <!-- 特征点标注 -->
      <g v-if="showFeatures" :clip-path="`url(#${clipId})`" class="layer-features">
        <g v-for="f in functionsWithHead" :key="'ft' + f.id">
          <template v-if="f.visible !== false && f.features">
            <circle v-for="(z, i) in f.features.zeros" :key="'z' + f.id + i"
                    :cx="sx(z.x)" :cy="sy(0)" r="3.5" class="feat-zero" />
            <circle v-for="(e, i) in f.features.extrema" :key="'e' + f.id + i"
                    :cx="sx(e.x)" :cy="sy(e.y)" r="3.5" class="feat-extremum" />
          </template>
        </g>
      </g>

      <!-- 探针（鼠标位置 / 拖动取值） -->
      <g v-if="probeVisible && probeX !== null" :clip-path="`url(#${clipId})`" class="layer-probe">
        <line :x1="sx(probeX)" :y1="pad.t" :x2="sx(probeX)" :y2="pad.t + plotH" class="probe-line" />
        <template v-for="f in probeDots" :key="'pd' + f.id">
          <circle :cx="sx(f.x)" :cy="sy(f.y)" r="4" :fill="f.color" class="probe-dot" />
        </template>
      </g>
    </svg>

    <!-- 鼠标读数：贴在光标附近，避免眼神来回跑 -->
    <div v-if="probeVisible && probeX !== null" class="probe-readout"
         :style="{ left: Math.min(Math.max(sx(probeX) + 12, 4), size.w - 176) + 'px' }">
      <div class="pr-x">x = {{ fmtReadout(probeX) }}</div>
      <div v-for="f in probeDots" :key="'pr' + f.id" class="pr-row">
        <span class="pr-dot" :style="{ background: f.color }"></span>
        <span class="pr-expr">{{ shortLabel(f) }}</span>
        <span class="pr-val">{{ Number.isFinite(f.y) ? fmtReadout(f.y) : '无定义' }}</span>
      </div>
    </div>

    <div v-if="!hasAnyVisible" class="plot-empty">
      <span>左侧输入一个函数，曲线会立即显示</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatNumber, niceTicks } from '@/utils/functionMath'

const props = defineProps({
  functions: { type: Array, default: () => [] },
  viewport: { type: Object, required: true },   // { xMin, xMax, yMin, yMax }
  showGrid: { type: Boolean, default: true },
  showFeatures: { type: Boolean, default: true },
  showAsymptotes: { type: Boolean, default: true },
  // 形成过程：progress ∈ [0,1]；为 null 表示不播放（显示完整曲线）
  progress: { type: Number, default: null },
  animMode: { type: String, default: 'trace' },  // trace | dots
  probeVisible: { type: Boolean, default: true },
})

const emit = defineEmits(['update:viewport', 'probe'])

const hostRef = ref(null)
const size = ref({ w: 800, h: 520 })
const pad = { l: 46, r: 18, t: 16, b: 30 }
const clipId = `plotclip-${Math.random().toString(36).slice(2, 9)}`

let ro = null
onMounted(() => {
  const el = hostRef.value
  if (!el) return
  const apply = () => {
    const r = el.getBoundingClientRect()
    size.value = { w: Math.max(240, r.width), h: Math.max(200, r.height) }
  }
  apply()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(apply)
    ro.observe(el)
  } else {
    window.addEventListener('resize', apply)
  }
})
onBeforeUnmount(() => {
  ro?.disconnect()
})

const plotW = computed(() => Math.max(10, size.value.w - pad.l - pad.r))
const plotH = computed(() => Math.max(10, size.value.h - pad.t - pad.b))

/* ------------------------------------------------------------ 坐标映射 */

function sx(x) {
  const { xMin, xMax } = props.viewport
  return pad.l + ((x - xMin) / (xMax - xMin || 1)) * plotW.value
}
function sy(y) {
  const { yMin, yMax } = props.viewport
  return pad.t + plotH.value - ((y - yMin) / (yMax - yMin || 1)) * plotH.value
}
function ix(px) {
  const { xMin, xMax } = props.viewport
  return xMin + ((px - pad.l) / (plotW.value || 1)) * (xMax - xMin)
}

const inViewY = (y) => y >= props.viewport.yMin && y <= props.viewport.yMax

/* ------------------------------------------------------------ 刻度与轴 */

const xTicks = computed(() => niceTicks(props.viewport.xMin, props.viewport.xMax,
  Math.max(4, Math.round(plotW.value / 84))).ticks)
const yTicks = computed(() => niceTicks(props.viewport.yMin, props.viewport.yMax,
  Math.max(3, Math.round(plotH.value / 52))).ticks)

const fmtTick = (v) => formatNumber(v, 3)
const fmtReadout = (v) => formatNumber(v, 3)

// 坐标轴位置：0 在视野内就用真实 0，否则贴边（保证轴始终可见）
const axisYPos = computed(() => {
  const { yMin, yMax } = props.viewport
  return yMin > 0 ? pad.t : (yMax < 0 ? pad.t + plotH.value : sy(0))
})
const axisXPos = computed(() => {
  const { xMin, xMax } = props.viewport
  return xMin > 0 ? pad.l : (xMax < 0 ? pad.l + plotW.value : sx(0))
})

const arrowX = computed(() => {
  const y = axisYPos.value
  const x = pad.l + plotW.value
  return `M ${x - 7} ${y - 4} L ${x} ${y} L ${x - 7} ${y + 4}`
})
const arrowY = computed(() => {
  const x = axisXPos.value
  const y = pad.t
  return `M ${x - 4} ${y + 7} L ${x} ${y} L ${x + 4} ${y + 7}`
})

/* ------------------------------------------------------------ 曲线路径 */

const hasAnyVisible = computed(() =>
  props.functions.some(f => f.visible !== false && f.sampled?.segments?.length))

const animating = computed(() => props.progress !== null && props.progress < 1)

/** 把一段采样点转成 SVG path（控制精度，避免超长字符串） */
function pathOf(points) {
  if (!points || points.length < 1) return ''
  const yLo = props.viewport.yMin - (props.viewport.yMax - props.viewport.yMin) * 3
  const yHi = props.viewport.yMax + (props.viewport.yMax - props.viewport.yMin) * 3
  let d = ''
  for (let i = 0; i < points.length; i++) {
    const p = points[i]
    const yy = Math.min(yHi, Math.max(yLo, p.y))   // 先夹紧，防超大数值撑爆渲染
    d += (i === 0 ? 'M' : 'L') + sx(p.x).toFixed(1) + ' ' + sy(yy).toFixed(1)
  }
  return d
}

/** 当前动画进度对应的 x 截断位置 */
const progressX = computed(() => {
  if (props.progress === null) return null
  const { xMin, xMax } = props.viewport
  return xMin + (xMax - xMin) * props.progress
})

/** 已"形成"的曲线部分（按 x 截断，并插入插值端点让截断处平滑） */
function formedSegments(f) {
  if (!f.sampled) return []
  const cut = progressX.value
  if (cut === null) return f.sampled.segments

  const out = []
  for (const seg of f.sampled.segments) {
    const part = []
    for (let i = 0; i < seg.length; i++) {
      const p = seg[i]
      if (p.x <= cut) {
        part.push(p)
      } else {
        const prev = seg[i - 1]
        if (prev) {
          // 线性插值出正好落在截断线上的点，避免动画边缘一跳一跳
          const t = (cut - prev.x) / (p.x - prev.x || 1)
          part.push({ x: cut, y: prev.y + (p.y - prev.y) * t, interpolated: true })
        }
        break
      }
    }
    if (part.length >= 2) out.push(part)
  }
  return out
}

/** 描点法的点：按进度逐步出现 */
function dotPoints(f) {
  if (!f.sampled || props.animMode !== 'dots') return []
  const cut = progressX.value
  const all = f.sampled.segments.flat()
  if (cut === null) {
    // 不播放时只标出少量"关键采样点"，避免几千个点糊成一团
    const stride = Math.max(1, Math.floor(all.length / 40))
    return all.filter((_, i) => i % stride === 0)
  }
  return all.filter(p => p.x <= cut)
}

/** 动画头部点（连续描绘用） */
const functionsWithHead = computed(() => props.functions.map(f => {
  const out = { ...f }
  if (props.progress === null || !f.sampled || f.visible === false) {
    out.animHead = null
    return out
  }
  const cut = progressX.value
  let head = null
  for (const seg of f.sampled.segments) {
    for (let i = 1; i < seg.length; i++) {
      const a = seg[i - 1], b = seg[i]
      if (a.x <= cut && b.x >= cut) {
        const t = (cut - a.x) / (b.x - a.x || 1)
        head = { x: cut, y: a.y + (b.y - a.y) * t }
        break
      }
      if (a.x <= cut) head = a
    }
    if (head) break
  }
  out.animHead = props.animMode === 'trace' ? head : null
  return out
}))

const allAsymptotes = computed(() =>
  props.functions
    .filter(f => f.visible !== false && f.features)
    .flatMap(f => f.features.asymptotes || []))

/* ------------------------------------------------------------ 交互：缩放 / 平移 / 探针 */

const probeX = ref(null)

const probeDots = computed(() => {
  if (probeX.value === null) return []
  return props.functions
    .filter(f => f.visible !== false && f.fn)
    .map(f => {
      let y
      try { y = f.fn(probeX.value, f.scope || {}) } catch { y = NaN }
      return { id: f.id, color: f.color, x: probeX.value, y, label: f.expr }
    })
})

function shortLabel(f) {
  const s = String(f.expr || '')
  return s.length > 16 ? s.slice(0, 15) + '…' : s
}

function localPos(e) {
  const r = hostRef.value.getBoundingClientRect()
  return { px: e.clientX - r.left, py: e.clientY - r.top }
}

function inPlot(px, py) {
  return px >= pad.l && px <= pad.l + plotW.value && py >= pad.t && py <= pad.t + plotH.value
}

function onWheel(e) {
  const { px, py } = localPos(e)
  if (!inPlot(px, py)) return
  const factor = e.deltaY > 0 ? 1.12 : 1 / 1.12
  const vp = props.viewport
  const cx = ix(px)
  const cy = (() => {
    const t = (py - pad.t) / (plotH.value || 1)
    return vp.yMax - t * (vp.yMax - vp.yMin)
  })()
  emit('update:viewport', {
    xMin: cx - (cx - vp.xMin) * factor,
    xMax: cx + (vp.xMax - cx) * factor,
    yMin: cy - (cy - vp.yMin) * factor,
    yMax: cy + (vp.yMax - cy) * factor,
  })
}

let drag = null
function onMouseDown(e) {
  const { px, py } = localPos(e)
  if (!inPlot(px, py)) return
  drag = { px, py, vp: { ...props.viewport }, moved: false }
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  const { px, py } = localPos(e)
  // 探针始终跟随（拖动时暂停更新，避免与平移打架）
  if (!drag) {
    if (inPlot(px, py)) {
      probeX.value = ix(px)
      emit('probe', probeX.value)
    }
    return
  }
  const dx = px - drag.px
  const dy = py - drag.py
  if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true
  const sxPerPx = (drag.vp.xMax - drag.vp.xMin) / (plotW.value || 1)
  const syPerPx = (drag.vp.yMax - drag.vp.yMin) / (plotH.value || 1)
  emit('update:viewport', {
    xMin: drag.vp.xMin - dx * sxPerPx,
    xMax: drag.vp.xMax - dx * sxPerPx,
    yMin: drag.vp.yMin + dy * syPerPx,
    yMax: drag.vp.yMax + dy * syPerPx,
  })
}

function onMouseUp() {
  drag = null
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

defineExpose({ sx, sy })
</script>

<style scoped>
.plot-host {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 240px;
  background: var(--bg-secondary);
  cursor: crosshair;
  user-select: none;
}
.plot-svg { display: block; }

.grid-line { stroke: var(--border-light); stroke-width: 1; opacity: 0.55; }
.grid-line.major { stroke: var(--border); opacity: 0.9; }
.axis-line { stroke: var(--text-secondary); stroke-width: 1.2; }
.axis-arrow { fill: none; stroke: var(--text-secondary); stroke-width: 1.2; stroke-linecap: round; }
.tick-label { font-size: var(--fs-xs); fill: var(--text-muted); font-family: var(--font-mono); }
.axis-name { font-size: var(--fs-sm); fill: var(--text-secondary); font-style: italic; }

.curve-line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.curve-ghost { fill: none; stroke-width: 2; opacity: 0.13; stroke-linejoin: round; }
.curve-dot { opacity: 0.85; }
.head-dot { stroke: #fff; stroke-width: 1.5; }
.guide-line { stroke-width: 1; stroke-dasharray: 3 3; opacity: 0.5; }

.asym-line { stroke: var(--warning); stroke-width: 1.2; stroke-dasharray: 5 4; opacity: 0.75; }
.feat-zero { fill: var(--bg-secondary); stroke: var(--accent); stroke-width: 1.6; }
.feat-extremum { fill: var(--amber); stroke: #fff; stroke-width: 1.2; }

.probe-line { stroke: var(--text-muted); stroke-width: 1; stroke-dasharray: 2 3; }
.probe-dot { stroke: #fff; stroke-width: 1.5; }

.probe-readout {
  position: absolute;
  top: 8px;
  min-width: 168px;
  padding: 7px 9px;
  background: var(--bg-glass-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(6px);
  pointer-events: none;
  font-size: var(--fs-sm);
}
.pr-x { font-family: var(--font-mono); color: var(--text-primary); margin-bottom: 3px; }
.pr-row { display: flex; align-items: center; gap: 6px; line-height: 1.7; }
.pr-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pr-expr {
  flex: 1; min-width: 0; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pr-val { font-family: var(--font-mono); color: var(--text-primary); font-weight: 600; }

.plot-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: var(--fs-md);
  pointer-events: none;
}
</style>
