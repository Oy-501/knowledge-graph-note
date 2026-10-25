/**
 * 背景色调判断回归测试。
 * 运行：node tests/bgTone.test.mjs
 */
import assert from 'node:assert/strict'
import {
  parseColor, relLuminance, contrastRatio, toneOf, resolveBackgroundTone,
} from '../src/utils/bgTone.js'

// ---- 颜色解析 ----
assert.deepEqual(parseColor('#fff'), { r: 255, g: 255, b: 255 })
assert.deepEqual(parseColor('#05060a'), { r: 5, g: 6, b: 10 })
assert.deepEqual(parseColor('rgb(10, 20, 30)'), { r: 10, g: 20, b: 30 })
assert.deepEqual(parseColor('rgba(10, 20, 30, 0.5)'), { r: 10, g: 20, b: 30 })
assert.equal(parseColor('not-a-color'), null)
assert.equal(parseColor(''), null)

// ---- 亮度与对比度 ----
assert.ok(relLuminance({ r: 0, g: 0, b: 0 }) < 0.001, '纯黑亮度应接近 0')
assert.ok(relLuminance({ r: 255, g: 255, b: 255 }) > 0.99, '纯白亮度应接近 1')
assert.ok(contrastRatio({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 }) > 20, '黑白对比度应超过 20')

// ---- 深浅判定 ----
assert.equal(toneOf({ r: 5, g: 6, b: 10 }), 'dark')
assert.equal(toneOf({ r: 245, g: 247, b: 250 }), 'light')
assert.equal(toneOf({ r: 128, g: 128, b: 128 }), 'dark', '中灰亮度低于阈值，按深色处理')

// ---- 背景配置解析（预设表由调用方注入，避免依赖 Vite 资源解析）----
const PRESETS = [
  { id: 'deep-grid', swatch: ['#05060A', '#22D3EE'] },
  { id: 'paper-plain', swatch: ['#F7F8FA', '#1677FF'] },
]

assert.equal(resolveBackgroundTone({ type: 'color', value: '#ffffff' }).tone, 'light')
assert.equal(resolveBackgroundTone({ type: 'color', value: '#05060a' }).tone, 'dark')
assert.equal(resolveBackgroundTone({ type: 'asset', value: 'deep-grid' }, PRESETS).tone, 'dark')
assert.equal(resolveBackgroundTone({ type: 'asset', value: 'paper-plain' }, PRESETS).tone, 'light')
assert.equal(resolveBackgroundTone({ type: 'asset', value: 'unknown' }, PRESETS).source, 'fallback')
assert.equal(resolveBackgroundTone({ type: 'custom', value: 'blob:x' }).source, 'pending-image')
assert.equal(resolveBackgroundTone({ type: 'asset' }, PRESETS).source, 'fallback')

// 旧版渐变预设：浅色必须识别出来
const LEGACY = [
  { id: 'minimal', colors: ['#f5f5f5', '#eeeeee'] },
  { id: 'dark_night', colors: ['#1a1a2e', '#16213e'] },
]
assert.equal(resolveBackgroundTone({ type: 'preset', value: 'minimal' }, [], LEGACY).tone, 'light')
assert.equal(resolveBackgroundTone({ type: 'preset', value: 'dark_night' }, [], LEGACY).tone, 'dark')
assert.equal(resolveBackgroundTone({ type: 'preset', value: 'missing' }, [], LEGACY).source, 'fallback')
assert.equal(resolveBackgroundTone({}).source, 'fallback')

console.log('bgTone: all assertions passed')
