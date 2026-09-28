<template>
  <div class="bgc-view">
    <!-- ==================== 顶部：场景快捷 + 主要动作 ==================== -->
    <header class="bgc-head">
      <div class="bgc-title">
        <h2>背景 CSS 生成器</h2>
        <p>
          用一句自然语言描述需求，自动分析图片、匹配断点，生成可直接粘贴的 CSS。
          <span class="bgc-offline">本地解析 · 不联网 · 不调用外部模型</span>
        </p>
      </div>
      <div class="bgc-head-actions">
        <button type="button" class="bgc-btn" @click="fillRandomExample">换一个例子</button>
        <button
          type="button"
          class="bgc-btn bgc-btn-primary"
          :disabled="!result"
          @click="copyCss"
        >
          {{ copied ? '已复制' : '复制 CSS' }}
        </button>
      </div>
    </header>

    <div class="bgc-body">
      <!-- ==================== 左：输入与判定 ==================== -->
      <section class="bgc-panel bgc-input">
        <h3 class="bgc-panel-title">1 · 图片与描述</h3>

        <!-- 图片地址 -->
        <label class="bgc-label" for="bgc-url">图片地址</label>
        <div class="bgc-row">
          <input
            id="bgc-url"
            v-model="url"
            class="bgc-input-el"
            type="text"
            placeholder="https://… 图片地址，或直接写 linear-gradient(...)"
            spellcheck="false"
          />
          <label class="bgc-btn bgc-btn-file" title="选本地图片：不受跨域限制，可以做像素分析">
            本地图
            <input type="file" accept="image/*" hidden @change="onPickLocal" />
          </label>
        </div>

        <div class="bgc-url-state">
          <span v-if="isGradient" class="bgc-badge bgc-badge-info">CSS 渐变（无需图片分析）</span>
          <span v-else-if="analyzing" class="bgc-badge">读取图片中…</span>
          <span v-else-if="loadError" class="bgc-badge bgc-badge-danger">图片打不开：{{ loadError }}</span>
          <span v-else-if="analysis" class="bgc-badge bgc-badge-ok">
            {{ analysis.width }}×{{ analysis.height }}
            · 比例 {{ analysis.ratio.toFixed(2) }}
            <template v-if="analysis.pixels">· 已分析像素</template>
            <template v-else-if="analysis.tainted">· 跨域，读不到像素</template>
          </span>
          <span v-else class="bgc-badge bgc-badge-muted">等待图片</span>
          <button v-if="isLocalFile" type="button" class="bgc-clear" @click="clearLocal">改用网络地址</button>
        </div>

        <!-- 高分屏双图源：只有描述里提到才出现，免得平时占地方 -->
        <div v-if="intent.hiDpi" class="bgc-row bgc-gap-top">
          <input
            v-model="url2x"
            class="bgc-input-el bgc-input-sm"
            type="text"
            placeholder="2x 图地址（高分屏用，可选；留空则只输出 1x）"
            spellcheck="false"
          />
        </div>

        <!-- 描述 -->
        <label class="bgc-label" for="bgc-desc">用一句话描述需求</label>
        <textarea
          id="bgc-desc"
          v-model="desc"
          class="bgc-textarea"
          rows="3"
          spellcheck="false"
          placeholder="例：全屏英雄区背景图，铺满不留白，标题在底部，不要裁到主体"
        />

        <div class="bgc-chips">
          <button
            v-for="s in SCENARIOS"
            :key="s.key"
            type="button"
            class="bgc-chip"
            :class="{ active: desc === s.text }"
            :title="s.why"
            @click="desc = s.text"
          >{{ s.label }}</button>
        </div>

        <details class="bgc-details">
          <summary>能听懂哪些说法</summary>
          <dl class="bgc-vocab">
            <div v-for="g in VOCAB" :key="g.k">
              <dt>{{ g.k }}</dt>
              <dd>{{ g.v }}</dd>
            </div>
          </dl>
        </details>

        <!-- 判定结果 -->
        <h3 class="bgc-panel-title bgc-mt">2 · 判定结果</h3>
        <div class="bgc-slots">
          <div v-for="s in slotList" :key="s.k" class="bgc-slot">
            <span class="bgc-slot-k">{{ s.k }}</span>
            <span class="bgc-slot-v" :class="{ locked: s.locked }">{{ s.v }}</span>
          </div>
        </div>

        <!-- 手动覆盖 -->
        <div class="bgc-override">
          <div class="bgc-override-head">
            <span>手动调整</span>
            <button v-if="hasOverride" type="button" class="bgc-clear" @click="resetOverrides">恢复为描述判定</button>
          </div>
          <div class="bgc-field">
            <span>填充方式</span>
            <select :value="effFill" class="bgc-select" @change="ovFill = $event.target.value">
              <option value="cover">铺满裁剪 cover</option>
              <option value="contain">完整显示 contain</option>
              <option value="stretch">拉伸铺满 100% 100%</option>
              <option value="repeat">平铺 repeat</option>
              <option value="repeat-x">横向平铺 repeat-x</option>
              <option value="repeat-y">纵向平铺 repeat-y</option>
            </select>
          </div>
          <div class="bgc-field">
            <span>整屏高</span>
            <label class="bgc-switch">
              <input type="checkbox" :checked="effFullscreen" @change="ovFullscreen = $event.target.checked" />
              <i />
            </label>
          </div>
          <div class="bgc-field">
            <span>文字遮罩</span>
            <label class="bgc-switch">
              <input type="checkbox" :checked="effOverlay" @change="ovOverlay = $event.target.checked" />
              <i />
            </label>
          </div>
          <div v-if="effOverlay" class="bgc-field">
            <span>遮罩强度</span>
            <input
              type="range" min="0.1" max="0.9" step="0.05"
              :value="effStrength"
              class="bgc-range"
              @input="ovStrength = Number($event.target.value)"
            />
            <em>{{ Math.round(effStrength * 100) }}%</em>
          </div>
          <div class="bgc-field">
            <span>响应式</span>
            <select :value="effStrategy" class="bgc-select" @change="ovStrategy = $event.target.value">
              <option value="mobile-first">移动端优先（min-width）</option>
              <option value="desktop-first">桌面优先（max-width）</option>
            </select>
          </div>
          <div class="bgc-field">
            <span>类名</span>
            <input
              v-model="ovClassName"
              class="bgc-input-el bgc-input-sm"
              type="text"
              :placeholder="intent.className"
              spellcheck="false"
            />
          </div>
        </div>

        <!-- 判定依据 -->
        <details v-if="result?.reasons?.length" class="bgc-details" open>
          <summary>判定依据（{{ result.reasons.length }} 条）</summary>
          <ul class="bgc-reasons">
            <li v-for="(r, i) in result.reasons" :key="i">{{ r }}</li>
          </ul>
        </details>
      </section>

      <!-- ==================== 中：实时预览 ==================== -->
      <section class="bgc-panel bgc-preview">
        <h3 class="bgc-panel-title">
          3 · 实时预览
          <em class="bgc-panel-sub">{{ currentDevice.label }} {{ currentDevice.w }}×{{ currentDevice.h }}</em>
        </h3>

        <div class="bgc-devices">
          <button
            v-for="d in DEVICES"
            :key="d.key"
            type="button"
            class="bgc-chip"
            :class="{ active: device === d.key }"
            :title="d.hint"
            @click="device = d.key"
          >{{ d.label }}</button>
        </div>

        <div ref="frameWrap" class="bgc-frame-box">
          <div v-if="isGradient" class="bgc-frame-hint">渐变背景不需要图片，右侧直接取代码即可</div>
          <iframe
            v-else
            ref="frame"
            class="bgc-frame"
            title="背景预览"
            :srcdoc="previewDoc"
            :style="frameStyle"
            @load="measure"
          />
        </div>

        <div class="bgc-readout">
          <template v-if="forecast">
            <div class="bgc-readout-row">
              <span>视口</span>
              <b>{{ currentDevice.w }} × {{ currentDevice.h }}</b>
              <span class="bgc-readout-tag">实际渲染 {{ Math.round(scale * 100) }}%</span>
            </div>
            <div v-if="intent.fill === 'cover'" class="bgc-readout-row">
              <span>裁剪</span>
              <b :class="{ warn: forecast.lost > 0.4 }">
                {{ forecast.lost < 0.005 ? '无裁剪' : `裁掉 ${Math.round(forecast.lost * 100)}% 的${forecast.axis === 'vertical' ? '高度' : '宽度'}` }}
              </b>
            </div>
            <div v-else-if="intent.fill === 'contain'" class="bgc-readout-row">
              <span>留白</span>
              <b :class="{ warn: forecast.emptyArea > 0.4 }">
                {{ forecast.emptyArea < 0.005 ? '无留白' : `留出 ${Math.round(forecast.emptyArea * 100)}% 空白` }}
              </b>
            </div>
            <div class="bgc-readout-row">
              <span>元素高度</span>
              <b :class="{ warn: measured.shortfall > 0 }">
                {{ measured.elementHeight }}px
                {{ measured.shortfall > 0 ? `（下方还有 ${measured.shortfall}px 未覆盖）` : '· 铺满视口' }}
              </b>
            </div>
          </template>
          <div v-else class="bgc-readout-row bgc-readout-empty">
            填入图片地址后这里会给出实测数据
          </div>
        </div>
      </section>

      <!-- ==================== 右：代码与风险 ==================== -->
      <section class="bgc-panel bgc-code-panel">
        <h3 class="bgc-panel-title">4 · 生成的代码</h3>

        <pre class="bgc-code"><code>{{ result ? result.css : '（填入图片地址与描述后生成）' }}</code></pre>

        <div v-if="result?.warnings?.length" class="bgc-warns">
          <div class="bgc-warns-head">
            需要注意（{{ result.warnings.length }} 条）
          </div>
          <ul>
            <li v-for="(w, i) in result.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>
        <div v-else-if="result" class="bgc-ok-note">
          这张图在常见设备上都不至于被裁得太狠，没发现需要提醒的地方。
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * 背景 CSS 生成器（工具页）
 * ========================
 * 三栏布局：左「输入与判定」、中「实时预览」、右「代码与风险」。
 *
 * 几个刻意的实现选择：
 *
 * 1. **预览用 iframe srcdoc，而不是 div 模拟**。
 *    生成的 CSS 原样注入 iframe，media query 会按 iframe 的真实宽度真正生效——
 *    切设备就等于真的换了视口，这才叫「验证」。div 模拟做不到这一点。
 *    srcdoc 与父页面同源，所以还能读回元素的**实测高度**显示在下方读数里。
 *
 * 2. **图片加载两遍**。
 *    第一遍不加 crossOrigin（保证一定能显示、拿到尺寸）；
 *    第二遍加 crossOrigin='anonymous' 尝试拿像素做分析。
 *    只加载一遍并带上 crossOrigin 的话，服务端没发 CORS 头的图会**整张加载失败**——
 *    为了分析像素而让图显示不出来，得不偿失。
 *
 * 3. **生成算两遍**。
 *    `result` 用真实意图（可能是「只要属性」模式）给用户复制；
 *    `previewResult` 强制带选择器，供预览使用。
 *    两个都是纯函数，多算一次的成本可以忽略，但省掉了一堆拼装特例。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseIntent, analyzeImage, generateCss, cropForecast, DEVICES, SCENARIOS,
} from '@/utils/backgroundCss'

/* ---------------------------------------------------------------- 状态 */

const url = ref('')
const url2x = ref('')
const desc = ref(SCENARIOS[0].text)
const device = ref('laptop')
const analysis = ref(null)
const analyzing = ref(false)
const loadError = ref('')
const isLocalFile = ref(false)
const copied = ref(false)

const ovFill = ref('')
const ovFullscreen = ref(null)
const ovOverlay = ref(null)
const ovStrength = ref(null)
const ovStrategy = ref('')
const ovClassName = ref('')

const frame = ref(null)
const frameWrap = ref(null)
const scale = ref(1)
const boxW = ref(0)
const boxH = ref(0)
const measured = ref({ elementHeight: 0, shortfall: 0, viewport: 0 })

const isGradient = computed(() =>
  /gradient\(|^\s*#|^\s*rgba?\(|^\s*hsla?\(/i.test(url.value.trim()))

const currentDevice = computed(() => DEVICES.find((d) => d.key === device.value) || DEVICES[3])

/* ---------------------------------------------------------------- 生成 */

const intent = computed(() => parseIntent(desc.value))

const override = computed(() => {
  const o = {}
  if (ovFill.value) o.fill = ovFill.value
  if (ovFullscreen.value !== null) o.fullscreen = ovFullscreen.value
  if (ovOverlay.value !== null) o.overlay = ovOverlay.value
  if (ovStrength.value !== null) o.overlayStrength = ovStrength.value
  if (ovStrategy.value) o.strategy = ovStrategy.value
  if (ovClassName.value.trim()) o.className = ovClassName.value.trim()
  return o
})

const hasOverride = computed(() => Object.keys(override.value).length > 0)

/** 给用户复制用：按真实意图生成（可能是「只要属性」模式） */
const result = computed(() => generateCss({
  url: url.value.trim(),
  url2x: url2x.value.trim(),
  intent: intent.value,
  analysis: analysis.value,
  override: override.value,
}))

/** 供预览用：强制带选择器，否则裸属性模式下预览框里什么都看不到 */
const previewResult = computed(() => generateCss({
  url: url.value.trim(),
  url2x: url2x.value.trim(),
  intent: { ...intent.value, bare: false },
  analysis: analysis.value,
  override: override.value,
}))

/* 手动调整时，界面要显示「当前生效值」，而不是用户点过的值 */
const effFill = computed(() => ovFill.value || intent.value.fill)
const effFullscreen = computed(() => (ovFullscreen.value !== null ? ovFullscreen.value : intent.value.fullscreen))
const effOverlay = computed(() => (ovOverlay.value !== null ? ovOverlay.value : intent.value.overlay))
const effStrength = computed(() => (ovStrength.value !== null ? ovStrength.value : intent.value.overlayStrength))
const effStrategy = computed(() => ovStrategy.value || intent.value.strategy)

const slotList = computed(() => {
  const it = intent.value
  const label = (k, v, locked = false) => ({ k, v, locked })
  return [
    label('场景', USAGE_TEXT[it.usage] || it.usage),
    label('填充', FILL_TEXT[effFill.value] || effFill.value),
    label('高度', effFullscreen.value ? '整屏高' : it.height ? it.height.label : '自适应'),
    label('焦点', it.focalLocked ? `${FOCAL_TEXT[it.focal] || it.focal}（按描述）` : '按图片重心自动', it.focalLocked),
    label('遮罩', effOverlay.value ? `开 · ${Math.round(effStrength.value * 100)}%` : '关'),
    label('响应式', effStrategy.value === 'mobile-first' ? '移动端优先' : '桌面优先'),
    label('类名', `.${result.value?.className || it.className}`),
  ]
})

const forecast = computed(() => {
  const r = analysis.value?.ratio
  if (!r || isGradient.value) return null
  return cropForecast(r, currentDevice.value.w / currentDevice.value.h)
})

/* ---------------------------------------------------------------- 预览 */

const previewDoc = computed(() => {
  const css = previewResult.value?.css || ''
  const it = intent.value
  const cls = previewResult.value?.className || 'bg-image'
  const justify = it.textPos === 'top' ? 'flex-start'
    : it.textPos === 'center' ? 'center' : 'flex-end'
  const align = it.textPos === 'left' ? 'flex-start'
    : it.textPos === 'right' ? 'flex-end' : 'center'

  return `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; }
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    /* 未被元素覆盖的区域用条纹标示出来，能直接看出 contain 的留白 */
    background-color: ${it.fullscreen ? '#1a1d23' : '#2a2e36'};
    background-image: repeating-linear-gradient(45deg,
      rgba(255,255,255,.045) 0 8px, transparent 8px 16px);
  }
${css}
  /* 演示内容：让文字压在图上，才能检查可读性 */
  .${cls} { display: flex; flex-direction: column; }
  .bgc-demo-inner {
    position: relative; z-index: 1; flex: 1;
    display: flex; flex-direction: column;
    justify-content: ${justify}; align-items: ${align};
    text-align: ${align === 'flex-start' ? 'left' : align === 'flex-end' ? 'right' : 'center'};
    gap: 10px; padding: 30px 26px;
  }
  .bgc-demo-inner h1 {
    margin: 0; font-size: 26px; font-weight: 700; letter-spacing: .5px;
    color: #fff; text-shadow: 0 1px 10px rgba(0,0,0,.35);
  }
  .bgc-demo-inner p {
    margin: 0; max-width: 34em; font-size: 14px; line-height: 1.7;
    color: rgba(255,255,255,.92); text-shadow: 0 1px 8px rgba(0,0,0,.35);
  }
  .bgc-demo-btn {
    display: inline-block; padding: 9px 20px; border-radius: 8px;
    background: rgba(255,255,255,.94); color: #1c2027;
    font-size: 13px; font-weight: 600;
  }
</style></head>
<body>
  <!-- id 是给外层 measure() 用的：靠类名匹配会误命中或匹配不到（如 hero-bg 里没有 bg- 子串） -->
  <div id="bgc-demo" class="${cls}">
    <div class="bgc-demo-inner">
      <h1>主标题写在这里</h1>
      <p>这段正文用来检查文字压在图片上的可读性。如果看不清，就在描述里加「要遮罩」。</p>
      <span class="bgc-demo-btn">开始使用</span>
    </div>
  </div>
</body></html>`
})

const frameStyle = computed(() => {
  const d = currentDevice.value
  const left = Math.max(0, (boxW.value - d.w * scale.value) / 2)
  const top = Math.max(0, (boxH.value - d.h * scale.value) / 2)
  return {
    width: d.w + 'px',
    height: d.h + 'px',
    left: left + 'px',
    top: top + 'px',
    transform: `scale(${scale.value})`,
    transformOrigin: '0 0',
  }
})

function fit() {
  const box = frameWrap.value?.getBoundingClientRect()
  if (!box || !box.width) return
  boxW.value = box.width
  boxH.value = box.height
  const d = currentDevice.value
  // 留 2px 余量，避免出现滚动条
  scale.value = Math.max(0.1, Math.min(1, (box.width - 2) / d.w, (box.height - 2) / d.h))
}

/**
 * 读 iframe 里的**实测**高度——这是「验证」，不是拿公式再算一遍。
 *
 * 注意：**不要除以 scale**。外侧那个 transform: scale() 作用在 <iframe> 元素上，
 * 而 iframe 内部的文档有自己独立的 CSS 像素坐标系，
 * 内部的 getBoundingClientRect() 返回的就是真实 CSS 像素，不受父级缩放影响。
 * 早期版本多除了一个 scale，768px 的高度被读成 2979px。
 */
function measure() {
  const doc = frame.value?.contentDocument
  if (!doc) return
  const el = doc.querySelector('#bgc-demo')
  const vp = currentDevice.value.h
  const h = el ? Math.round(el.getBoundingClientRect().height) : 0
  measured.value = { elementHeight: h, shortfall: Math.max(0, vp - h), viewport: vp }
}

/* ---------------------------------------------------------------- 图片加载 */

/** 加载一张图；crossOrigin 为 true 时用于取像素（可能因未发 CORS 头而失败） */
function loadImg(src, crossOrigin, timeout = 12000) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    // 只对真正跨源的 http(s) 地址设 crossOrigin：
    // data: / blob: 本身同源，设了没有意义，个别浏览器反而会因此加载失败。
    if (crossOrigin && /^https?:/i.test(src)) img.crossOrigin = 'anonymous'
    let settled = false
    const timer = setTimeout(() => {
      if (!settled) { settled = true; reject(new Error('加载超时')) }
    }, timeout)
    img.onload = () => { if (!settled) { settled = true; clearTimeout(timer); resolve(img) } }
    img.onerror = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(new Error(crossOrigin ? '该图未开放跨域读取' : '图片加载失败'))
    }
    img.src = src
  })
}

let analyzeTimer = null
let analyzeSeq = 0

async function analyzeUrl() {
  const u = url.value.trim()
  const seq = ++analyzeSeq
  loadError.value = ''
  if (!u || isGradient.value) { analysis.value = null; analyzing.value = false; return }

  analyzing.value = true
  try {
    // 第一遍：不加 crossOrigin，确保图一定显示得出来、尺寸一定拿得到。
    // 只加载一遍并带 crossOrigin 的话，服务端没发 CORS 头的图会整张加载失败 ——
    // 为了分析像素而让图显示不出来，得不偿失。
    const plain = await loadImg(u, false)
    if (seq !== analyzeSeq) return
    const base = {
      width: plain.naturalWidth,
      height: plain.naturalHeight,
      ratio: plain.naturalWidth / plain.naturalHeight,
      ok: true,
    }
    if (!/^https?:/i.test(u)) {
      // data: / blob: 同源，直接用第一遍的图分析，省掉一次重复加载
      const full = await analyzeImage(plain)
      if (seq !== analyzeSeq) return
      analysis.value = full?.ok ? full : { ...base, pixels: null }
    } else {
      // 第二遍：加 crossOrigin 拿像素；失败就降级成「只有尺寸」
      try {
        const cors = await loadImg(u, true)
        if (seq !== analyzeSeq) return
        const full = await analyzeImage(cors)
        analysis.value = full?.ok ? full : { ...base, pixels: null }
      } catch {
        if (seq !== analyzeSeq) return
        analysis.value = { ...base, pixels: null, tainted: true }
      }
    }
  } catch (e) {
    if (seq !== analyzeSeq) return
    analysis.value = null
    loadError.value = e.message || String(e)
  } finally {
    if (seq === analyzeSeq) analyzing.value = false
  }
}

function onPickLocal(e) {
  const file = e.target.files?.[0]
  if (!file) return
  if (url.value.startsWith('blob:')) URL.revokeObjectURL(url.value)
  isLocalFile.value = true
  url.value = URL.createObjectURL(file)
  e.target.value = ''
  ElMessage.success('已载入本地图片：不受跨域限制，能够分析主体位置')
}

function clearLocal() {
  if (url.value.startsWith('blob:')) URL.revokeObjectURL(url.value)
  isLocalFile.value = false
  url.value = ''
}

/* ---------------------------------------------------------------- 交互 */

async function copyCss() {
  const text = result.value?.css || ''
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1600)
  } catch {
    // 剪贴板 API 在非安全上下文 / 无权限时会失败，退回选中让用户自己复制
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      copied.value = true
      setTimeout(() => { copied.value = false }, 1600)
    } catch {
      ElMessage.warning('浏览器不允许自动复制，请手动选中右侧代码复制')
    }
    document.body.removeChild(ta)
  }
}

function resetOverrides() {
  ovFill.value = ''
  ovFullscreen.value = null
  ovOverlay.value = null
  ovStrength.value = null
  ovStrategy.value = ''
  ovClassName.value = ''
}

let exampleIdx = 0
function fillRandomExample() {
  exampleIdx = (exampleIdx + 1) % SCENARIOS.length
  desc.value = SCENARIOS[exampleIdx].text
}

/* ---------------------------------------------------------------- 生命周期 */

let ro = null

onMounted(async () => {
  await nextTick()
  fit()
  if (typeof ResizeObserver !== 'undefined' && frameWrap.value) {
    ro = new ResizeObserver(() => { fit(); measure() })
    ro.observe(frameWrap.value)
  }
  if (!url.value) url.value = DEFAULT_URL
})

onBeforeUnmount(() => {
  ro?.disconnect()
  clearTimeout(analyzeTimer)
  if (url.value.startsWith('blob:')) URL.revokeObjectURL(url.value)
})

watch(url, () => {
  clearTimeout(analyzeTimer)
  analyzeTimer = setTimeout(analyzeUrl, 400)
}, { immediate: true })

watch(device, async () => { await nextTick(); fit(); setTimeout(measure, 260) })
watch(previewDoc, () => { setTimeout(measure, 320) })

/* ---------------------------------------------------------------- 文案表 */

const USAGE_TEXT = {
  hero: '全屏英雄区', banner: '横幅 / 通栏', card: '卡片 / 缩略图',
  pattern: '平铺图案', section: '区块背景', block: '普通背景块',
}
const FILL_TEXT = {
  cover: '铺满 cover', contain: '完整 contain', stretch: '拉伸',
  repeat: '平铺 repeat', 'repeat-x': '横向 repeat-x', 'repeat-y': '纵向 repeat-y',
}
const FOCAL_TEXT = {
  '50% 0%': '顶部', '50% 100%': '底部', '0% 50%': '左侧',
  '100% 50%': '右侧', '50% 50%': '居中',
}

const VOCAB = [
  { k: '场景', v: '英雄区 / 首屏、横幅 / 通栏、卡片 / 缩略图、底纹 / 纹理、区块 / 正文背景' },
  { k: '填充', v: '「铺满、填满、不留白」→ cover；「不拉伸、不变形、完整显示、不要裁剪」→ contain；「平铺、重复」→ repeat；「横向 / 纵向平铺」→ repeat-x / repeat-y' },
  { k: '高度', v: '「全屏、一屏高、满屏」→ 整屏高；「高 480px」「半屏」「两屏高」→ 显式高度' },
  { k: '焦点保护', v: '「不要裁到主体 / 别裁到人脸 / 保住 logo」→ 按图片细节重心自动定位 background-position' },
  { k: '焦点方位', v: '「主体在下方」「重点在左边」「重心偏右」→ 直接指定焦点（注意：「标题在底部」只决定文字位置）' },
  { k: '遮罩', v: '「要遮罩 / 压暗 / 文字要清楚 / 加一层渐变」→ 追加 ::after 覆盖层；「淡一点 / 重一点 / 遮罩 60%」控制强度' },
  { k: '响应式', v: '默认移动端优先（min-width 逐级增强）；说「桌面优先 / 大屏优先」则改用 max-width 降级' },
  { k: '其它', v: '「固定 / 视差」→ background-attachment: fixed；「暗色适配」→ prefers-color-scheme；「高分屏 / 2x」→ image-set；「类名 xxx」→ 指定选择器；「只要属性」→ 不包选择器' },
]

/**
 * 默认演示图：本地生成的 SVG data URI。
 *
 * 为什么不用网络图：图床失效或断网时首屏就是一条红色报错，太难看；
 * 而且跨域图读不到像素，「按主体重心自动定位」这个最核心的能力当场演示不出来。
 * data URI 一定加载成功、一定同源。
 *
 * 画面为什么长这样：左半是「月亮 + 一排明暗交替的岩脊」，右半只有平滑渐变。
 * 纯矢量画面细节太少，会被判成「细节分布均匀」而退回居中 —— 那就演示不出重心定位。
 * 岩脊的明暗块在缩到 128px 采样后仍留有可测的边缘，所以细节重心的确会偏左。
 * 而且它长得还算像一张图，不至于让人以为这是个色块测试页。
 */
function buildDemoSvg() {
  const ridges = []
  for (let i = 0; i < 13; i++) {
    const x = i * 62
    const top = 460 + (i % 3) * 88
    ridges.push(
      `<path d="M${x} 1080 L${x + 32} ${top} L${x + 62} 1080 Z" fill="${i % 2 === 0 ? '#243b52' : '#0a1017'}"/>`,
    )
  }
  return '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">'
    + '<defs>'
    + '<linearGradient id="sky" x1="0" y1="0" x2="0.4" y2="1">'
    + '<stop offset="0" stop-color="#2c4c6d"/><stop offset="0.55" stop-color="#7199b8"/><stop offset="1" stop-color="#2d4459"/>'
    + '</linearGradient>'
    + '<linearGradient id="rock" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0" stop-color="#22354a"/><stop offset="1" stop-color="#080d13"/>'
    + '</linearGradient>'
    + '</defs>'
    + '<rect width="1920" height="1080" fill="url(#sky)"/>'
    + '<circle cx="420" cy="300" r="240" fill="#f7e6c0" opacity="0.12"/>'
    + '<circle cx="420" cy="300" r="150" fill="#f7e6c0"/>'
    + ridges.join('')
    + '<path d="M980 1080 L1180 940 L1420 1000 L1700 930 L1920 985 L1920 1080 Z" fill="url(#rock)" opacity="0.42"/>'
    + '</svg>'
}

const DEFAULT_URL = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(buildDemoSvg())
</script>

<style scoped>
/* ===== 页面骨架 =====
   根容器保持透明（项目约定）：素材背景层要靠它透上来。 */
.bgc-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 14px 18px 16px;
}

.bgc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.bgc-title h2 {
  margin: 0 0 4px;
  font-size: var(--fs-lg);
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: .3px;
}
.bgc-title p {
  margin: 0;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}
.bgc-offline {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--success-soft);
  color: var(--success);
  font-size: var(--fs-xs);
  white-space: nowrap;
}
.bgc-head-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* ===== 三栏主体 =====
   grid-template-rows 的 minmax(0, 1fr) 不能省：隐式行会按内容撑高，
   把画布顶破后被父级 overflow:hidden 裁掉（函数图像页踩过这个坑）。 */
.bgc-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 340px) minmax(0, 1fr) minmax(340px, 430px);
  grid-template-rows: minmax(0, 1fr);
  gap: 12px;
}

.bgc-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  backdrop-filter: blur(14px) saturate(1.2);
  -webkit-backdrop-filter: blur(14px) saturate(1.2);
  overflow-y: auto;
  overflow-x: hidden;
}
.bgc-panel-title {
  margin: 0 0 10px;
  font-size: var(--fs-sm);
  font-weight: 650;
  color: var(--text-secondary);
  letter-spacing: .4px;
}
.bgc-mt { margin-top: 18px; }
.bgc-gap-top { margin-top: 8px; }
.bgc-panel-sub {
  margin-left: 8px;
  font-style: normal;
  font-weight: 400;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}

/* ===== 表单元素 ===== */
.bgc-label {
  display: block;
  margin: 10px 0 6px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.bgc-row { display: flex; gap: 8px; align-items: stretch; }

.bgc-input-el,
.bgc-textarea,
.bgc-select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: var(--fs-sm);
  font-family: inherit;
  transition: border-color var(--dur-fast) var(--ease-out);
}
.bgc-input-el:focus,
.bgc-textarea:focus,
.bgc-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.bgc-input-sm { padding: 5px 8px; font-size: var(--fs-xs); }
.bgc-textarea {
  resize: vertical;
  min-height: 62px;
  line-height: 1.6;
  font-size: var(--fs-sm);
}
.bgc-select { cursor: pointer; }

/* ===== 按钮 ===== */
.bgc-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--fs-sm);
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}
.bgc-btn:hover { background: var(--bg-hover); border-color: var(--accent); }
.bgc-btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}
.bgc-btn-primary:hover { background: var(--accent-strong); border-color: var(--accent-strong); }
.bgc-btn-primary:disabled { opacity: .45; cursor: not-allowed; }
.bgc-btn-file { flex-shrink: 0; cursor: pointer; }
.bgc-clear {
  border: none;
  background: none;
  padding: 0;
  color: var(--accent);
  font-size: var(--fs-xs);
  font-family: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* ===== 徽标与状态 ===== */
.bgc-url-state {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.bgc-badge {
  display: inline-block;
  padding: 2px 9px;
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
}
.bgc-badge-ok { background: var(--success-soft); color: var(--success); }
.bgc-badge-info { background: var(--accent-soft); color: var(--accent); }
.bgc-badge-danger { background: var(--danger-soft); color: var(--danger); }
.bgc-badge-muted { color: var(--text-muted); }

/* ===== 描述示例 ===== */
.bgc-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.bgc-chip {
  padding: 4px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  font-family: inherit;
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.bgc-chip:hover { border-color: var(--accent); color: var(--accent); }
.bgc-chip.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}

/* ===== 折叠说明 ===== */
.bgc-details {
  margin-top: 10px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}
.bgc-details > summary {
  cursor: pointer;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  list-style: none;
  user-select: none;
}
.bgc-details > summary:hover { color: var(--accent); }
.bgc-details > summary::-webkit-details-marker { display: none; }
.bgc-details > summary::before { content: '▸ '; color: var(--text-muted); }
.bgc-details[open] > summary::before { content: '▾ '; }

.bgc-vocab { margin: 8px 0 0; font-size: var(--fs-xs); line-height: 1.75; }
.bgc-vocab > div { display: flex; gap: 6px; margin-bottom: 5px; }
.bgc-vocab dt {
  flex-shrink: 0;
  width: 58px;
  color: var(--accent);
  font-weight: 600;
}
.bgc-vocab dd { margin: 0; color: var(--text-secondary); }

.bgc-reasons {
  margin: 8px 0 0;
  padding-left: 0;
  list-style: none;
  font-size: var(--fs-xs);
  line-height: 1.75;
  color: var(--text-secondary);
}
.bgc-reasons li { padding-left: 12px; position: relative; margin-bottom: 3px; }
.bgc-reasons li::before {
  content: '·';
  position: absolute;
  left: 2px;
  color: var(--accent);
  font-weight: 700;
}

/* ===== 判定槽位 ===== */
.bgc-slots { display: flex; flex-direction: column; gap: 5px; }
.bgc-slot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 9px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  font-size: var(--fs-xs);
}
.bgc-slot-k {
  flex-shrink: 0;
  width: 48px;
  color: var(--text-muted);
}
.bgc-slot-v {
  flex: 1;
  min-width: 0;
  color: var(--text-primary);
  font-weight: 550;
  word-break: break-word;
}
.bgc-slot-v.locked { color: var(--accent); }

/* ===== 手动覆盖 ===== */
.bgc-override {
  margin-top: 14px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
}
.bgc-override-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.bgc-field {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.bgc-field > span:first-child { flex-shrink: 0; width: 62px; }
.bgc-field em { font-style: normal; color: var(--text-muted); width: 34px; }
.bgc-range { flex: 1; min-width: 0; accent-color: var(--accent); }

.bgc-switch { display: inline-flex; cursor: pointer; }
.bgc-switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.bgc-switch i {
  width: 34px;
  height: 18px;
  border-radius: 9px;
  background: var(--bg-tertiary);
  position: relative;
  transition: background var(--dur-fast) var(--ease-out);
}
.bgc-switch i::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: transform var(--dur-fast) var(--ease-out);
}
.bgc-switch input:checked + i { background: var(--accent); }
.bgc-switch input:checked + i::after { transform: translateX(16px); }
.bgc-switch input:focus-visible + i { box-shadow: 0 0 0 3px var(--accent-soft); }

/* ===== 预览 ===== */
.bgc-devices { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }

.bgc-frame-box {
  position: relative;
  flex: 1;
  min-height: 200px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-deep);
  overflow: hidden;
}
.bgc-frame {
  position: absolute;
  border: 0;
  display: block;
  background: transparent;
}
.bgc-frame-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}

.bgc-readout {
  margin-top: 10px;
  padding: 9px 11px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  font-size: var(--fs-xs);
}
.bgc-readout-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
  line-height: 1.6;
}
.bgc-readout-row > span:first-child {
  flex-shrink: 0;
  width: 56px;
  color: var(--text-muted);
}
.bgc-readout-row b {
  color: var(--text-primary);
  font-weight: 600;
  font-family: var(--font-mono);
}
.bgc-readout-row b.warn { color: var(--warning); }
.bgc-readout-tag { color: var(--text-faint); margin-left: auto; }
.bgc-readout-empty { color: var(--text-muted); }

/* ===== 代码 =====
   不写 overflow: hidden（那会裁掉下方的风险提示），
   交给 .bgc-panel 的 overflow-y: auto 统一滚动，代码块自己也能内部滚动。 */
.bgc-code-panel { min-height: 0; }
.bgc-code {
  flex: 1;
  min-height: 160px;
  margin: 0;
  padding: 11px 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--bg-deep);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: auto;
  tab-size: 2;
}
.bgc-warns {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--warning);
  border-left-width: 4px;
  border-radius: var(--radius-sm);
  background: var(--warning-soft);
}
.bgc-warns-head {
  font-size: var(--fs-xs);
  font-weight: 650;
  color: var(--warning);
  margin-bottom: 5px;
}
.bgc-warns ul {
  margin: 0;
  padding-left: 16px;
  font-size: var(--fs-xs);
  line-height: 1.75;
  color: var(--text-primary);
}
.bgc-warns li { margin-bottom: 4px; }
.bgc-ok-note {
  margin-top: 12px;
  padding: 9px 12px;
  border-left: 3px solid var(--success);
  border-radius: var(--radius-sm);
  background: var(--success-soft);
  color: var(--success);
  font-size: var(--fs-xs);
  line-height: 1.7;
}

/* ===== 自适应：窄屏折叠为两栏 / 单栏 =====

   行高必须写成「有上限的比例」，不能写 auto：
   `grid-template-rows: minmax(0,1fr) auto` 里 auto 行会先按内容把高度吃掉，
   1fr 只剩 0 —— 实测输入栏和预览栏被压成 30px（只剩内边距），
   整页看起来像「只有代码面板」。minmax(0, 38%) 给了明确的收缩空间，
   第一行才有余量，同时代码区仍在可视范围内（面板内部自己滚动）。 */
@media (max-width: 1360px) {
  .bgc-body {
    grid-template-columns: minmax(280px, 320px) minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 38%);
  }
  .bgc-code-panel { grid-column: 1 / -1; }
  .bgc-code { min-height: 120px; }
}

/* 单栏时不再强行把三块塞进一屏：让 bgc-view 自己滚，
   每块按内容自然高度排布。屏幕又窄又矮还硬分三行，每行只剩一百来像素，没法用。 */
@media (max-width: 900px) {
  .bgc-view { overflow-y: auto; }
  .bgc-body {
    display: flex;
    flex-direction: column;
    flex: none;
    min-height: 0;
    gap: 10px;
  }
  .bgc-panel { flex: none; overflow: visible; }
  .bgc-input, .bgc-code-panel { grid-column: auto; }
  .bgc-frame-box { height: 330px; min-height: 330px; }
  .bgc-view { padding: 12px 12px 14px; }
}
</style>
