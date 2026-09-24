/**
 * settingsStore.js
 * 用户偏好设置存储：背景主题、编辑器配置
 *
 * 存储策略：
 *  - 背景设置：IndexedDB（较大数据用 IndexedDB）
 *  - 轻量偏好：LocalStorage（快速读取）
 */

import { defineStore } from 'pinia'
import { openDb, STORE_SETTINGS } from './indexedDB'

const LS_KEY = 'kg-settings'

// 8种预设背景主题
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
    theme: 'light',              // 'light' | 'dark'（亮色为默认主题）
    background: {
      type: 'preset',         // 'preset' | 'custom' | 'color'
      value: 'dark_night',    // 预设ID / base64图片 / 颜色值
      opacity: 0.8,
      blur: 0,
      scope: 'editor'         // 'editor' | 'workbench' | 'global'
    },
    editor: {
      fontSize: 16,
      lineHeight: 1.8,
      fontFamily: 'system-ui',
      fullscreenDefault: false
    }
  }
}

/** 浅合并默认值（兼容旧版持久化数据缺新字段的情况） */
function _mergeDefaults(saved) {
  if (!saved || typeof saved !== 'object') return getDefaultSettings()
  const def = getDefaultSettings()
  return {
    theme: saved.theme || def.theme,
    background: { ...def.background, ...(saved.background || {}) },
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

async function _saveSettings(settings) {
  // 轻量版存 LS
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
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_SETTINGS, 'readwrite')
      tx.objectStore(STORE_SETTINGS).put({ id: 'main', ...settings })
      tx.oncomplete = () => resolve(true)
      tx.onerror = () => resolve(false)
    })
  } catch (e) {
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
      return ''
    },
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
    },

    /** 一键切换亮/暗主题（带 220ms 平滑过渡） */
    async toggleTheme() {
      this.settings.theme = this.isDark ? 'light' : 'dark'
      await this.save()
      const root = document.documentElement
      root.classList.add('theme-anim')
      root.classList.toggle('dark', this.isDark)
      setTimeout(() => root.classList.remove('theme-anim'), 300)
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
      await this.save()
      this._applyBackground()
    },

    /** 设置预设背景 */
    async setPresetBackground(presetId) {
      await this.setBackground({ type: 'preset', value: presetId })
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
      const scope = bg.scope || 'editor'

      const root = document.documentElement
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