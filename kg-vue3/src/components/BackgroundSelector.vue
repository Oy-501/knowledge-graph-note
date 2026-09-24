<template>
  <Transition name="fade">
    <div v-if="visible" class="bg-selector-overlay" @click.self="$emit('close')">
      <div class="bg-selector">
        <div class="bg-header">
          <h3>🖼️ 背景主题</h3>
          <button type="button" class="bg-close" @click="$emit('close')">✕</button>
        </div>
        <div class="bg-section">
          <h4>预设主题</h4>
          <div class="bg-presets">
            <div v-for="preset in presets" :key="preset.id" class="bg-preset-item" :class="{ active: settingsStore.currentBackground.type === 'preset' && settingsStore.currentBackground.value === preset.id }" :style="{ background: preset.gradient }" @click="onSelectPreset(preset.id)" :title="preset.name + ' - ' + preset.desc">
              <span class="bg-preset-name">{{ preset.name }}</span>
              <span class="bg-preset-desc">{{ preset.desc }}</span>
              <span v-if="settingsStore.currentBackground.type === 'preset' && settingsStore.currentBackground.value === preset.id" class="bg-preset-check">✓</span>
            </div>
          </div>
        </div>
        <div class="bg-section">
          <h4>纯色背景</h4>
          <div class="bg-color-row">
            <input type="color" :value="settingsStore.currentBackground.type === 'color' ? settingsStore.currentBackground.value : '#1a1a2e'" class="bg-color-picker" @input="onColorChange($event.target.value)" />
            <span class="bg-color-hex">{{ settingsStore.currentBackground.type === 'color' ? settingsStore.currentBackground.value : '#1a1a2e' }}</span>
            <button type="button" v-if="settingsStore.currentBackground.type === 'color'" class="bg-btn bg-btn-sm" @click="onApplyColor">应用</button>
          </div>
        </div>
        <div class="bg-section">
          <h4>自定义背景</h4>
          <div class="bg-upload-zone" @click="triggerUpload" @dragover.prevent @drop.prevent="onDrop">
            <span v-if="!customPreview">点击上传或拖拽图片到此处</span>
            <img v-else :src="customPreview" class="bg-custom-preview" />
            <span class="bg-upload-hint">JPG, PNG, WebP (≤5MB)</span>
          </div>
          <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" style="display:none" @change="onFileSelected" />
          <div v-if="customPreview" class="bg-custom-controls">
            <div class="bg-control-row"><span>透明度</span><input type="range" min="0" max="100" :value="customOpacity" class="bg-slider" @input="customOpacity = Number($event.target.value)" /><span class="bg-control-val">{{ customOpacity }}%</span></div>
            <div class="bg-control-row"><span>模糊度</span><input type="range" min="0" max="20" :value="customBlur" class="bg-slider" @input="customBlur = Number($event.target.value)" /><span class="bg-control-val">{{ customBlur }}px</span></div>
            <div class="bg-custom-actions"><button type="button" class="bg-btn bg-btn-primary" @click="onApplyCustom">应用背景</button><button type="button" class="bg-btn" @click="onClearCustom">清除</button></div>
          </div>
        </div>
        <div class="bg-section">
          <h4>应用范围</h4>
          <div class="bg-scope-row">
            <button type="button" class="bg-scope-btn" :class="{ active: settingsStore.currentBackground.scope === 'editor' }" @click="settingsStore.setBackgroundScope('editor')">仅编辑器</button>
            <button type="button" class="bg-scope-btn" :class="{ active: settingsStore.currentBackground.scope === 'workbench' }" @click="settingsStore.setBackgroundScope('workbench')">整个工作台</button>
            <button type="button" class="bg-scope-btn" :class="{ active: settingsStore.currentBackground.scope === 'global' }" @click="settingsStore.setBackgroundScope('global')">全局</button>
          </div>
        </div>
        <div class="bg-footer">
          <button type="button" class="bg-btn" @click="onResetDefault">恢复默认</button>
          <button type="button" class="bg-btn bg-btn-primary" @click="$emit('close')">完成</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore, PRESET_BACKGROUNDS } from '@/store/settingsStore'

defineProps({ visible: { type: Boolean, default: false } })
defineEmits(['close'])
const settingsStore = useSettingsStore()
const presets = PRESET_BACKGROUNDS
const fileInput = ref(null); const customPreview = ref(null); const customBase64 = ref(null); const customOpacity = ref(80); const customBlur = ref(0)

function onSelectPreset(presetId) { settingsStore.setPresetBackground(presetId) }
function onColorChange(color) { settingsStore.setColorBackground(color) }
function onApplyColor() { settingsStore.setBackgroundScope(settingsStore.currentBackground.scope || 'editor') }
function triggerUpload() { fileInput.value?.click() }
function onFileSelected(e) { const file = e.target.files?.[0]; if (!file) return; processFile(file) }
function onDrop(e) { const file = e.dataTransfer?.files?.[0]; if (!file) return; processFile(file) }
function processFile(file) {
  if (file.size > 5 * 1024 * 1024) { ElMessage.warning('图片大小不能超过 5MB'); return }
  const reader = new FileReader()
  reader.onload = () => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height
      const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0)
      const webp = canvas.toDataURL('image/webp', 0.8)
      customBase64.value = webp; customPreview.value = webp
    }
    img.src = reader.result
  }
  reader.readAsDataURL(file)
}
function onApplyCustom() {
  if (!customBase64.value) return
  settingsStore.setCustomBackground(customBase64.value, { opacity: customOpacity.value / 100, blur: customBlur.value, scope: settingsStore.currentBackground.scope })
  ElMessage.success('自定义背景已应用')
}
function onClearCustom() { customPreview.value = null; customBase64.value = null; customOpacity.value = 80; customBlur.value = 0 }
function onResetDefault() { settingsStore.setPresetBackground('dark_night'); settingsStore.setBackgroundScope('editor'); customPreview.value = null; customBase64.value = null; ElMessage.success('已恢复默认背景') }
</script>

<style scoped>
.bg-selector-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 1200; display: flex; align-items: center; justify-content: center; }
.bg-selector { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 12px; width: 480px; max-height: 85vh; overflow-y: auto; box-shadow: var(--shadow-lg); padding: 20px; }
.bg-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.bg-header h3 { font-size: 16px; color: var(--text-primary); margin: 0; }
.bg-close { background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; padding: 4px; }
.bg-section { margin-bottom: 16px; }
.bg-section h4 { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; }
.bg-presets { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.bg-preset-item { height: 70px; border-radius: 8px; cursor: pointer; position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 2px solid transparent; transition: all 0.2s; overflow: hidden; }
.bg-preset-item:hover { transform: scale(1.05); }
.bg-preset-item.active { border-color: var(--accent); box-shadow: 0 0 12px rgba(91,155,243,0.4); }
.bg-preset-name { font-size: 11px; font-weight: 600; color: rgba(0,0,0,0.7); text-shadow: 0 1px 2px rgba(255,255,255,0.5); }
.bg-preset-desc { font-size: 9px; color: rgba(0,0,0,0.5); }
.bg-preset-check { position: absolute; top: 4px; right: 6px; font-size: 12px; color: var(--accent); font-weight: 700; }
.bg-color-row { display: flex; align-items: center; gap: 10px; }
.bg-color-picker { width: 36px; height: 36px; border: 2px solid var(--border); border-radius: 6px; cursor: pointer; background: none; padding: 2px; }
.bg-color-hex { font-size: 12px; font-family: var(--font-mono); color: var(--text-secondary); }
.bg-upload-zone { border: 2px dashed var(--border); border-radius: 8px; padding: 24px; text-align: center; cursor: pointer; transition: all 0.2s; color: var(--text-muted); font-size: 12px; }
.bg-upload-zone:hover { border-color: var(--accent); background: var(--bg-hover); }
.bg-custom-preview { max-width: 100%; max-height: 120px; border-radius: 6px; margin-bottom: 6px; }
.bg-upload-hint { display: block; font-size: 10px; color: var(--text-muted); margin-top: 4px; }
.bg-custom-controls { margin-top: 10px; }
.bg-control-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; color: var(--text-secondary); }
.bg-slider { flex: 1; accent-color: var(--accent); height: 4px; }
.bg-control-val { font-size: 10px; font-family: var(--font-mono); color: var(--text-muted); width: 32px; text-align: right; }
.bg-custom-actions { display: flex; gap: 6px; margin-top: 8px; }
.bg-scope-row { display: flex; gap: 6px; }
.bg-scope-btn { flex: 1; padding: 6px 0; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-secondary); font-size: 11px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.bg-scope-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.bg-scope-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.bg-footer { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-light); }
.bg-btn { padding: 6px 16px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-secondary); font-size: 12px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.bg-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.bg-btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.bg-btn-primary:hover { opacity: 0.9; }
.bg-btn-sm { padding: 3px 10px; font-size: 11px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
