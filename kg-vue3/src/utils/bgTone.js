/** 背景色调判断：按背景亮度切换按钮配色，保证换背景后文字与描边仍可读。 */

const DARK_LUMINANCE = 0.45
const FALLBACK = { tone: 'dark', luminance: 0.05, source: 'fallback' }

/** 解析 #rgb / #rrggbb / rgb() / rgba()；解析不了返回 null。 */
export function parseColor(value) {
  if (!value || typeof value !== 'string') return null
  const text = value.trim().toLowerCase()

  const hex = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})(?:[0-9a-f]{2})?$/)
  if (hex) {
    let h = hex[1]
    if (h.length === 3) h = h.split('').map(c => c + c).join('')
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    }
  }

  const rgb = text.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/)
  if (rgb) {
    return { r: Number(rgb[1]), g: Number(rgb[2]), b: Number(rgb[3]) }
  }
  return null
}

/** 通道归一化（sRGB → 线性）。 */
function channel(v) {
  const c = Math.max(0, Math.min(255, v)) / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

/** WCAG 相对亮度，0（黑）~ 1（白）。 */
export function relLuminance({ r, g, b }) {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

/** 两色对比度，1 ~ 21。 */
export function contrastRatio(a, b) {
  const la = relLuminance(a)
  const lb = relLuminance(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

/** 按亮度判定背景是深还是浅。 */
export function toneOf(rgb) {
  return relLuminance(rgb) < DARK_LUMINANCE ? 'dark' : 'light'
}

/** 同步解析背景配置：纯色取色值，素材/旧渐变取预设的首色。 */
export function resolveBackgroundTone(background = {}, presets = [], legacyPresets = []) {
  const type = background.type || 'asset'

  if (type === 'color') {
    const rgb = parseColor(background.value)
    return rgb ? { tone: toneOf(rgb), luminance: relLuminance(rgb), source: 'color' } : FALLBACK
  }

  if (type === 'asset') {
    const preset = presets.find(p => p.id === background.value)
    const rgb = parseColor(preset?.swatch?.[0])
    return rgb
      ? { tone: toneOf(rgb), luminance: relLuminance(rgb), source: 'asset-swatch' }
      : FALLBACK
  }

  if (type === 'preset') {
    const legacy = legacyPresets.find(p => p.id === background.value)
    const rgb = parseColor(legacy?.colors?.[0])
    return rgb
      ? { tone: toneOf(rgb), luminance: relLuminance(rgb), source: 'preset-colors' }
      : FALLBACK
  }

  // 自定义图片与旧渐变：先给保守值，图片可再异步采样覆盖
  return { ...FALLBACK, source: 'pending-image' }
}

/**
 * 采样图片平均色。图片按 opacity 叠在底色上，所以先混合再算亮度，
 * 否则一张 20% 不透明度的亮图会被误判成浅色背景。
 */
export function sampleImageTone(url, baseHex = '#05060A', alpha = 0.8) {
  return new Promise(resolve => {
    const base = parseColor(baseHex) || { r: 5, g: 6, b: 10 }
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = 1
        canvas.height = 1
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(img, 0, 0, 1, 1)
        const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data
        const a = Math.max(0, Math.min(1, Number(alpha) || 0))
        const mixed = {
          r: r * a + base.r * (1 - a),
          g: g * a + base.g * (1 - a),
          b: b * a + base.b * (1 - a),
        }
        resolve({ tone: toneOf(mixed), luminance: relLuminance(mixed), source: 'image-sample' })
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

/** 把结论写到根节点：CSS 用 [data-bg-tone] 选择器接管按钮配色。 */
export function applyBgTone(tone, luminance) {
  const root = document.documentElement
  if (root.dataset.bgTone !== tone) root.dataset.bgTone = tone
  root.style.setProperty('--bg-lum', (luminance ?? 0).toFixed(3))
}
