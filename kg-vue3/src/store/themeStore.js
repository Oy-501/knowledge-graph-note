/**
 * themeStore.js —— 界面设计器（Theme Studio）的状态与下发
 *
 * 要解决的问题：用户想「自己设计网页」，但逐个组件换色会立刻破坏一致性
 * （历史教训：39 个卡片类名 / 59 个按钮类名 / 11 种圆角都是这么来的）。
 * 所以这里只暴露**系统级维度**，用户调的是「整个体系的取值」，不是某颗按钮。
 *
 * 可调六项 → 全部落在 CSS 变量上一处下发、全站响应：
 *   hue      强调色相（oklch 派生 accent 家族，明度/彩度锁定 → 换色相也不会刺眼）
 *   density  密度（字号栅格 + 控件基准高度同步缩放）
 *   radius   圆角系数（三档等比缩放，不引入新的中间值）
 *   surface  面板通透度
 *   grain    颗粒强度
 *   display  展示字（衬线 / 黑体）
 *
 * 不参与个性化：--seal（朱砂）。它是品牌印记，不是皮肤变量 —— 见 identity.css。
 */

import { defineStore } from 'pinia'

const LS_KEY = 'kg-theme'

/** 六项的取值边界。 ranges 同时用于 UI 的 slider min/max 与导入校验 */
export const TOKEN_RANGES = {
  hue: { min: 0, max: 360, step: 1 },
  density: { min: 0.85, max: 1.2, step: 0.05 },
  radius: { min: 0, max: 2, step: 0.1 },
  surface: { min: 0.7, max: 1, step: 0.02 },
  grain: { min: 0, max: 0.4, step: 0.01 },
}

/** 出厂值：与 main.css / identity.css 的默认外观一致 */
function defaultTokens() {
  return {
    hue: 195,      // 青（近似既有品牌强调色）
    density: 1,
    radius: 1,
    surface: 0.9,
    grain: 0.14,
    display: 'serif',
  }
}

/**
 * 预设气质：不是随机配色，而是把六项组合成「一眼能叫出名字」的倾向。
 * 每套都守住同一套 component 结构，换的是取值 —— 所以不会看着像换了个应用。
 */
export const THEME_PRESETS = [
  { id: 'instrument', name: '学术仪器', desc: '青 · 标准密度 · 出厂外观', tokens: { hue: 195, density: 1, radius: 1, surface: 0.9, grain: 0.14, display: 'serif' } },
  { id: 'ink', name: '暗室墨水', desc: '靛蓝 · 高通透 · 极致安静', tokens: { hue: 250, density: 1, radius: 0.8, surface: 0.78, grain: 0.2, display: 'serif' } },
  { id: 'press', name: '暖纸刊物', desc: '琥珀 · 圆润 · 阅读友好', tokens: { hue: 62, density: 1.1, radius: 1.5, surface: 0.95, grain: 0.24, display: 'serif' } },
  { id: 'terminal', name: '终端仪', desc: '青绿 · 紧凑 · 无圆角', tokens: { hue: 158, density: 0.9, radius: 0.2, surface: 0.86, grain: 0.08, display: 'sans' } },
  { id: 'gallery', name: '展陈', desc: '紫 · 宽松 · 大留白', tokens: { hue: 305, density: 1.15, radius: 1.3, surface: 0.92, grain: 0.12, display: 'serif' } },
]

const DISPLAY_FONTS = {
  serif: '"Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", "SimSun", serif',
  sans: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif',
}

/** 字号栅格出厂值（px），density 在其上等比缩放 */
const FS_SCALE = { xs: 11, sm: 12, md: 13, base: 14, lg: 16, xl: 18 }
/** 圆角三档出厂值（px），radius 系数等比缩放 */
const RADIUS_SCALE = { sm: 6, md: 10, lg: 14 }

function clamp(v, range, fallback) {
  const n = Number(v)
  if (!Number.isFinite(n)) return fallback
  return Math.min(range.max, Math.max(range.min, n))
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    tokens: defaultTokens(),
    loaded: false,
    /** 当前应用的预设 id；自由调参后会置为 custom */
    activePreset: 'instrument',
  }),

  getters: {
    isDirty: (s) => s.activePreset === 'custom',
  },

  actions: {
    load() {
      let saved = null
      try {
        saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null')
      } catch { /* 坏了就当没有，不弹错 */ }

      const d = defaultTokens()
      if (saved && typeof saved === 'object') {
        this.tokens = {
          hue: clamp(saved.hue, TOKEN_RANGES.hue, d.hue),
          density: clamp(saved.density, TOKEN_RANGES.density, d.density),
          radius: clamp(saved.radius, TOKEN_RANGES.radius, d.radius),
          surface: clamp(saved.surface, TOKEN_RANGES.surface, d.surface),
          grain: clamp(saved.grain, TOKEN_RANGES.grain, d.grain),
          display: DISPLAY_FONTS[saved.display] ? saved.display : d.display,
        }
        this.activePreset = saved.activePreset || 'custom'
      }
      this.loaded = true
      this.apply()
    },

    /** 改一项并立刻下发。preset 随之失效为 custom */
    setToken(key, value) {
      if (!(key in this.tokens)) return
      if (TOKEN_RANGES[key]) {
        this.tokens[key] = clamp(value, TOKEN_RANGES[key], defaultTokens()[key])
      } else {
        this.tokens[key] = value
      }
      this.activePreset = 'custom'
      this.apply()
      this.persist()
    },

    applyPreset(id) {
      const p = THEME_PRESETS.find(x => x.id === id)
      if (!p) return
      this.tokens = { ...p.tokens }
      this.activePreset = id
      this.apply()
      this.persist()
    },

    reset() {
      this.tokens = defaultTokens()
      this.activePreset = 'instrument'
      this.apply()
      this.persist()
    },

    /**
     * 把六项翻译成 CSS 变量写到 <html> 的行内样式。
     * 行内优先级高于样式表，所以这就是「用户自定义 > 出厂默认」。
     */
    apply() {
      const t = this.tokens
      const root = document.documentElement
      // accent 派生依赖明暗：亮底要压暗才够 4.5:1，暗底要提亮才不发闷
      const isDark = root.classList.contains('dark')

      const L = isDark
        ? { accent: 0.74, fill: 0.62, light: 0.84, strong: 0.68 }
        : { accent: 0.52, fill: 0.46, light: 0.58, strong: 0.44 }
      const C = isDark ? 0.13 : 0.12
      const h = t.hue
      const o = (l, c, alpha) => `oklch(${l} ${c} ${h}${alpha != null ? ` / ${alpha}` : ''})`
      const set = (k, v) => root.style.setProperty(k, v)

      // 强调色家族：明度/彩度锁定，只让用户转色相 ——
      // 这样任何 hue 都不会出现「荧光外套」或「脏灰」，协调性是算出来的不是碰出来的
      set('--accent', o(L.accent, C))
      set('--accent-fill', o(L.fill, C))
      set('--accent-light', o(L.light, C * 0.9))
      set('--accent-strong', o(L.strong, C))
      set('--accent-soft', o(L.accent, C, isDark ? 0.13 : 0.11))
      set('--accent-glow', o(L.accent, C, isDark ? 0.42 : 0.3))

      // 密度：字号栅格 + 控件基准高度**同一个系数**缩放。
      // 只缩字号不缩按钮，界面会变成「小字挤在大盒子里」，这是密度调色最常见的失败。
      for (const [k, px] of Object.entries(FS_SCALE)) {
        set(`--fs-${k}`, `${(px * t.density).toFixed(2)}px`)
      }
      set('--ctrl-h', `${Math.round(30 * t.density)}px`)

      // 圆角：三档等比缩放，不新增中间值（4/8/12 这类值只会让界面看起来没对齐）
      set('--radius-sm', `${(RADIUS_SCALE.sm * t.radius).toFixed(1)}px`)
      set('--radius', `${(RADIUS_SCALE.md * t.radius).toFixed(1)}px`)
      set('--radius-lg', `${(RADIUS_SCALE.lg * t.radius).toFixed(1)}px`)

      // 面板通透：三档按原比例联动（0.90 / 0.82 / 0.88 的相对关系保持不变）
      set('--surface-1', `color-mix(in srgb, var(--bg-secondary) ${(t.surface * 100).toFixed(1)}%, transparent)`)
      set('--surface-2', `color-mix(in srgb, var(--bg-secondary) ${(t.surface * 91.1).toFixed(1)}%, transparent)`)
      set('--surface-3', `color-mix(in srgb, var(--bg-primary) ${(t.surface * 97.8).toFixed(1)}%, transparent)`)

      set('--tex-grain-opacity', String(t.grain))
      set('--font-display', DISPLAY_FONTS[t.display] || DISPLAY_FONTS.serif)
    },

    persist() {
      try {
        localStorage.setItem(LS_KEY, JSON.stringify({ ...this.tokens, activePreset: this.activePreset }))
      } catch { /* localStorage 不可用时纯内存生效即可 */ }
    },

    exportJson() {
      return JSON.stringify({ name: '我的主题', tokens: { ...this.tokens } }, null, 2)
    },

    /** 导入别人给的主题 JSON；返回错误文案，成功返回 null */
    importJson(text) {
      let parsed
      try {
        parsed = JSON.parse(text)
      } catch {
        return '不是合法的 JSON'
      }
      const src = parsed?.tokens
      if (!src || typeof src !== 'object') return '缺少 tokens 字段'
      const d = defaultTokens()
      this.tokens = {
        hue: clamp(src.hue, TOKEN_RANGES.hue, d.hue),
        density: clamp(src.density, TOKEN_RANGES.density, d.density),
        radius: clamp(src.radius, TOKEN_RANGES.radius, d.radius),
        surface: clamp(src.surface, TOKEN_RANGES.surface, d.surface),
        grain: clamp(src.grain, TOKEN_RANGES.grain, d.grain),
        display: DISPLAY_FONTS[src.display] ? src.display : d.display,
      }
      this.activePreset = 'custom'
      this.apply()
      this.persist()
      return null
    },
  },
})
