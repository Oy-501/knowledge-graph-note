<template>
  <Transition name="fade">
    <div v-if="visible" class="bg-selector-overlay" @click.self="$emit('close')">
      <div class="bg-selector">
        <header class="bg-header">
          <div>
            <h3>背景与素材</h3>
            <p class="bg-sub">
              {{ counts.backdrops }} 张摄影背景 · {{ counts.patterns }} 个纹理图案
              <span class="bg-sub-src">来自 Unsplash 与 Hero Patterns</span>
            </p>
          </div>
          <button type="button" class="bg-close" @click="$emit('close')" aria-label="关闭">✕</button>
        </header>

        <!-- 分类页签 -->
        <nav class="bg-tabs" role="tablist">
          <button
            v-for="t in TABS" :key="t.key" type="button" role="tab"
            class="bg-tab" :class="{ active: tab === t.key }"
            :aria-selected="tab === t.key"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </nav>

        <!-- ============ ① 整套预设 ============ -->
        <section v-show="tab === 'preset'" class="bg-pane">
          <p class="bg-note">
            每套预设已验证过「照片 × 图案」的叠加效果 —— 自己乱配很容易糊成一片。
          </p>
          <div class="bg-preset-grid">
            <button
              v-for="p in presets" :key="p.id" type="button"
              class="bg-preset" :class="{ active: isPresetActive(p.id) }"
              :title="p.hint"
              @click="settingsStore.setAssetPreset(p.id)"
            >
              <span class="bp-preview" :style="presetPreviewStyle(p)">
                <span class="bp-swatch" :style="{ background: swatchBg(p) }"></span>
              </span>
              <span class="bp-name">{{ p.name }}</span>
              <span class="bp-hint">{{ p.hint }}</span>
              <span v-if="isPresetActive(p.id)" class="bp-check">✓</span>
            </button>
          </div>
        </section>

        <!-- ============ ② 摄影背景 ============ -->
        <section v-show="tab === 'photo'" class="bg-pane">
          <div class="bg-toolbar">
            <span>单独更换照片，图案保持不变</span>
            <button type="button" class="bg-btn bg-btn-sm" @click="settingsStore.setAssetPhoto(null)">不用照片</button>
          </div>
          <div v-for="g in groupedBackdrops" :key="g.name" class="bg-group">
            <h4>{{ g.name }}</h4>
            <div class="bg-photo-grid">
              <button
                v-for="b in g.items" :key="b.key" type="button"
                class="bg-photo" :class="{ active: parts?.photo === b.key }"
                :title="b.desc"
                @click="settingsStore.setAssetPhoto(b.key)"
              >
                <img :src="backdropUrl(b.key)" :alt="b.name" loading="lazy" decoding="async" />
                <span class="bph-name">{{ b.name }}</span>
                <span v-if="parts?.photo === b.key" class="bph-check">✓</span>
              </button>
            </div>
          </div>
        </section>

        <!-- ============ ③ 纹理图案 ============ -->
        <section v-show="tab === 'pattern'" class="bg-pane">
          <div class="bg-toolbar">
            <span>单独更换图案，照片保持不变</span>
            <button type="button" class="bg-btn bg-btn-sm" @click="settingsStore.setAssetPattern(null)">不用图案</button>
          </div>
          <div v-for="g in groupedPatterns" :key="g.name" class="bg-group">
            <h4>{{ g.name }}</h4>
            <div class="bg-pattern-grid">
              <button
                v-for="p in g.items" :key="p.key" type="button"
                class="bg-pattern" :class="{ active: parts?.pattern === p.key }"
                :title="p.desc"
                @click="settingsStore.setAssetPattern(p.key)"
              >
                <span class="bpa-tile" :style="patternTileStyle(p.key)"></span>
                <span class="bpa-name">{{ p.name }}</span>
              </button>
            </div>
          </div>
        </section>

        <!-- ============ ④ 微调（素材模式才有） ============ -->
        <section v-if="parts" class="bg-tune">
          <h4>微调当前素材</h4>
          <div class="bg-row">
            <label>图案大小</label>
            <input type="range" min="12" max="420" step="2" :value="parts.patternSize"
                   @input="settingsStore.tweakAsset({ patternSize: Number($event.target.value) })" />
            <b>{{ parts.patternSize }}px</b>
          </div>
          <div class="bg-row">
            <label>图案浓度</label>
            <input type="range" min="0" max="100" step="1" :value="Math.round(parts.patternOpacity * 100)"
                   @input="settingsStore.tweakAsset({ patternOpacity: Number($event.target.value) / 100 })" />
            <b>{{ Math.round(parts.patternOpacity * 100) }}%</b>
          </div>
          <div class="bg-row">
            <label>照片浓度</label>
            <input type="range" min="0" max="100" step="1" :value="Math.round(parts.photoOpacity * 100)"
                   @input="settingsStore.tweakAsset({ photoOpacity: Number($event.target.value) / 100 })" />
            <b>{{ Math.round(parts.photoOpacity * 100) }}%</b>
          </div>
          <div class="bg-row">
            <label>照片模糊</label>
            <input type="range" min="0" max="24" step="1" :value="parts.blur"
                   @input="settingsStore.tweakAsset({ blur: Number($event.target.value) })" />
            <b>{{ parts.blur }}px</b>
          </div>
        </section>

        <!-- ============ ⑤ 纯色 / 自定义 / 旧版渐变 ============ -->
        <section v-show="tab === 'custom'" class="bg-pane">
          <div class="bg-group">
            <h4>纯色背景</h4>
            <div class="bg-row">
              <input type="color" :value="colorValue" class="bg-color" @input="onColorChange($event.target.value)" />
              <code class="bg-hex">{{ colorValue }}</code>
              <button type="button" class="bg-btn bg-btn-sm bg-btn-primary"
                      @click="settingsStore.setBackground({ type: 'color', value: colorValue })">应用</button>
              <button type="button" class="bg-btn bg-btn-sm" @click="toAssetMode">回到素材</button>
            </div>
          </div>

          <div class="bg-group">
            <h4>自定义图片</h4>
            <div class="bg-upload" @click="fileInput?.click()" @dragover.prevent @drop.prevent="onDrop">
              <img v-if="customPreview" :src="customPreview" class="bg-upload-preview" alt="自定义背景预览" />
              <template v-else>
                <span>点击或拖拽图片到此处</span>
                <small>JPG / PNG / WebP，≤ 5MB（自动转 WebP 压缩）</small>
              </template>
            </div>
            <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp"
                   class="sr-only" @change="onFileSelected" />
            <div v-if="customPreview" class="bg-row">
              <button type="button" class="bg-btn bg-btn-sm bg-btn-primary" @click="applyCustom">应用为背景</button>
              <button type="button" class="bg-btn bg-btn-sm" @click="clearCustom">清除</button>
            </div>
          </div>

          <div class="bg-group">
            <h4>旧版渐变（保留，不再推荐）</h4>
            <div class="bg-legend">
              <button v-for="p in legacyPresets" :key="p.id" type="button"
                      class="bg-legend-item" :style="{ background: p.gradient }"
                      :title="`${p.name} · ${p.desc}`"
                      @click="settingsStore.setPresetBackground(p.id)">
                <span>{{ p.name }}</span>
              </button>
            </div>
          </div>
        </section>

        <footer class="bg-footer">
          <span class="bg-credits">
            素材署名：{{ credits.patterns }}；{{ credits.photos }}
          </span>
          <div class="bg-footer-btns">
            <button type="button" class="bg-btn" @click="resetDefault">恢复默认</button>
            <button type="button" class="bg-btn bg-btn-primary" @click="$emit('close')">完成</button>
          </div>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore, PRESET_BACKGROUNDS } from '@/store/settingsStore'
import {
  ASSET_PRESETS, PATTERNS, BACKDROPS,
  patternUrl, backdropUrl, CREDITS, COUNTS,
} from '@/assets/catalog'

defineProps({ visible: { type: Boolean, default: false } })
defineEmits(['close'])

const settingsStore = useSettingsStore()

const TABS = [
  { key: 'preset', label: '整套预设' },
  { key: 'photo', label: '摄影背景' },
  { key: 'pattern', label: '纹理图案' },
  { key: 'custom', label: '自定义' },
]
const tab = ref('preset')

const presets = ASSET_PRESETS
const legacyPresets = PRESET_BACKGROUNDS
const credits = CREDITS
const counts = COUNTS

const fileInput = ref(null)
const customPreview = ref(null)
const customBase64 = ref(null)

/** 当前生效的素材参数（预设 + 覆盖项合并结果） */
const parts = computed(() => settingsStore.assetParts)

const colorValue = computed(() => {
  const bg = settingsStore.currentBackground
  return bg.type === 'color' ? bg.value : '#0A0C13'
})

/* —— 分组：把长列表按组切开，避免 24 个图案挤成一大坨 —— */
function groupBy(list) {
  const map = new Map()
  for (const it of list) {
    if (!map.has(it.group)) map.set(it.group, [])
    map.get(it.group).push(it)
  }
  return [...map.entries()].map(([name, items]) => ({ name, items }))
}
const groupedPatterns = computed(() => groupBy(PATTERNS))
const groupedBackdrops = computed(() => groupBy(BACKDROPS))

/* —— 预览样式 —— */

function isPresetActive(id) {
  const bg = settingsStore.currentBackground
  return bg.type === 'asset' && bg.value === id
}

/** 预设卡片的预览：用真实照片做底 + 图案平铺 + 色板条 */
function presetPreviewStyle(p) {
  const url = backdropUrl(p.photo)
  const tile = patternUrl(p.pattern)
  return {
    backgroundImage: url ? `url("${url}")` : 'none',
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    // 图案用 mask 叠一层，颜色取色板第二色 —— 与实际渲染逻辑一致
    '--pv-tile': tile ? `url("${tile}")` : 'none',
    '--pv-tile-size': `${Math.min(p.patternSize || 64, 40)}px`,
    '--pv-color': p.swatch?.[1] || 'var(--accent)',
  }
}

function swatchBg(p) {
  return `linear-gradient(90deg, ${p.swatch?.[0] || '#000'} 0%, ${p.swatch?.[1] || '#fff'} 100%)`
}

/** 图案格子里的小方块：与 texture.css 同样的 mask 着色做法 */
function patternTileStyle(key) {
  const url = patternUrl(key)
  return {
    backgroundColor: 'var(--text-secondary)',
    WebkitMaskImage: `url("${url}")`,
    maskImage: `url("${url}")`,
    WebkitMaskSize: '26px',
    maskSize: '26px',
    WebkitMaskRepeat: 'repeat',
    maskRepeat: 'repeat',
  }
}

/* —— 自定义图 / 纯色 —— */

function onColorChange(v) {
  settingsStore.setBackground({ type: 'color', value: v })
}

function toAssetMode() {
  const last = settingsStore.currentBackground.value
  settingsStore.setAssetPreset(ASSET_PRESETS.some(p => p.id === last) ? last : 'deep-grid')
}

function onFileSelected(e) {
  const f = e.target.files?.[0]
  if (f) processFile(f)
}

function onDrop(e) {
  const f = e.dataTransfer?.files?.[0]
  if (f) processFile(f)
}

function processFile(file) {
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 5MB')
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const img = new Image()
    img.onload = () => {
      // 压缩成 WebP 再存：IndexedDB 里放原图会把库撑到几十 MB，
      // 而后台背景并不需要原始分辨率。
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      canvas.getContext('2d').drawImage(img, 0, 0)
      const webp = canvas.toDataURL('image/webp', 0.82)
      customBase64.value = webp
      customPreview.value = webp
    }
    img.src = reader.result
  }
  reader.readAsDataURL(file)
}

async function applyCustom() {
  if (!customBase64.value) return
  await settingsStore.setCustomBackground(customBase64.value, {
    opacity: settingsStore.currentBackground.opacity ?? 0.8,
    blur: 0,
    scope: 'global',
  })
  ElMessage.success('自定义背景已应用')
}

function clearCustom() {
  customPreview.value = null
  customBase64.value = null
}

function resetDefault() {
  settingsStore.setAssetPreset('deep-grid')
  customPreview.value = null
  customBase64.value = null
  ElMessage.success('已恢复默认素材背景')
}
</script>

<style scoped>
.bg-selector-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 68%, transparent);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.bg-selector {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  width: 720px;
  max-width: 100%;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

/* —— 头部 —— */
.bg-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border-light);
}
.bg-header h3 { font-size: var(--fs-lg); color: var(--text-primary); margin: 0; }
.bg-sub { font-size: var(--fs-sm); color: var(--text-secondary); margin-top: 3px; }
.bg-sub-src { color: var(--text-muted); }
.bg-close {
  background: none; border: none; color: var(--text-muted);
  font-size: var(--fs-lg); cursor: pointer; padding: 2px 6px; border-radius: 6px;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-close:hover { color: var(--text-primary); background: var(--bg-hover); }

/* —— 页签 —— */
.bg-tabs {
  display: flex; gap: 4px; padding: 10px 20px 0;
  border-bottom: 1px solid var(--border-light);
}
.bg-tab {
  padding: 6px 14px; border: none; background: transparent;
  color: var(--text-secondary); font-size: var(--fs-md); font-weight: 500;
  border-radius: 8px 8px 0 0; cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-tab:hover { color: var(--text-primary); background: var(--bg-hover); }
.bg-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

/* —— 内容区 —— */
.bg-pane,
.bg-tune { padding: 14px 20px; }
.bg-selector > section { overflow-y: auto; }
.bg-note { font-size: var(--fs-sm); color: var(--text-muted); margin-bottom: 10px; }
.bg-group { margin-bottom: 14px; }
.bg-group h4 {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-secondary);
  margin-bottom: 7px; letter-spacing: 0.3px;
}
.bg-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  font-size: var(--fs-sm); color: var(--text-muted); margin-bottom: 10px;
}

/* —— 整套预设 —— */
.bg-preset-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
}
.bg-preset {
  position: relative; padding: 0; border: 1px solid var(--border);
  border-radius: 10px; background: var(--bg-secondary); cursor: pointer;
  overflow: hidden; text-align: left;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-preset:hover { border-color: var(--accent); transform: translateY(-2px); }
.bg-preset.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft), 0 6px 20px var(--accent-glow);
}
.bp-preview {
  display: block; height: 62px; position: relative;
  background-color: var(--bg-tertiary);
  background-blend-mode: luminosity;
  opacity: 0.95;
}
/* 图案层：沿用与实际渲染一致的「纯色 + mask」做法 */
.bp-preview::after {
  content: '';
  position: absolute; inset: 0;
  background-color: var(--pv-color);
  -webkit-mask-image: var(--pv-tile);
  mask-image: var(--pv-tile);
  -webkit-mask-size: var(--pv-tile-size);
  mask-size: var(--pv-tile-size);
  -webkit-mask-repeat: repeat;
  mask-repeat: repeat;
  opacity: 0.4;
}
.bp-swatch { display: block; height: 5px; }
.bp-name {
  display: block; font-size: var(--fs-sm); font-weight: 600;
  color: var(--text-primary); padding: 6px 8px 0;
}
.bp-hint {
  display: block; font-size: var(--fs-xs); color: var(--text-muted);
  padding: 1px 8px 7px; line-height: 1.4;
}
.bp-check {
  position: absolute; top: 5px; right: 5px;
  width: 17px; height: 17px; border-radius: 50%;
  background: var(--accent); color: var(--on-accent);
  font-size: var(--fs-xs); display: flex; align-items: center; justify-content: center;
  font-weight: 700;
}

/* —— 摄影背景 —— */
.bg-photo-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.bg-photo {
  position: relative; padding: 0; border: 2px solid transparent;
  border-radius: 8px; overflow: hidden; cursor: pointer; background: var(--bg-tertiary);
  aspect-ratio: 16 / 10;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.bg-photo:hover { transform: scale(1.04); border-color: var(--border); }
.bg-photo.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft), 0 4px 16px var(--accent-glow);
}
.bph-name {
  position: absolute; left: 0; right: 0; bottom: 0;
  font-size: var(--fs-xs); color: #fff; padding: 8px 5px 3px;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.78));
  text-align: left;
}
.bph-check {
  position: absolute; top: 4px; right: 4px;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--accent); color: var(--on-accent);
  font-size: var(--fs-xs); display: flex; align-items: center; justify-content: center;
  font-weight: 700;
}

/* —— 纹理图案 —— */
.bg-pattern-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.bg-pattern {
  padding: 0; border: 2px solid var(--border); border-radius: 8px;
  background: var(--bg-secondary); cursor: pointer; overflow: hidden;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-pattern:hover { border-color: var(--accent); transform: translateY(-2px); }
.bg-pattern.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.bpa-tile {
  display: block; height: 42px; opacity: 0.75;
}
.bpa-name {
  display: block; font-size: var(--fs-xs); color: var(--text-secondary);
  padding: 4px 0 5px; background: var(--bg-tertiary);
}

/* —— 微调滑杆 —— */
.bg-tune {
  border-top: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-tertiary) 40%, transparent);
  flex-shrink: 0;
}
.bg-tune h4 {
  font-size: var(--fs-sm); font-weight: 600; color: var(--text-secondary);
  margin-bottom: 8px;
}
.bg-row {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
  font-size: var(--fs-sm); color: var(--text-secondary);
}
.bg-row label { width: 62px; flex-shrink: 0; }
.bg-row input[type="range"] { flex: 1; accent-color: var(--accent); height: 4px; }
.bg-row b {
  width: 52px; text-align: right; flex-shrink: 0;
  font-family: var(--font-mono); font-size: var(--fs-xs);
  color: var(--text-muted); font-weight: 500;
}

/* —— 自定义 —— */
.bg-color {
  width: 40px; height: 32px; border: 1px solid var(--border);
  border-radius: 6px; background: none; padding: 2px; cursor: pointer;
}
.bg-hex { font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--text-secondary); }
.bg-upload {
  border: 1.5px dashed var(--border); border-radius: 10px;
  padding: 22px; text-align: center; cursor: pointer;
  color: var(--text-muted); font-size: var(--fs-sm);
  display: flex; flex-direction: column; gap: 4px; align-items: center;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-upload:hover {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.bg-upload-preview { max-width: 100%; max-height: 110px; border-radius: 6px; }
.bg-legend { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.bg-legend-item {
  height: 46px; border: 1px solid var(--border); border-radius: 8px;
  cursor: pointer; position: relative; overflow: hidden;
  display: flex; align-items: flex-end; justify-content: center;
  padding-bottom: 4px;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-legend-item:hover { transform: scale(1.03); border-color: var(--accent); }
.bg-legend-item span {
  font-size: var(--fs-xs); color: rgba(0, 0, 0, 0.72);
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.6);
  font-weight: 600;
}

/* —— 底部 —— */
.bg-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 11px 20px; border-top: 1px solid var(--border-light);
  background: var(--bg-primary); flex-shrink: 0;
}
.bg-credits { font-size: var(--fs-xs); color: var(--text-muted); line-height: 1.45; }
.bg-footer-btns { display: flex; gap: 8px; flex-shrink: 0; }
.bg-btn {
  padding: 6px 15px; border: 1px solid var(--border);
  background: var(--bg-secondary); color: var(--text-secondary);
  font-size: var(--fs-sm); border-radius: 7px; cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.bg-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.bg-btn-primary {
  background: var(--accent-fill); color: var(--on-accent); border-color: var(--accent-fill);
}
.bg-btn-primary:hover { background: var(--accent); color: var(--on-accent); }
.bg-btn-sm { padding: 3px 10px; font-size: var(--fs-xs); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
