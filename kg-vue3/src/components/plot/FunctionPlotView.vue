<template>
  <div class="fp-view">
    <header class="fp-head">
      <div class="fp-head-text">
        <h2>函数图像</h2>
        <p>输入任意函数看曲线，并可回放它「怎么被画出来」——连续描绘、描点取点、逐步求值。</p>
      </div>
      <div class="fp-head-actions">
        <label class="fp-range">
          <span>x 范围</span>
          <el-input v-model.number="xRangeInput.min" size="small" class="fp-range-input" />
          <span class="fp-range-sep">~</span>
          <el-input v-model.number="xRangeInput.max" size="small" class="fp-range-input" />
          <el-button size="small" @click="applyXRange">应用</el-button>
        </label>
        <el-button size="small" @click="fitY" :disabled="!hasCurve">适应窗口</el-button>
        <el-button size="small" @click="openCatalog">函数速查</el-button>
        <el-button size="small" @click="exportSvg">导出 SVG</el-button>
      </div>
    </header>

    <div class="fp-body">
      <!-- ==================== 左：函数与参数 ==================== -->
      <aside class="fp-left">
        <section class="fp-block">
          <div class="fp-block-head">
            <h3>函数</h3>
            <el-button size="small" text type="primary" @click="addFunction">+ 添加</el-button>
          </div>

          <div class="fp-func-list">
            <div v-for="f in funcs" :key="f.id"
                 class="fp-func" :class="{ active: f.id === activeId, hidden: !f.visible }">
              <div class="ff-row">
                <button class="ff-color" :style="{ background: f.color }"
                        :title="`切换第 ${f.index + 1} 条曲线的显示`"
                        @click="f.visible = !f.visible"></button>
                <el-input v-model="f.expr" size="small" placeholder="例如 2*sin(x) + 1"
                          class="ff-input" spellcheck="false"
                          @focus="activeId = f.id" @input="onExprInput(f)" />
                <button class="ff-del" title="删除" @click="removeFunction(f.id)"
                        :disabled="funcs.length <= 1">×</button>
              </div>

              <div v-if="f.error" class="ff-error">
                <span class="ff-error-mark">!</span>{{ f.error }}
              </div>

              <!-- 归一化后的实际解析式：让"我写的"和"系统理解的"对得上 -->
              <div v-else-if="f.expr && f.normalized && f.normalized !== f.expr"
                   class="ff-norm">
                解析为 <code>{{ f.normalized }}</code>
              </div>

              <div v-if="!f.error && f.params && f.params.length" class="ff-params">
                <div v-for="p in f.params" :key="p" class="ff-param">
                  <span class="fp-name">{{ p }}</span>
                  <el-slider v-model="f.scope[p]" :min="paramRange(f, p).min"
                             :max="paramRange(f, p).max" :step="paramRange(f, p).step"
                             size="small" :show-tooltip="false" />
                  <span class="fp-val">{{ round2(f.scope[p]) }}</span>
                </div>
                <div class="ff-param-hint">拖动参数即可看到曲线连续变形——这就是参数如何"形成"图形</div>
              </div>
            </div>
          </div>
        </section>

        <section class="fp-block">
          <div class="fp-block-head"><h3>快速示例</h3></div>
          <div class="fp-presets">
            <button v-for="p in PRESETS" :key="p.label" class="fp-preset"
                    :title="p.expr" @click="usePreset(p)">
              {{ p.label }}
            </button>
          </div>
        </section>

        <section class="fp-block">
          <div class="fp-block-head"><h3>显示选项</h3></div>
          <div class="fp-toggles">
            <label><el-switch v-model="show.grid" size="small" />网格</label>
            <label><el-switch v-model="show.features" size="small" />零点 / 极值</label>
            <label><el-switch v-model="show.asymptotes" size="small" />渐近线</label>
            <label><el-switch v-model="show.autoY" size="small" />纵向自适应</label>
          </div>
        </section>
      </aside>

      <!-- ==================== 中：绘图 + 形成过程控制条 ==================== -->
      <main class="fp-main">
        <div ref="canvasWrapRef" class="fp-canvas">
          <PlotCanvas
            :functions="plotFunctions"
            :viewport="viewport"
            :show-grid="show.grid"
            :show-features="show.features"
            :show-asymptotes="show.asymptotes"
            :progress="anim.playing || anim.progress < 1 ? anim.progress : null"
            :anim-mode="anim.mode"
            :probe-visible="true"
            @update:viewport="onViewportChange"
            @probe="onProbe"
          />
        </div>

        <div class="fp-anim">
          <div class="fp-anim-left">
            <el-button size="small" type="primary" @click="toggleAnim">
              {{ anim.playing ? '暂停' : (anim.progress >= 1 ? '重放' : '播放形成过程') }}
            </el-button>
            <el-button size="small" @click="resetAnim">回到起点</el-button>
            <el-button size="small" @click="finishAnim">一秒画完</el-button>
          </div>

          <div class="fp-anim-middle">
            <el-radio-group v-model="anim.mode" size="small">
              <el-radio-button label="trace">连续描绘</el-radio-button>
              <el-radio-button label="dots">描点法</el-radio-button>
            </el-radio-group>
            <el-slider v-model="anim.percent" :min="0" :max="100" :step="0.5"
                       size="small" class="fp-anim-slider" :show-tooltip="false" />
            <span class="fp-anim-pct">{{ Math.round(anim.progress * 100) }}%</span>
          </div>

          <div class="fp-anim-right">
            <span class="fp-speed-label">速度</span>
            <el-slider v-model="anim.speed" :min="0.2" :max="6" :step="0.2"
                       size="small" class="fp-speed" :show-tooltip="false" />
            <span class="fp-speed-val">{{ anim.speed }}×</span>
          </div>
        </div>
      </main>

      <!-- ==================== 右：形成过程详解 ==================== -->
      <aside class="fp-right">
        <el-tabs v-model="panel" class="fp-tabs">
          <!-- 逐步求值 -->
          <el-tab-pane label="逐步求值" name="steps">
            <div class="fp-xpick">
              <span>取 x =</span>
              <el-input v-model.number="evalX" size="small" class="fp-xpick-input" />
              <el-button size="small" @click="evalX = round2(probeX ?? evalX)">用鼠标位置</el-button>
            </div>

            <div v-if="activeFn && activeFn.error" class="fp-note warn">
              当前函数有错误：{{ activeFn.error }}
            </div>
            <div v-else-if="!visibleSteps.length" class="fp-note">
              在图上移动鼠标，或在上方输入一个 x 值，这里会按计算顺序拆解每一步。
            </div>

            <template v-else>
              <div class="fp-result">
                <span class="fr-label">{{ activeFn.expr }} 在 x = {{ fmt(evalX) }} 处</span>
                <span class="fr-value">= {{ Number.isFinite(evalResult.result) ? fmt(evalResult.result) : '无定义' }}</span>
              </div>
              <ol class="fp-steps">
                <li v-for="(s, i) in visibleSteps" :key="i" class="fp-step">
                  <span class="fs-idx">{{ i + 1 }}</span>
                  <span class="fs-expr" :style="{ paddingLeft: s.depth * 8 + 'px' }">{{ s.expr }}</span>
                  <span class="fs-eq">=</span>
                  <span class="fs-val">{{ Number.isFinite(s.value) ? fmt(s.value) : '无定义' }}</span>
                  <span class="fs-kind">{{ s.kind }}</span>
                </li>
              </ol>
              <div class="fp-note">按「先括号内、再乘除、最后加减」的实际计算顺序列出。</div>
            </template>
          </el-tab-pane>

          <!-- 数值表 -->
          <el-tab-pane label="数值表" name="table">
            <div class="fp-table-head">
              <span>按绘图区范围等距取值</span>
              <el-select v-model="tableCount" size="small" class="fp-table-count">
                <el-option :value="9" label="9 行" />
                <el-option :value="13" label="13 行" />
                <el-option :value="21" label="21 行" />
              </el-select>
            </div>
            <div class="fp-table-wrap">
              <table class="fp-table">
                <thead>
                  <tr>
                    <th>x</th>
                    <th v-for="f in visibleFuncs" :key="f.id">
                      <span class="ft-dot" :style="{ background: f.color }"></span>{{ short(f.expr) }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in tableRows" :key="row.x">
                    <td class="ft-x">{{ fmt(row.x) }}</td>
                    <td v-for="(v, i) in row.values" :key="i">{{ Number.isFinite(v) ? fmt(v) : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </el-tab-pane>

          <!-- 特征 -->
          <el-tab-pane label="图像特征" name="features">
            <div v-if="!activeFn || activeFn.error" class="fp-note">
              选中左侧一个可用函数后，这里会列出它的零点、极值、渐近线与定义域断点。
            </div>
            <div v-else-if="!activeFn.features" class="fp-note">正在计算…</div>
            <template v-else>
              <div class="fp-feat-group">
                <div class="fg-title">零点 <span class="fg-count">{{ activeFn.features.zeros.length }}</span></div>
                <div v-if="!activeFn.features.zeros.length" class="fg-empty">在可见范围内没有零点</div>
                <div v-else class="fg-items">
                  <button v-for="(z, i) in activeFn.features.zeros" :key="'z' + i"
                          class="fg-item" @click="moveProbeTo(z.x)">
                    x ≈ {{ fmt(z.x) }}
                  </button>
                </div>
              </div>

              <div class="fp-feat-group">
                <div class="fg-title">极值 <span class="fg-count">{{ activeFn.features.extrema.length }}</span></div>
                <div v-if="!activeFn.features.extrema.length" class="fg-empty">没有找到局部极值</div>
                <div v-else class="fg-items">
                  <button v-for="(e, i) in activeFn.features.extrema" :key="'e' + i"
                          class="fg-item" @click="moveProbeTo(e.x)">
                    {{ e.kind === 'max' ? '极大' : '极小' }} ({{ fmt(e.x) }}, {{ fmt(e.y) }})
                  </button>
                </div>
              </div>

              <div class="fp-feat-group">
                <div class="fg-title">竖直渐近线 <span class="fg-count">{{ activeFn.features.asymptotes.length }}</span></div>
                <div v-if="!activeFn.features.asymptotes.length" class="fg-empty">没有竖直渐近线</div>
                <div v-else class="fg-items">
                  <button v-for="(a, i) in activeFn.features.asymptotes" :key="'a' + i"
                          class="fg-item warn" @click="moveProbeTo(a.x)">
                    x ≈ {{ fmt(a.x) }}
                  </button>
                </div>
              </div>

              <div v-if="activeFn.features.domainGaps.length" class="fp-feat-group">
                <div class="fg-title">无定义区间 <span class="fg-count">{{ activeFn.features.domainGaps.length }}</span></div>
                <div class="fg-items">
                  <span v-for="(g, i) in activeFn.features.domainGaps.slice(0, 6)" :key="'g' + i"
                        class="fg-item static">
                    {{ fmt(g.xStart) }} ~ {{ fmt(g.xEnd) }}
                  </span>
                </div>
              </div>
            </template>
          </el-tab-pane>

          <!-- 说明 -->
          <el-tab-pane label="怎么用" name="help">
            <div class="fp-help">
              <p><b>输入很宽松</b>：<code>2x</code>、<code>2sin(x)</code>、<code>(x+1)(x-1)</code> 都会自动补上乘号；<code>ln</code>、<code>lg</code>、<code>tg</code>、<code>π</code>、<code>√</code> 也能识别。</p>
              <p><b>鼠标操作</b>：滚轮缩放、按住拖动平移、移动鼠标看该 x 处的函数值。</p>
              <p><b>形成过程</b>有三种看法：
                底部时间轴回放「曲线怎么被画出来」；
                拖动左侧参数滑块看「参数如何改变形状」；
                「逐步求值」标签页看「某个 x 的值是怎么一步步算出来的」。</p>
              <p><b>断点会断开</b>：<code>1/x</code>、<code>tan(x)</code>、<code>log(x)</code> 在无定义处不会连成直线，
                并会把竖直渐近线标出来——把"无定义"画成"一条陡线"是错的。</p>
              <p><b>想用别的函数</b>：点右上角「函数速查」，那里按类别列了 40+ 个函数与示例。</p>
            </div>
          </el-tab-pane>
        </el-tabs>
      </aside>
    </div>

    <!-- 函数速查抽屉 -->
    <el-drawer v-model="catalogOpen" title="函数速查" size="420px" direction="rtl">
      <div class="fp-catalog">
        <el-input v-model="catalogQuery" size="small" placeholder="搜索函数名，如 log / 三角 / 取整"
                  clearable class="cat-search" />
        <div v-for="g in filteredCatalog" :key="g.group" class="cat-group">
          <div class="cat-group-title">{{ g.group }}</div>
          <button v-for="item in g.items" :key="item.name" class="cat-item"
                  :title="`插入到当前函数：${item.sample}`" @click="insertFunction(item.sample)">
            <code class="ci-name">{{ item.name }}</code>
            <span class="ci-desc">{{ item.desc }}</span>
            <span class="ci-add">插入</span>
          </button>
        </div>
        <div v-if="!filteredCatalog.length" class="cat-empty">没有匹配的函数</div>
        <div class="cat-foot">
          基于 mathjs，函数库远不止这些；只要能解析的表达式都可以直接写。
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import PlotCanvas from '@/components/plot/PlotCanvas.vue'
import {
  compileFunction, sampleFunction, findFeatures, collectEvalSteps,
  niceTicks, formatNumber, FUNCTION_CATALOG, PRESETS,
} from '@/utils/functionMath'

/* ------------------------------------------------------------ 曲线配色 */
// 在暖白/深色底上都能分辨，且相邻色相差别足够大
const PALETTE = ['#0C6B84', '#BE2E3E', '#A34A08', '#0F7B5C',
                 '#6D4AA6', '#B22E6B', '#2C6E9B', '#7A6A00']

let uid = 0

function makeFunc(expr) {
  const id = ++uid
  const f = {
    id, index: 0, expr, color: PALETTE[(id - 1) % PALETTE.length],
    visible: true, scope: {}, fn: null, node: null,
    params: [], error: '', normalized: '', sampled: null, features: null,
  }
  compileInto(f)
  return f
}

const funcs = ref([makeFunc('sin(x)')])
const activeId = ref(1)
const activeFn = computed(() => funcs.value.find(f => f.id === activeId.value) || funcs.value[0])

/* ------------------------------------------------------------ 视图状态 */

const viewport = reactive({ xMin: -8, xMax: 8, yMin: -3, yMax: 3 })
const xRangeInput = reactive({ min: -8, max: 8 })
const show = reactive({ grid: true, features: true, asymptotes: true, autoY: true })
const panel = ref('steps')
const catalogOpen = ref(false)
const catalogQuery = ref('')
const tableCount = ref(13)
const canvasWrapRef = ref(null)
const probeX = ref(0)
const evalX = ref(1)
const sampleCount = ref(1200)

const anim = reactive({ playing: false, progress: 1, percent: 100, speed: 1.6, mode: 'trace' })

/* ------------------------------------------------------------ 编译与采样 */

function compileInto(f) {
  const res = compileFunction(f.expr)
  if (!res.ok) {
    f.error = res.error
    f.fn = null; f.node = null; f.params = []; f.normalized = ''
    f.sampled = null; f.features = null
    return
  }
  f.error = ''
  f.fn = res.fn
  f.node = res.node
  f.normalized = res.expr
  f.params = res.params
  // 新出现的参数给一个合理的初始值，沿用用户已调过的值
  for (const p of res.params) if (!(p in f.scope)) f.scope[p] = 1
}

/** 参数滑块的取值范围：按参数名给不同的默认量程，比一律 0~10 好用 */
function paramRange(f, name) {
  if (/^[nN]$/.test(name)) return { min: 1, max: 8, step: 1 }
  if (/^(b|k|w|ω)$/.test(name)) return { min: 0.1, max: 5, step: 0.1 }
  return { min: -5, max: 5, step: 0.1 }
}

function resampleAll() {
  for (const f of funcs.value) {
    if (!f.fn) { f.sampled = null; f.features = null; continue }
    const sampled = sampleFunction(f.fn, {
      xMin: viewport.xMin, xMax: viewport.xMax,
      samples: sampleCount.value, scope: f.scope,
    })
    f.sampled = sampled
    f.features = findFeatures(sampled.segments, sampled.gaps,
      { xMin: viewport.xMin, xMax: viewport.xMax, span: sampled.span })
  }
  if (show.autoY) fitY()
}

/** 纵向自适应：用分位数取"主体范围"，避免被渐近线附近的极值撑爆视野 */
function fitY() {
  const ys = []
  for (const f of funcs.value) {
    if (!f.sampled || f.visible === false) continue
    for (const seg of f.sampled.segments) for (const p of seg) ys.push(p.y)
  }
  const finite = ys.filter(Number.isFinite).sort((a, b) => a - b)
  if (finite.length < 2) { viewport.yMin = -3; viewport.yMax = 3; return }

  const q = (p) => finite[Math.min(finite.length - 1, Math.floor(p * (finite.length - 1)))]
  let lo = q(0.01), hi = q(0.99)
  if (!(hi > lo)) { lo -= 1; hi += 1 }

  const padY = (hi - lo) * 0.12
  viewport.yMin = lo - padY
  viewport.yMax = hi + padY
  // 尽量让 y=0 留在视野里（数学图像少了 x 轴会很别扭）
  if (lo > 0 && lo < (hi - lo)) viewport.yMin = -padY
  if (hi < 0 && -hi < (hi - lo)) viewport.yMax = padY
}

const hasCurve = computed(() => funcs.value.some(f => f.sampled?.segments?.length))

/* ------------------------------------------------------------ 传给画布的数据 */

const plotFunctions = computed(() => funcs.value.map((f, i) => ({ ...f, index: i })))
const visibleFuncs = computed(() => funcs.value.filter(f => f.visible !== false && !f.error))

function onExprInput(f) {
  compileInto(f)
  activeId.value = f.id
  scheduleResample()
}

let resampleTimer = null
function scheduleResample() {
  clearTimeout(resampleTimer)
  // 轻微防抖：连续敲键盘时不必每字符都重采样
  resampleTimer = setTimeout(() => {
    resampleAll()
    if (anim.progress < 1) {
      anim.progress = 1
      anim.percent = 100
    }
  }, 180)
}

function addFunction() {
  const f = makeFunc('x^2')
  funcs.value.push(f)
  activeId.value = f.id
  nextTick(resampleAll)
}

function removeFunction(id) {
  if (funcs.value.length <= 1) return
  funcs.value = funcs.value.filter(f => f.id !== id)
  if (activeId.value === id) activeId.value = funcs.value[0]?.id
  nextTick(resampleAll)
}

function usePreset(p) {
  const f = activeFn.value
  f.expr = p.expr
  compileInto(f)
  scheduleResample()
}

function insertFunction(sample) {
  const f = activeFn.value
  f.expr = sample
  compileInto(f)
  catalogOpen.value = false
  scheduleResample()
  ElMessage.success(`已插入 ${sample}`)
}

const filteredCatalog = computed(() => {
  const q = catalogQuery.value.trim().toLowerCase()
  if (!q) return FUNCTION_CATALOG
  return FUNCTION_CATALOG
    .map(g => ({
      group: g.group,
      items: g.items.filter(it =>
        it.name.toLowerCase().includes(q) ||
        it.desc.toLowerCase().includes(q) ||
        g.group.toLowerCase().includes(q)),
    }))
    .filter(g => g.items.length)
})

function openCatalog() { catalogOpen.value = true }

/* ------------------------------------------------------------ 视口交互 */

function onViewportChange(vp) {
  viewport.xMin = vp.xMin; viewport.xMax = vp.xMax
  viewport.yMin = vp.yMin; viewport.yMax = vp.yMax
  xRangeInput.min = round2(vp.xMin); xRangeInput.max = round2(vp.xMax)
  scheduleResample()
}

function applyXRange() {
  const a = Number(xRangeInput.min), b = Number(xRangeInput.max)
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) {
    ElMessage.warning('x 范围需要是两个不同的数'); return
  }
  viewport.xMin = Math.min(a, b)
  viewport.xMax = Math.max(a, b)
  resampleAll()
}

function onProbe(x) {
  probeX.value = x
  // 鼠标位置就是"当前考察的 x"：跟随更新，逐步求值面板才是实时的
  if (panel.value === 'steps') evalX.value = round2(x)
}

function moveProbeTo(x) {
  probeX.value = x
  evalX.value = round2(x)
}

/* ------------------------------------------------------------ 形成过程动画 */

let rafId = null
let lastT = 0

function tick(t) {
  if (!anim.playing) return
  const dt = lastT ? (t - lastT) / 1000 : 0
  lastT = t
  // 速度按"每秒走完整程的比例"定义，配合底数让低速段也能看清
  const next = anim.progress + dt * anim.speed * 0.28
  if (next >= 1) {
    anim.progress = 1
    anim.percent = 100
    anim.playing = false
    rafId = null
    return
  }
  anim.progress = next
  anim.percent = next * 100
  rafId = requestAnimationFrame(tick)
}

function toggleAnim() {
  if (anim.playing) { anim.playing = false; cancelAnimationFrame(rafId); rafId = null; return }
  if (anim.progress >= 1) { anim.progress = 0; anim.percent = 0 }
  anim.playing = true
  lastT = 0
  rafId = requestAnimationFrame(tick)
}

function resetAnim() {
  anim.playing = false
  cancelAnimationFrame(rafId); rafId = null
  anim.progress = 0
  anim.percent = 0
}

function finishAnim() {
  anim.playing = false
  cancelAnimationFrame(rafId); rafId = null
  anim.progress = 1
  anim.percent = 100
}

watch(() => anim.percent, (v) => {
  if (!anim.playing) {
    anim.progress = v / 100
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  clearTimeout(resampleTimer)
})

/* ------------------------------------------------------------ 逐步求值 */

// 一次算好，求值结果与步骤列表共用，避免重复遍历 AST
const evalResult = computed(() => {
  if (!activeFn.value?.node || !Number.isFinite(evalX.value)) return { steps: [], result: NaN }
  return collectEvalSteps(activeFn.value.node, { ...activeFn.value.scope, x: evalX.value })
})

// 常量/变量本身不单独成步，否则噪声会盖过主要运算逻辑
const visibleSteps = computed(() => evalResult.value.steps.filter(s => !s.trivial))

/* ------------------------------------------------------------ 数值表 */

const tableRows = computed(() => {
  const { xMin, xMax } = viewport
  const n = tableCount.value
  const { ticks } = niceTicks(xMin, xMax, Math.max(2, Math.round(n / 2)))
  return ticks.map(x => ({
    x,
    values: visibleFuncs.value.map(f => {
      try { return f.fn(x, f.scope) } catch { return NaN }
    }),
  }))
})

/* ------------------------------------------------------------ 工具 */

const round2 = (v) => Math.round((Number(v) || 0) * 100) / 100
const fmt = (v) => formatNumber(v, 3)
const short = (s) => { const t = String(s || ''); return t.length > 12 ? t.slice(0, 11) + '…' : t }

function exportSvg() {
  const svg = canvasWrapRef.value?.querySelector('svg')
  if (!svg) { ElMessage.warning('还没有可导出的图形'); return }
  const clone = svg.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  // 把 CSS 变量解析成实际颜色，否则导出的 SVG 在别处打开会丢样式
  const css = getComputedStyle(document.documentElement)
  const vars = ['--bg-secondary', '--border-light', '--border', '--text-secondary',
                '--text-muted', '--warning', '--amber', '--accent']
  const resolved = vars.map(v => `${v}: ${css.getPropertyValue(v).trim()};`).join('')
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  style.textContent = `:root{${resolved}}
    .grid-line{stroke:var(--border-light);stroke-width:1;opacity:.55}
    .grid-line.major{stroke:var(--border);opacity:.9}
    .axis-line{stroke:var(--text-secondary);stroke-width:1.2}
    .axis-arrow{fill:none;stroke:var(--text-secondary);stroke-width:1.2}
    .tick-label{font-size:11px;fill:var(--text-muted);font-family:monospace}
    .axis-name{font-size:12px;fill:var(--text-secondary);font-style:italic}
    .curve-line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
    .curve-ghost{fill:none;stroke-width:2;opacity:.13}
    .curve-dot{opacity:.85}
    .head-dot{stroke:#fff;stroke-width:1.5}
    .guide-line{stroke-width:1;stroke-dasharray:3 3;opacity:.5}
    .asym-line{stroke:var(--warning);stroke-width:1.2;stroke-dasharray:5 4;opacity:.75}
    .feat-zero{fill:var(--bg-secondary);stroke:var(--accent);stroke-width:1.6}
    .feat-extremum{fill:var(--amber);stroke:#fff;stroke-width:1.2}
    .probe-line{stroke:var(--text-muted);stroke-width:1;stroke-dasharray:2 3}
    .probe-dot{stroke:#fff;stroke-width:1.5}`
  clone.insertBefore(style, clone.firstChild)

  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `函数图像-${Date.now()}.svg`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('已导出 SVG')
}

/* ------------------------------------------------------------ 初始化 */

nextTick(() => {
  // 采样密度跟绘图区宽度挂钩：宽屏多采点，曲线更顺；窄屏少采点，省算力
  const w = canvasWrapRef.value?.getBoundingClientRect().width || 900
  // 下限不能太低：极点能否被检出，取决于"有没有采样点足够靠近它"。
  // 采样过稀时 tan(x) 在 ±5π/2 附近的极点会被整段跨过，曲线出现竖直连线。
  // 密度同时随画布宽度走：宽屏多采点更平滑，也不至于在窄屏浪费算力。
  sampleCount.value = Math.min(4000, Math.max(1600, Math.round(w * 2.5)))
  resampleAll()
  finishAnim()
})
</script>

<style scoped>
/* 三栏：左（函数/参数）· 中（画布+时间轴）· 右（形成过程详解） */
.fp-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 14px 18px 16px;
  /* 不写 background：整页容器必须透明，否则会整块盖住素材背景层
     （见 styles/main.css 里 --surface-* 的说明） */
}

.fp-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 12px; flex-shrink: 0;
}
.fp-head-text h2 { margin: 0; font-size: var(--fs-xl); color: var(--text-primary); }
.fp-head-text p { margin: 5px 0 0; font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.6; }
.fp-head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.fp-range {
  display: flex; align-items: center; gap: 5px;
  font-size: var(--fs-sm); color: var(--text-secondary);
}
.fp-range-input { width: 62px; }
.fp-range-sep { color: var(--text-muted); }

.fp-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: 296px minmax(320px, 1fr) 330px;
  /* minmax(0, 1fr) 不能省：grid 的隐式行默认按内容撑高，
     结果画布会把 fp-body 顶破、底部被父级 overflow:hidden 裁掉。
     显式给出 0 下限，行高才由容器高度决定，内部 flex 才能正常收缩。 */
  grid-template-rows: minmax(0, 1fr);
  gap: 12px;
}

/* ---------------- 左栏 ---------------- */
.fp-left {
  display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto; padding-right: 2px;
}
.fp-block {
  background: var(--surface-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 10px 12px 12px;
}
.fp-block-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.fp-block-head h3 {
  margin: 0; font-size: var(--fs-md); font-weight: 600; color: var(--text-primary);
}

.fp-func {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin-bottom: 8px;
  background: var(--bg-primary);
  transition: border-color .15s, box-shadow .15s;
}
.fp-func.active { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.fp-func.hidden { opacity: .5; }

.ff-row { display: flex; align-items: center; gap: 6px; }
.ff-color {
  width: 14px; height: 14px; border-radius: 4px; flex-shrink: 0;
  border: 1px solid rgba(0,0,0,.14); cursor: pointer; padding: 0;
}
.ff-input { flex: 1; min-width: 0; }
.ff-input :deep(input) { font-family: var(--font-mono); font-size: var(--fs-sm); }
.ff-del {
  width: 20px; height: 20px; flex-shrink: 0; padding: 0;
  border: none; background: transparent; cursor: pointer;
  color: var(--text-muted); font-size: 16px; line-height: 1; border-radius: 4px;
}
.ff-del:hover:not(:disabled) { background: var(--danger-soft); color: var(--danger); }
.ff-del:disabled { opacity: .3; cursor: not-allowed; }

.ff-error {
  display: flex; align-items: flex-start; gap: 5px;
  margin-top: 6px; font-size: var(--fs-sm); color: var(--danger); line-height: 1.5;
}
.ff-error-mark {
  flex-shrink: 0; width: 14px; height: 14px; border-radius: 50%;
  background: var(--danger); color: #fff; font-size: 11px; line-height: 14px; text-align: center;
}
.ff-norm {
  margin-top: 5px; font-size: var(--fs-xs); color: var(--text-muted);
}
.ff-norm code {
  font-family: var(--font-mono); background: var(--bg-tertiary);
  padding: 1px 4px; border-radius: 3px; color: var(--text-secondary);
}

.ff-params { margin-top: 8px; }
.ff-param { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.fp-name {
  width: 18px; flex-shrink: 0; font-family: var(--font-mono);
  font-style: italic; font-size: var(--fs-sm); color: var(--accent);
}
.ff-param :deep(.el-slider) { flex: 1; }
.fp-val {
  width: 34px; flex-shrink: 0; text-align: right;
  font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--text-secondary);
}
.ff-param-hint { font-size: var(--fs-xs); color: var(--text-muted); margin-top: 5px; line-height: 1.5; }

.fp-presets { display: flex; flex-wrap: wrap; gap: 5px; }
.fp-preset {
  padding: 3px 8px; border-radius: var(--radius-full);
  border: 1px solid var(--border-light); background: var(--bg-primary);
  color: var(--text-secondary); font-size: var(--fs-sm);
  cursor: pointer; transition: all .15s;
}
.fp-preset:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

.fp-toggles { display: flex; flex-direction: column; gap: 7px; }
.fp-toggles label {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--fs-sm); color: var(--text-secondary);
}

/* ---------------- 中栏 ---------------- */
.fp-main { display: flex; flex-direction: column; min-width: 0; gap: 10px; }
.fp-canvas {
  flex: 1; min-height: 0;
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  overflow: hidden;
}

.fp-anim {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 9px 12px;
  background: var(--surface-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.fp-anim-left, .fp-anim-middle, .fp-anim-right { display: flex; align-items: center; gap: 8px; }
.fp-anim-middle { flex: 1; min-width: 200px; }
.fp-anim-slider { flex: 1; min-width: 90px; }
.fp-anim-pct {
  width: 40px; text-align: right; font-family: var(--font-mono);
  font-size: var(--fs-sm); color: var(--text-secondary);
}
.fp-anim-right { margin-left: auto; }
.fp-speed-label { font-size: var(--fs-sm); color: var(--text-muted); }
.fp-speed { width: 80px; }
.fp-speed-val {
  width: 30px; font-family: var(--font-mono);
  font-size: var(--fs-sm); color: var(--text-secondary);
}

/* ---------------- 右栏 ---------------- */
.fp-right {
  background: var(--surface-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 6px 12px 12px;
  overflow-y: auto;
  min-width: 0;
}
.fp-tabs :deep(.el-tabs__header) { margin-bottom: 10px; }
.fp-tabs :deep(.el-tabs__item) { font-size: var(--fs-md); }

.fp-xpick {
  display: flex; align-items: center; gap: 6px; margin-bottom: 10px;
  font-size: var(--fs-sm); color: var(--text-secondary);
}
.fp-xpick-input { width: 76px; }
.fp-xpick-input :deep(input) { font-family: var(--font-mono); }

.fp-result {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  padding: 8px 10px; margin-bottom: 8px;
  background: var(--accent-soft); border-radius: var(--radius-sm);
}
.fr-label { font-size: var(--fs-sm); color: var(--text-secondary); }
.fr-value {
  font-family: var(--font-mono); font-size: var(--fs-md);
  font-weight: 600; color: var(--accent);
}

.fp-steps { list-style: none; margin: 0; padding: 0; }
.fp-step {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 0; border-bottom: 1px dashed var(--border-light);
  font-size: var(--fs-sm);
}
.fs-idx {
  width: 17px; height: 17px; flex-shrink: 0; border-radius: 50%;
  background: var(--bg-tertiary); color: var(--text-muted);
  font-size: var(--fs-xs); line-height: 17px; text-align: center;
}
.fs-expr {
  flex: 1; min-width: 0; font-family: var(--font-mono);
  color: var(--text-primary); overflow-wrap: anywhere;
}
.fs-eq { color: var(--text-muted); }
.fs-val { font-family: var(--font-mono); font-weight: 600; color: var(--accent); }
.fs-kind {
  flex-shrink: 0; font-size: var(--fs-xs); color: var(--text-muted);
  background: var(--bg-tertiary); padding: 1px 5px; border-radius: 3px;
}

.fp-note {
  margin-top: 10px; padding: 8px 10px;
  background: var(--bg-tertiary); border-radius: var(--radius-sm);
  font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.65;
}
.fp-note.warn { background: var(--danger-soft); color: var(--danger); }

.fp-table-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 8px;
  font-size: var(--fs-sm); color: var(--text-secondary);
}
.fp-table-count { width: 92px; }
.fp-table-wrap { overflow-x: auto; }
.fp-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.fp-table th, .fp-table td {
  padding: 4px 6px; text-align: right;
  border-bottom: 1px solid var(--border-light);
  font-family: var(--font-mono); white-space: nowrap;
}
.fp-table th { color: var(--text-secondary); font-weight: 600; }
.fp-table td { color: var(--text-primary); }
.ft-x { color: var(--text-secondary); }
.ft-dot {
  display: inline-block; width: 7px; height: 7px;
  border-radius: 50%; margin-right: 4px; vertical-align: middle;
}

.fp-feat-group { margin-bottom: 14px; }
.fg-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary);
  margin-bottom: 6px; display: flex; align-items: center; gap: 6px;
}
.fg-count {
  font-size: var(--fs-xs); color: var(--text-muted);
  background: var(--bg-tertiary); padding: 1px 6px; border-radius: var(--radius-full);
}
.fg-empty { font-size: var(--fs-sm); color: var(--text-muted); }
.fg-items { display: flex; flex-wrap: wrap; gap: 5px; }
.fg-item {
  padding: 2px 8px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-light); background: var(--bg-primary);
  font-family: var(--font-mono); font-size: var(--fs-sm);
  color: var(--text-secondary); cursor: pointer;
}
.fg-item:hover { border-color: var(--accent); color: var(--accent); }
.fg-item.warn { border-color: var(--warning); color: var(--warning); }
.fg-item.static { cursor: default; }
.fg-item.static:hover { border-color: var(--border-light); color: var(--text-secondary); }

.fp-help p { margin: 0 0 9px; font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.7; }
.fp-help code {
  font-family: var(--font-mono); font-size: var(--fs-xs);
  background: var(--bg-tertiary); padding: 1px 5px; border-radius: 3px;
  color: var(--text-primary);
}

/* ---------------- 函数速查 ---------------- */
.fp-catalog { padding-bottom: 12px; }
.cat-search { margin-bottom: 12px; }
.cat-group { margin-bottom: 14px; }
.cat-group-title {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-primary);
  margin-bottom: 6px; padding-bottom: 4px;
  border-bottom: 1px solid var(--border-light);
}
.cat-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 5px 7px; border: none; border-radius: var(--radius-sm);
  background: transparent; cursor: pointer; text-align: left;
}
.cat-item:hover { background: var(--accent-soft); }
.ci-name {
  flex-shrink: 0; min-width: 92px;
  font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--accent);
}
.ci-desc { flex: 1; font-size: var(--fs-sm); color: var(--text-secondary); }
.ci-add { flex-shrink: 0; font-size: var(--fs-xs); color: var(--text-muted); }
.cat-item:hover .ci-add { color: var(--accent); }
.cat-empty { font-size: var(--fs-sm); color: var(--text-muted); text-align: center; padding: 20px; }
.cat-foot {
  margin-top: 12px; padding-top: 10px;
  border-top: 1px solid var(--border-light);
  font-size: var(--fs-xs); color: var(--text-muted); line-height: 1.6;
}
</style>
