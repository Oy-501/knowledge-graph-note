<!--
  界面设计器：让用户自己在网页里定义整套界面的取值。
  这里不逐 button 换色 —— 历史教训是那样立刻会碎。
  用户调的是六个**体系级维度**，一条 slider 下去全站响应。
-->
<template>
  <div class="ts-view">
    <header class="ts-head">
      <div class="u-kicker">
        <span class="u-kicker__no">NO. 09</span>
        <span class="u-kicker__rule"></span>
        <span>界面设计器</span>
      </div>
      <h2>设计你自己的界面</h2>
      <p class="ts-lede">
        拖动任意一项，整个应用立刻跟着变 —— 你调的是体系，不是某个零件。
        印记色（朱砂）与「标记位」规则保持出厂设定，所以再怎么调也不会看着像换了個应用。
      </p>
      <div class="ts-head-actions">
        <button type="button" class="u-btn u-btn--outline" @click="toggleDark">
          {{ isDark ? '切到亮色' : '切到暗色' }}
        </button>
        <button type="button" class="u-btn u-btn--ghost" @click="pickImport">导入主题</button>
        <button type="button" class="u-btn u-btn--ghost" @click="doExport">导出 JSON</button>
        <button type="button" class="u-btn u-btn--ghost" @click="theme.reset()">恢复出厂</button>
      </div>
    </header>

    <div class="ts-body">
      <!-- ================= 左：预设 + 六项调节 ================= -->
      <aside class="ts-panel">
        <section class="ts-block">
          <h3 class="ts-block-title">气质预设</h3>
          <div class="ts-presets">
            <button
              v-for="p in presets"
              :key="p.id"
              type="button"
              class="ts-preset"
              :class="{ 'is-active': theme.activePreset === p.id }"
              @click="theme.applyPreset(p.id)"
            >
              <span class="ts-preset-swatch" :style="{ background: hueOf(p) }"></span>
              <span class="ts-preset-text">
                <strong>{{ p.name }}</strong>
                <em>{{ p.desc }}</em>
              </span>
            </button>
          </div>
          <p v-if="theme.isDirty" class="ts-note">当前为自定义：{{ theme.activePreset === 'custom' ? '自由调参中' : '' }}</p>
        </section>

        <section class="ts-block">
          <h3 class="ts-block-title">体系维度</h3>

          <div class="ts-field">
            <label for="t-hue">
              <span>强调色相</span>
              <b class="mono">{{ theme.tokens.hue }}°</b>
            </label>
            <input id="t-hue" class="ts-slider" type="range"
                   :min="ranges.hue.min" :max="ranges.hue.max" :step="ranges.hue.step"
                   :value="theme.tokens.hue"
                   @input="e => theme.setToken('hue', +e.target.value)" />
            <p class="ts-hint">明度与彩度锁定，只转色相 —— 所以任何取值都不会刺眼。</p>
          </div>

          <div class="ts-field">
            <label for="t-density">
              <span>密度</span>
              <b class="mono">×{{ theme.tokens.density.toFixed(2) }}</b>
            </label>
            <input id="t-density" class="ts-slider" type="range"
                   :min="ranges.density.min" :max="ranges.density.max" :step="ranges.density.step"
                   :value="theme.tokens.density"
                   @input="e => theme.setToken('density', +e.target.value)" />
            <p class="ts-hint">字号与控件高度同一个系数缩放，避免「小字挤在大盒子里」。</p>
          </div>

          <div class="ts-field">
            <label for="t-radius">
              <span>圆角</span>
              <b class="mono">×{{ theme.tokens.radius.toFixed(1) }}</b>
            </label>
            <input id="t-radius" class="ts-slider" type="range"
                   :min="ranges.radius.min" :max="ranges.radius.max" :step="ranges.radius.step"
                   :value="theme.tokens.radius"
                   @input="e => theme.setToken('radius', +e.target.value)" />
          </div>

          <div class="ts-field">
            <label for="t-surface">
              <span>面板通透</span>
              <b class="mono">{{ Math.round(theme.tokens.surface * 100) }}%</b>
            </label>
            <input id="t-surface" class="ts-slider" type="range"
                   :min="ranges.surface.min" :max="ranges.surface.max" :step="ranges.surface.step"
                   :value="theme.tokens.surface"
                   @input="e => theme.setToken('surface', +e.target.value)" />
          </div>

          <div class="ts-field">
            <label for="t-grain">
              <span>颗粒</span>
              <b class="mono">{{ theme.tokens.grain.toFixed(2) }}</b>
            </label>
            <input id="t-grain" class="ts-slider" type="range"
                   :min="ranges.grain.min" :max="ranges.grain.max" :step="ranges.grain.step"
                   :value="theme.tokens.grain"
                   @input="e => theme.setToken('grain', +e.target.value)" />
          </div>

          <div class="ts-field">
            <span class="ts-field-label">展示字</span>
            <div class="ts-seg">
              <button type="button" class="ts-seg-btn"
                      :class="{ 'is-on': theme.tokens.display === 'serif' }"
                      @click="theme.setToken('display', 'serif')">
                <span class="ts-serif">衬线</span>
              </button>
              <button type="button" class="ts-seg-btn"
                      :class="{ 'is-on': theme.tokens.display === 'sans' }"
                      @click="theme.setToken('display', 'sans')">
                <span class="ts-sans">黑体</span>
              </button>
            </div>
          </div>
        </section>
      </aside>

      <!-- ================= 右：实时预览（消费同一套变量） ================= -->
      <section class="ts-stage">
        <div class="u-sec-title">
          <span class="u-sec-title__no">01</span>
          <h3 class="u-sec-title__label">实时预览</h3>
          <span class="u-sec-title__fill"></span>
          <span class="u-sec-title__note">下面这些就是应用的真实组件</span>
        </div>

        <div class="ts-mock">
          <div class="ts-mock-nav">
            <span class="ts-seal">谱</span>
            <span class="ts-mock-tab is-active">知识图谱</span>
            <span class="ts-mock-tab">知识工作台</span>
            <span class="ts-mock-tab">知识库</span>
          </div>

          <div class="ts-mock-body">
            <div class="ts-mock-main">
              <h4 class="ts-mock-h4">这是标题，用展示字</h4>
              <p class="ts-mock-p">
                正文行在这条灰色带子上。密度一栏拖到最紧，整个界面的字号与控件会一起收，
                而不是只有文字变小 —— 这是这一版设计器最想修的一点。
              </p>
              <div class="ts-mock-btnrow">
                <button type="button" class="u-btn u-btn--solid">主操作</button>
                <button type="button" class="u-btn u-btn--outline">次要</button>
                <button type="button" class="u-btn u-btn--tonal">强调色</button>
                <button type="button" class="u-btn u-btn--ghost">安静</button>
              </div>
              <div class="ts-mock-chips">
                <span class="u-chip u-chip--on">已关联</span>
                <span class="u-chip">知识点</span>
                <span class="u-chip u-chip--muted">未校验</span>
              </div>
            </div>

            <div class="ts-mock-side">
              <div class="u-surface ts-card">
                <span class="u-chip">面板 A</span>
                <div class="ts-bar" :style="{ width: '72%' }"></div>
                <div class="ts-bar" :style="{ width: '48%' }"></div>
              </div>
              <div class="u-surface u-surface--inset ts-card">
                <span class="u-chip u-chip--muted">内嵌块</span>
                <div class="ts-bar ts-bar-alt" :style="{ width: '60%' }"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="ts-values">
          <div v-for="row in summary" :key="row.k" class="ts-value">
            <span>{{ row.k }}</span>
            <code>{{ row.v }}</code>
          </div>
        </div>
      </section>
    </div>

    <input ref="fileRef" type="file" accept=".json,application/json" hidden @change="onImport" />
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useThemeStore, THEME_PRESETS, TOKEN_RANGES } from '@/store/themeStore'
import { useSettingsStore } from '@/store/settingsStore'

const theme = useThemeStore()
const settings = useSettingsStore()
const presets = THEME_PRESETS
const ranges = TOKEN_RANGES
const fileRef = ref(null)

const isDark = computed(() => settings.isDark)

onMounted(() => {
  if (!theme.loaded) theme.load()
})

// 色卡：把预设的 hue 转成预览能显示的颜色（与 themeStore 同一套 oklch 派生口径）
function hueOf(p) {
  const dark = settings.isDark
  return `oklch(${dark ? 0.74 : 0.52} 0.13 ${p.tokens.hue})`
}

function toggleDark() {
  settings.toggleTheme()
  // accent 派生依赖明暗，切完要重算一次，否则换到亮底时强调色偏淡看不清
  requestAnimationFrame(() => theme.apply())
}

function doExport() {
  const blob = new Blob([theme.exportJson()], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'my-theme.json'
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('主题已导出')
}

function pickImport() {
  fileRef.value?.click()
}

async function onImport(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const err = theme.importJson(await file.text())
  ElMessage[err ? 'warning' : 'success'](err || '主题已导入')
  e.target.value = ''
}

const summary = computed(() => [
  { k: '强调色相', v: `${theme.tokens.hue}°` },
  { k: '密度', v: `×${theme.tokens.density.toFixed(2)}` },
  { k: '圆角', v: `×${theme.tokens.radius.toFixed(1)}` },
  { k: '通透', v: `${Math.round(theme.tokens.surface * 100)}%` },
  { k: '颗粒', v: theme.tokens.grain.toFixed(2) },
  { k: '展示字', v: theme.tokens.display === 'serif' ? '衬线' : '黑体' },
])
</script>

<style scoped>
.ts-view {
  height: 100%;
  overflow: auto;
  padding: 20px 24px 40px;
}
.ts-head {
  max-width: 900px;
}
.ts-head h2 { margin: 10px 0 8px; }
.ts-lede {
  margin: 0 0 14px;
  font-size: var(--fs-md);
  color: var(--text-secondary);
  line-height: 1.7;
  max-width: 62ch;
}
.ts-head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.ts-body {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 24px;
  margin-top: 22px;
  align-items: start;
}
@media (max-width: 1080px) {
  .ts-body { grid-template-columns: 1fr; }
}

/* ---------------- 左栏 ---------------- */
.ts-panel {
  position: sticky;
  top: 0;
}
.ts-block + .ts-block { margin-top: 22px; }
.ts-block-title {
  margin: 0 0 10px;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}
.ts-presets {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ts-preset {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  text-align: left;
  background: var(--surface-1);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out),
              background-color var(--dur-fast) var(--ease-out);
}
.ts-preset:hover { background: var(--bg-hover); }
.ts-preset.is-active {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.ts-preset-swatch {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: 1px solid var(--border-light);
}
.ts-preset-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ts-preset-text strong { font-size: var(--fs-md); color: var(--text-primary); font-weight: 600; }
.ts-preset-text em {
  font-style: normal;
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.ts-note { margin: 8px 0 0; font-size: var(--fs-xs); color: var(--text-muted); }

/* ---------------- 调节项 ---------------- */
.ts-field { margin-bottom: 16px; }
.ts-field label,
.ts-field-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.ts-field label b { color: var(--text-primary); font-weight: 600; }
.mono { font-family: var(--font-mono); }
.ts-hint {
  margin: 5px 0 0;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  line-height: 1.5;
}

/* 滑块：hairline 轨 + 实心 thumb，不加辉光（静止的东西不该发光） */
.ts-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 18px;
  background: transparent;
  cursor: pointer;
}
.ts-slider::-webkit-slider-runnable-track {
  height: 2px;
  background: var(--border);
  border-radius: 1px;
}
.ts-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--accent-fill);
  border: 0;
}
.ts-slider::-moz-range-track {
  height: 2px;
  background: var(--border);
}
.ts-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: 0;
  border-radius: 50%;
  background: var(--accent-fill);
}
.ts-slider:focus-visible::-webkit-slider-thumb { outline: 2px solid var(--accent); outline-offset: 2px; }

.ts-seg {
  display: inline-flex;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.ts-seg-btn {
  padding: 6px 14px;
  background: var(--surface-1);
  border: 0;
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out),
              color var(--dur-fast) var(--ease-out);
}
.ts-seg-btn + .ts-seg-btn { border-left: 1px solid var(--border-light); }
.ts-seg-btn:hover { background: var(--bg-hover); }
.ts-seg-btn.is-on { background: var(--accent-soft); color: var(--accent); }
.ts-serif { font-family: var(--font-display); }
.ts-sans { font-family: var(--font-sans); }

/* ---------------- 右栏预览 ---------------- */
.ts-stage { min-width: 0; }
.ts-mock {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--surface-3);
}
.ts-mock-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--rule);
}
.ts-seal {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  margin-right: 14px;
  background: var(--seal);
  color: var(--seal-ink);
  font-family: var(--font-display);
  font-weight: 900;
  font-size: 13px;
  border-radius: 2px;
  transform: rotate(-3deg);
}
.ts-mock-tab {
  padding: 5px 10px;
  font-size: var(--fs-sm);
  color: var(--text-muted);
  border-radius: 3px;
}
.ts-mock-tab.is-active {
  color: var(--text-primary);
  font-weight: 600;
  position: relative;
}
.ts-mock-tab.is-active::after {
  content: "";
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: -1px;
  height: 2px;
  background: var(--accent);
}
.ts-mock-body {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 16px;
  padding: 18px;
}
@media (max-width: 1320px) {
  .ts-mock-body { grid-template-columns: 1fr; }
}
.ts-mock-h4 {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-size: calc(var(--fs-lg) + 2px);
  color: var(--text-primary);
  position: relative;
  padding-left: 17px;
}
.ts-mock-h4::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.45em;
  width: 7px;
  height: 7px;
  background: var(--accent);
  transform: rotate(45deg);
}
.ts-mock-p {
  margin: 0 0 14px;
  font-size: var(--fs-md);
  color: var(--text-secondary);
  line-height: 1.75;
}
.ts-mock-btnrow { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.ts-mock-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ts-card {
  padding: 12px;
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ts-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--accent-fill);
}
.ts-bar-alt { background: var(--text-faint); }

.ts-values {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.ts-value {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--surface-1);
}
.ts-value span { font-size: var(--fs-xs); color: var(--text-muted); }
.ts-value code { font-family: var(--font-mono); font-size: var(--fs-md); color: var(--text-primary); }
</style>
