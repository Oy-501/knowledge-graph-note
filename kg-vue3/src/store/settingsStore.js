/**
 * settingsStore.js
 * 用户偏好设置存储：主题、背景素材、编辑器配置
 *
 * 存储策略：
 *  - 背景设置：IndexedDB（较大数据用 IndexedDB，自定义图片可达数 MB）
 *  - 轻量偏好：LocalStorage（快速读取）
 */

import { defineStore } from 'pinia'
import { openDb, STORE_SETTINGS } from './indexedDB'
import { presetById, patternUrl, backdropUrl } from '@/assets/catalog'

const LS_KEY = 'kg-settings'

/**
 * 设置结构版本号。
 * 为什么要它：视觉改版把默认主题从「亮色」翻成了「深色」，
 * 但老用户的 localStorage 里存着 theme:'light'，会盖掉新默认值，
 * 结果「改版后第一次打开还是旧配色」，看起来像没生效。
 * 所以这里做一次性迁移：结构版本落后 → 采用新的默认主题。
 * 迁移只发生一次，之后用户自己的选择会被尊重（见 _mergeDefaults）。
 */
const SETTINGS_VERSION = 2

// 8 种旧版渐变预设（保留兼容：老用户存的是这些 id，删掉会导致背景空白）
export const PRESET_BACKGROUNDS = [
  { id: 'warm_sunset', name: '暖阳', desc: '舒适写作', colors: ['#fff3e0', '#ffe0b2', '#ffcc80'], gradient: 'linear-gradient(135deg, #fff3e0 0%, #ffe0b2 50%, #ffcc80 100%)' },
  { id: 'clear_sky', name: '青空', desc: '清爽专注', colors: ['#e3f2fd', '#bbdefb', '#90caf9'], gradient: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 50%, #90caf9 100%)' },
  { id: 'dusk', name: '暮色', desc: '创意激发', colors: ['#f3e5f5', '#e1bee7', '#ce93d8'], gradient: 'linear-gradient(135deg, #f3e5f5 0%, #e1bee7 50%, #ce93d8 100%)' },
  { id: 'minimal', name: '极简', desc: '专注内容', colors: ['#f5f5f5', '#eeeeee', '#e0e0e0'], gradient: 'linear-gradient(135deg, #f5f5f5 0%, #eeeeee 50%, #e0e0e0 100%)' },
  { id: 'dark_night', name: '暗夜', desc: '护眼编程', colors: ['#1a1a2e', '#16213e', '#0f3460'], gradient: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)' },
  { id: 'forest', name: '森林', desc: '自然舒缓', colors: ['#e8f5e9', '#c8e6c9', '#a5d6a7'], gradient: 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 50%, #a5d6a7 100%)' },
  { id: 'ocean', name: '海洋', desc: '平静思维', colors: ['#e0f7fa', '#b2ebf2', '#80deea'], gradient: 'linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 50%, #80deea 100%)' },
  { id: 'starry', name: '星空', desc: '深邃思考', colors: ['#0d0d2b', '#1a1a4e', '#2d2d7f'], gradient: 'linear-gradient(135deg, #0d0d2b 0%, #1a1a4e 50%, #2d2d7f 100%)' }
]

function getDefaultSettings() {
  return {
    settingsVersion: SETTINGS_VERSION,
    theme: 'dark',               // 'light' | 'dark' —— 深色科技风是本产品的主主题
    background: {
      // 'preset'（旧渐变）| 'custom'（用户上传图）| 'color' | 'asset'（素材预设）
      type: 'asset',
      value: 'deep-grid',        // 素材预设 id / 旧预设 id / base64 / 色值
      opacity: 0.8,
      blur: 0,
      scope: 'global'            // 素材背景默认全局，才能透到每个页面
    },
    editor: {
      fontSize: 16,
      lineHeight: 1.8,
      fontFamily: 'system-ui',
      fullscreenDefault: false
    }
  }
}

/**
 * 浅合并默认值（兼容旧版持久化数据缺新字段的情况）
 * 同时承担「一次性结构迁移」的职责。
 */
function _mergeDefaults(saved) {
  if (!saved || typeof saved !== 'object') return getDefaultSettings()
  const def = getDefaultSettings()

  const savedVersion = Number(saved.settingsVersion) || 1
  const needsMigration = savedVersion < SETTINGS_VERSION

  return {
    settingsVersion: SETTINGS_VERSION,
    // 迁移时用新默认主题，之后尊重用户选择
    theme: needsMigration ? def.theme : (saved.theme || def.theme),
    // 同理：老数据里没有 asset 背景，迁移时换成素材预设
    background: needsMigration
      ? { ...def.background, ...(saved.background || {}),
          type: 'asset', value: saved.background?.type === 'custom' ? saved.background.value : def.background.value }
      : { ...def.background, ...(saved.background || {}) },
    editor: { ...def.editor, ...(saved.editor || {}) }
  }
}

let _settingsDb = null
async function _getDb() {
  if (!_settingsDb) {
    _settingsDb = await openDb()
  }
  return _settingsDb
}

async function _loadSettings() {
  // 先从 LS 快速加载
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) {
      const parsed = _mergeDefaults(JSON.parse(raw))
      // 检测 [custom_image] 占位符，回读 IndexedDB 完整设置
      if (parsed.background?.value === '[custom_image]') {
        try {
          const db = await _getDb()
          if (db.objectStoreNames.contains(STORE_SETTINGS)) {
            const full = await new Promise((resolve) => {
              const tx = db.transaction(STORE_SETTINGS, 'readonly')
              const req = tx.objectStore(STORE_SETTINGS).get('main')
              req.onsuccess = () => resolve(req.result)
              req.onerror = () => resolve(null)
            })
            if (full) {
              const merged = _mergeDefaults(full)
              localStorage.setItem(LS_KEY, JSON.stringify(merged))
              return merged
            }
          }
        } catch (e) {
          console.warn('[settingsStore] fallback load from IndexedDB failed:', e.message)
        }
      }
      return parsed
    }
  } catch (e) { /* ignore */ }

  // 从 IndexedDB 加载（含自定义图片）
  try {
    const db = await _getDb()
    if (db.objectStoreNames.contains(STORE_SETTINGS)) {
      return new Promise((resolve) => {
        const tx = db.transaction(STORE_SETTINGS, 'readonly')
        const req = tx.objectStore(STORE_SETTINGS).get('main')
        req.onsuccess = () => {
          if (req.result) {
            // 同步到 LS
            const light = { ...req.result }
            if (light.background?.type === 'custom') {
              light.background = { ...light.background, value: '[custom_image]' }
            }
            const merged = _mergeDefaults(light)
            localStorage.setItem(LS_KEY, JSON.stringify(merged))
            resolve(merged)
          } else {
            resolve(getDefaultSettings())
          }
        }
        req.onerror = () => resolve(getDefaultSettings())
      })
    }
  } catch (e) { /* ignore */ }

  return getDefaultSettings()
}

/* ============================================================
   素材参数解析
   ------------------------------------------------------------
   一套素材背景由「来源」与「当前值」两部分拼出来：
     · 来源 = background.value 指向的预设（提供一套初始搭配）
     · 当前值 = background.photo / pattern / *Opacity 上的覆盖项
   用户在面板里单独换一张照片或一个图案时，只写覆盖项，
   不动预设 —— 这样「预设」始终是干净的基准，用户随时能退回去。
   ============================================================ */
function resolveAssetParts(bg) {
  const base = presetById(bg.value) || {}
  return {
    photo: bg.photo !== undefined ? bg.photo : (base.photo ?? null),
    pattern: bg.pattern !== undefined ? bg.pattern : (base.pattern ?? null),
    patternSize: bg.patternSize ?? base.patternSize ?? 64,
    patternOpacity: bg.patternOpacity ?? base.patternOpacity ?? 0.4,
    photoOpacity: bg.photoOpacity ?? base.photoOpacity ?? 0.5,
    blur: bg.blur ?? base.blur ?? 0,
  }
}

/** 清空素材槽位。切到非素材背景时必须调用，否则上一套素材会残留在界面上 */
function clearTextureVars(root, shouldClear) {
  if (!shouldClear) return
  root.style.setProperty('--tex-photo', 'none')
  root.style.setProperty('--tex-photo-opacity', '0')
  root.style.setProperty('--tex-pattern', 'none')
  root.style.setProperty('--tex-pattern-opacity', '0')
}

async function _saveSettings(settings) {
  try {
    const light = { ...settings }
    if (light.background?.type === 'custom') {
      light.background = { ...light.background, value: '[custom_image]' }
    }
    localStorage.setItem(LS_KEY, JSON.stringify(light))
  } catch (e) { /* ignore */ }

  // 完整版存 IndexedDB
  try {
    const db = await _getDb()
    // ⚠️ 必须先把 reactive 代理「拍平」成纯对象再 put。
    // Pinia 的 state 是 reactive 代理，而 IndexedDB 的结构化克隆算法
    // **不接受 Proxy**，直接 put 会抛 DataCloneError。
    // 这个异常发生在 await 处，会把调用方后续的代码整段跳过 ——
    // 之前的表现就是「点主题切换按钮完全没反应」：
    // toggleTheme 里 `await this.save()` 抛错 → 真正切 .dark 类的那行执行不到。
    // 控制台只有一行 DataCloneError，很难联想到是「保存设置失败」导致的。
    // JSON 往返是最稳的拍平方式（设置项本来就保证可 JSON 序列化 ——
    // localStorage 那份一直在用同样的方式存）。
    const plain = JSON.parse(JSON.stringify(settings))
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_SETTINGS, 'readwrite')
      tx.objectStore(STORE_SETTINGS).put({ id: 'main', ...plain })
      tx.oncomplete = () => resolve(true)
      tx.onerror = () => resolve(false)
    })
  } catch (e) {
    // 存储失败不该让用户操作失败 —— 调用方按「尽力持久化」处理
    console.warn('[settingsStore] 保存到 IndexedDB 失败（不影响本次设置生效）：', e?.message)
    return false
  }
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: getDefaultSettings(),
    loaded: false
  }),

  getters: {
    /** 当前是否暗色主题 */
    isDark: (s) => s.settings.theme === 'dark',
    /** 当前背景配置 */
    currentBackground: (s) => s.settings.background,
    /** 编辑器配置 */
    editorConfig: (s) => s.settings.editor,
    /** 获取当前背景 CSS 值 */
    backgroundCSS: (s) => {
      const bg = s.settings.background
      if (bg.type === 'preset') {
        const preset = PRESET_BACKGROUNDS.find(p => p.id === bg.value)
        if (preset) return preset.gradient
        return ''
      }
      if (bg.type === 'custom') {
        return `url(${bg.value}) center/cover no-repeat`
      }
      if (bg.type === 'color') {
        return bg.value
      }
      // 'asset' 类型不在这里产出 CSS —— 它由 texture.css 的槽位变量渲染，
      // 这里返回空串表示「不要用单层 background 盖掉素材层」
      return ''
    },
    /** 当前素材预设对象（type 非 asset 时为 null） */
    assetPreset: (s) => {
      const bg = s.settings.background
      return bg.type === 'asset' ? presetById(bg.value) : null
    },
    /** 当前实际生效的素材参数（预设 + 用户覆盖项合并后的结果） */
    assetParts: (s) => {
      const bg = s.settings.background
      return bg.type === 'asset' ? resolveAssetParts(bg) : null
    },
    /** 供 BackgroundSelector 判断选中态 */
    isAssetBackground: (s) => s.settings.background.type === 'asset',
    /** 背景覆盖层样式 */
    backgroundOverlay: (s) => {
      const bg = s.settings.background
      return {
        opacity: bg.opacity ?? 0.8,
        filter: bg.blur ? `blur(${bg.blur}px)` : 'none'
      }
    }
  },

  actions: {
    async load() {
      this.settings = await _loadSettings()
      this.loaded = true
      // 主题在首帧应用（无动画，避免闪烁）
      document.documentElement.classList.toggle('dark', this.isDark)
      // 注意：这里必须显式把背景写回 DOM。
      // 之前只在 setBackground 里调用 _applyBackground，
      // 结果「刷新页面后背景设置丢失」—— 状态是对的，只是从没被写到 DOM 上。
      // 这类 bug 不会报错，只会表现为「设置没生效」，很难从控制台看出来。
      this._applyBackground()
    },

    /** 一键切换亮/暗主题（带 220ms 平滑过渡） */
    async toggleTheme() {
      this.settings.theme = this.isDark ? 'light' : 'dark'

      // 先改界面，再落盘。
      // 顺序很重要：持久化是「尽力而为」，而切换主题是用户已经明确要求的动作，
      // 不能因为写 IndexedDB 失败就把界面动作也取消掉 ——
      // 之前的写法是先 await save() 再切类，一旦保存抛错，按钮就完全没反应。
      const root = document.documentElement
      root.classList.add('theme-anim')
      root.classList.toggle('dark', this.isDark)
      setTimeout(() => root.classList.remove('theme-anim'), 300)

      await this.save()
    },

    /** 显式设定主题 */
    async setTheme(theme) {
      if (theme !== 'dark' && theme !== 'light') return
      if (this.settings.theme === theme) return
      await this.toggleTheme()
    },

    async save() {
      await _saveSettings(this.settings)
    },

    /** 设置背景 */
    async setBackground(config) {
      this.settings.background = { ...this.settings.background, ...config }
      await this._commitBackground()
    },

    /**
     * 背景类改动的统一提交入口：先应用到 DOM，再落盘。
     * 顺序与 toggleTheme 同理 —— 落盘是尽力而为，界面必须立刻响应。
     */
    async _commitBackground() {
      this._applyBackground()
      await this.save()
    },

    /** 设置预设背景（旧版渐变） */
    async setPresetBackground(presetId) {
      await this.setBackground({ type: 'preset', value: presetId })
    },

    /** 设置素材预设（摄影背景 + 纹理图案的组合，来自 assets/catalog.js） */
    async setAssetPreset(presetId) {
      const preset = presetById(presetId)
      if (!preset) return
      // 换预设时把用户之前的单项覆盖清掉，让新预设完整生效。
      // 不清的话会出现「换了预设但图案还是上一套的」——
      // 因为覆盖项优先级高于预设，用户会以为是选中没生效。
      const bg = this.settings.background
      this.settings.background = {
        type: 'asset',
        value: presetId,
        scope: bg.scope || 'global',
        opacity: bg.opacity ?? 0.8,
        blur: preset.blur ?? 0,
        // 用 null 显式覆盖：resolveAssetParts 里 photo === null 表示「不要照片」
        photo: preset.photo ?? null,
        pattern: preset.pattern ?? null,
        patternSize: preset.patternSize,
        patternOpacity: preset.patternOpacity,
        photoOpacity: preset.photoOpacity,
      }
      await this._commitBackground()
    },

    /** 单独换摄影背景（pattern 不变）；传 null 表示去掉照片 */
    async setAssetPhoto(key) {
      await this.setBackground({ type: 'asset', photo: key ?? null })
    },

    /** 单独换纹理图案（photo 不变）；传 null 表示去掉图案 */
    async setAssetPattern(key) {
      await this.setBackground({ type: 'asset', pattern: key ?? null })
    },

    /**
     * 微调当前素材（图案尺寸 / 浓度 / 照片浓度 / 模糊）。
     * 与 setAssetPreset 分开：微调不应该把 type 改掉，
     * 否则用户从旧渐变切到素材后调一下滑杆就掉回旧背景了。
     */
    async tweakAsset(overrides = {}) {
      const bg = this.settings.background
      if (bg.type !== 'asset') return
      this.settings.background = { ...bg, ...overrides }
      await this._commitBackground()
    },

    /** 设置自定义背景图片 */
    async setCustomBackground(base64Image, options = {}) {
      await this.setBackground({
        type: 'custom',
        value: base64Image,
        opacity: options.opacity ?? 0.8,
        blur: options.blur ?? 0,
        scope: options.scope ?? 'editor'
      })
    },

    /** 设置纯色背景 */
    async setColorBackground(color) {
      await this.setBackground({ type: 'color', value: color })
    },

    /** 设置背景范围 */
    async setBackgroundScope(scope) {
      await this.setBackground({ scope })
    },

    /** 设置编辑器偏好 */
    async setEditorConfig(config) {
      this.settings.editor = { ...this.settings.editor, ...config }
      await this.save()
    },

    /** 应用背景到 DOM */
    _applyBackground() {
      const bg = this.settings.background
      const css = this.backgroundCSS
      const scope = bg.scope || 'global'
      const isAsset = bg.type === 'asset'

      const root = document.documentElement

      // ── ① 素材槽位 ──────────────────────────────────────────
      // texture.css 里的 .app-tex 三层（照片 / 图案 / 颗粒）全部从这里取值。
      // 全站没有任何组件写死 background-image，所以换素材只需改这几个变量。
      clearTextureVars(root, !isAsset)
      if (isAsset) {
        const parts = resolveAssetParts(bg)
        const pUrl = patternUrl(parts.pattern)
        const bUrl = backdropUrl(parts.photo)
        root.style.setProperty('--tex-pattern', pUrl ? `url("${pUrl}")` : 'none')
        root.style.setProperty('--tex-pattern-size', `${parts.patternSize}px`)
        root.style.setProperty('--tex-pattern-opacity', String(parts.pattern ? parts.patternOpacity : 0))
        root.style.setProperty('--tex-photo', bUrl ? `url("${bUrl}")` : 'none')
        root.style.setProperty('--tex-photo-opacity', String(bUrl ? parts.photoOpacity : 0))
        root.style.setProperty('--tex-photo-blur', `${parts.blur}px`)
      }

      // 素材背景是「材质层」，无法只作用于某个局部子视图
      // （它要透到导航、面板、画布各层之间，被裁进某个 view 就失去意义了）。
      // 所以素材一律全局生效，范围设置只对旧版渐变 / 纯色 / 自定义图有意义。
      root.dataset.texScope = isAsset ? 'global' : scope

      // ── ② 旧版单层背景（渐变 / 纯色 / 自定义图） ──────────────
      if (scope === 'global') {
        root.style.setProperty('--app-bg', css || 'var(--bg-deep)')
        root.style.setProperty('--editor-bg', css || 'var(--bg-primary)')
        root.style.setProperty('--workbench-bg', css || 'var(--bg-primary)')
      } else if (scope === 'workbench') {
        root.style.setProperty('--app-bg', 'var(--bg-deep)')
        root.style.setProperty('--editor-bg', css || 'var(--bg-primary)')
        root.style.setProperty('--workbench-bg', css || 'var(--bg-primary)')
      } else {
        root.style.setProperty('--app-bg', 'var(--bg-deep)')
        root.style.setProperty('--editor-bg', css || 'var(--bg-primary)')
        root.style.setProperty('--workbench-bg', 'var(--bg-primary)')
      }
    }
  }
})