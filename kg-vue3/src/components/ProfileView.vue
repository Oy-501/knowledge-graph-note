<template>
  <div class="pf-view">
    <header class="pf-head">
      <div>
        <h2>个人主页</h2>
        <p>管理你的资料、头像与自定义背景；上传的图片保存在服务端，换设备/换浏览器依然在。</p>
      </div>
      <el-button @click="$emit('open-admin')">
        <el-icon style="margin-right:4px"><Setting /></el-icon>进入后台管理
      </el-button>
    </header>

    <el-skeleton v-if="loading" :rows="6" animated />

    <div v-else class="pf-grid">
      <!-- 资料 -->
      <section class="pf-card">
        <h3>基本资料</h3>
        <div class="pf-avatar-row">
          <div class="pf-avatar" :style="avatarStyle" @click="pickAvatar">
            <img v-if="avatarUrl" :src="avatarUrl" alt="头像" />
            <span v-else class="pf-avatar-ph">{{ (form.display_name || 'U').slice(0, 1) }}</span>
            <div class="pf-avatar-mask">更换</div>
          </div>
          <div class="pf-avatar-tip">
            <div class="pf-tip-title">头像</div>
            <div class="pf-tip-sub">JPG / PNG / GIF / WebP，≤ {{ maxImageMB }}MB</div>
            <el-button size="small" :loading="uploadingAvatar" @click="pickAvatar">上传头像</el-button>
          </div>
          <input ref="avatarInput" type="file" accept="image/*" hidden @change="onAvatarChange" />
        </div>

        <el-form label-width="70px" size="small" class="pf-form">
          <el-form-item label="昵称">
            <el-input v-model="form.display_name" maxlength="40" placeholder="怎么称呼你" />
          </el-form-item>
          <el-form-item label="简介">
            <el-input v-model="form.bio" type="textarea" :rows="3"
                      maxlength="200" show-word-limit placeholder="一句话介绍自己或这个知识库" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="saveProfile">保存资料</el-button>
          </el-form-item>
        </el-form>
      </section>

      <!-- 背景 -->
      <section class="pf-card">
        <h3>自定义背景</h3>
        <div class="pf-bg-preview" :style="previewStyle">
          <span v-if="!bgUrl" class="pf-bg-empty">尚未上传背景图</span>
          <div v-else class="pf-bg-overlay">
            <span>{{ bgConfig.scope === 'global' ? '全局背景' : '仅工作台' }}</span>
          </div>
        </div>
        <div class="pf-bg-actions">
          <el-button size="small" :loading="uploadingBg" @click="pickBg">上传背景图</el-button>
          <el-button size="small" :disabled="!bgUrl" @click="applyBackground">应用到界面</el-button>
          <el-button size="small" type="danger" plain :disabled="!bgUrl" @click="clearBackground">
            移除
          </el-button>
          <input ref="bgInput" type="file" accept="image/*" hidden @change="onBgChange" />
        </div>
        <div class="pf-sliders">
          <div class="pf-slider-row">
            <span class="pf-slider-label">不透明度</span>
            <el-slider v-model="bgConfig.opacity" :min="0.1" :max="1" :step="0.05" size="small" />
            <span class="pf-slider-val">{{ Math.round(bgConfig.opacity * 100) }}%</span>
          </div>
          <div class="pf-slider-row">
            <span class="pf-slider-label">模糊</span>
            <el-slider v-model="bgConfig.blur" :min="0" :max="20" :step="1" size="small" />
            <span class="pf-slider-val">{{ bgConfig.blur }}px</span>
          </div>
          <div class="pf-slider-row">
            <span class="pf-slider-label">范围</span>
            <el-radio-group v-model="bgConfig.scope" size="small">
              <el-radio-button label="global">全局</el-radio-button>
              <el-radio-button label="editor">仅工作台</el-radio-button>
            </el-radio-group>
          </div>
          <el-button size="small" :loading="saving" @click="saveBackgroundConfig">保存背景设置</el-button>
        </div>
      </section>
    </div>

    <!-- 我的数据 -->
    <section v-if="!loading" class="pf-card">
      <h3>我的数据</h3>
      <div class="pf-stats">
        <div v-for="s in statCards" :key="s.label" class="pf-stat">
          <div class="pfs-val" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="pfs-label">{{ s.label }}</div>
          <div class="pfs-sub">{{ s.sub }}</div>
        </div>
      </div>
      <p class="pf-hint">
        待审知识点可在「后台管理 → 知识点审阅」里逐条确认为知识库条目；
        所有操作都会记录依据，方便回溯。
      </p>
    </section>
  </div>
</template>

<script setup>
/**
 * ProfileView.vue
 * 个人主页：头像 / 背景图上传（存服务端）、资料编辑、我的数据概览、后台入口。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import { profileAPI } from '@/api/index'
import { useSettingsStore } from '@/store/settingsStore'

defineEmits(['open-admin'])

const settingsStore = useSettingsStore()
const loading = ref(true)
const saving = ref(false)
const uploadingAvatar = ref(false)
const uploadingBg = ref(false)
const maxImageMB = ref(5)

const form = ref({ display_name: '', bio: '' })
const bgConfig = ref({ opacity: 0.8, blur: 0, scope: 'global', fit: 'cover' })
const profile = ref(null)
const stats = ref({})
const avatarInput = ref(null)
const bgInput = ref(null)

const avatarUrl = computed(() => profileAPI.fileUrl(profile.value?.avatar_url))
const bgUrl = computed(() => profileAPI.fileUrl(profile.value?.background_url))
const avatarStyle = computed(() => (avatarUrl.value
  ? { backgroundImage: `url(${avatarUrl.value})` } : {}))
const previewStyle = computed(() => {
  if (!bgUrl.value) return { background: 'var(--bg-tertiary)' }
  return {
    backgroundImage: `url(${bgUrl.value})`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    opacity: bgConfig.value.opacity,
    filter: bgConfig.value.blur ? `blur(${bgConfig.value.blur}px)` : 'none'
  }
})

const statCards = computed(() => {
  const s = stats.value || {}
  return [
    { label: '上传文件', value: s.files ?? 0, sub: '个', color: 'var(--accent)' },
    { label: '知识点', value: s.nodes ?? 0, sub: '个', color: 'var(--mint-strong)' },
    { label: '候选知识点', value: s.candidates ?? 0, sub: `已采纳 ${s.accepted ?? 0}`, color: 'var(--apricot-strong)' },
    { label: '待审', value: s.pending_review ?? 0, sub: '需人工确认', color: '#8E7BA8' },
    { label: '知识库条目', value: s.kb_entries ?? 0, sub: '全局共享', color: 'var(--info)' },
    { label: '操作记录', value: s.audit_rows ?? 0, sub: '条审计', color: 'var(--text-muted)' }
  ]
})

async function load() {
  loading.value = true
  try {
    const [p, o] = await Promise.all([profileAPI.get(), profileAPI.overview()])
    profile.value = p.profile
    form.value = { display_name: p.profile.display_name || '', bio: p.profile.bio || '' }
    bgConfig.value = { ...bgConfig.value, ...(p.profile.background_config || {}) }
    stats.value = o.stats || {}
    // 服务端有背景就自动应用一次，保证换设备后界面一致
    if (p.profile.background_url) applyBackground(true)
  } catch (e) {
    ElMessage.error(`个人主页加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

function pickAvatar() { avatarInput.value?.click() }
function pickBg() { bgInput.value?.click() }

async function onAvatarChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (file.size > maxImageMB.value * 1024 * 1024) {
    ElMessage.error(`头像超过 ${maxImageMB.value}MB，请压缩后再上传`)
    return
  }
  uploadingAvatar.value = true
  try {
    const res = await profileAPI.uploadAvatar(file)
    profile.value = res.profile
    ElMessage.success('头像已更新')
  } catch (err) {
    ElMessage.error(err.message || '头像上传失败')
  } finally {
    uploadingAvatar.value = false
  }
}

async function onBgChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (file.size > maxImageMB.value * 1024 * 1024) {
    ElMessage.error(`背景图超过 ${maxImageMB.value}MB，请压缩后再上传`)
    return
  }
  uploadingBg.value = true
  try {
    const res = await profileAPI.uploadBackground(file)
    profile.value = res.profile
    bgConfig.value = { ...bgConfig.value, ...(res.profile.background_config || {}) }
    ElMessage.success('背景图已上传')
    applyBackground(true)
  } catch (err) {
    ElMessage.error(err.message || '背景上传失败')
  } finally {
    uploadingBg.value = false
  }
}

/** 把服务端背景应用到界面（复用现有背景系统） */
async function applyBackground(silent = false) {
  if (!bgUrl.value) return
  await settingsStore.setBackground({
    type: 'custom',
    value: bgUrl.value,
    opacity: bgConfig.value.opacity,
    blur: bgConfig.value.blur,
    scope: bgConfig.value.scope
  })
  if (!silent) ElMessage.success('已应用为界面背景')
}

async function saveProfile() {
  saving.value = true
  try {
    const res = await profileAPI.update({
      display_name: form.value.display_name,
      bio: form.value.bio,
      background_config: bgConfig.value
    })
    profile.value = res.profile
    ElMessage.success('资料已保存')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveBackgroundConfig() {
  saving.value = true
  try {
    const res = await profileAPI.update({ background_config: bgConfig.value })
    profile.value = res.profile
    await applyBackground(true)
    ElMessage.success('背景设置已保存')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function clearBackground() {
  try {
    const res = await profileAPI.clearBackground()
    profile.value = res.profile
    await settingsStore.setPresetBackground('fresh')
    ElMessage.info('已移除自定义背景')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.pf-view { flex: 1; min-width: 0; padding: 16px 20px 40px; height: 100%; overflow-y: auto; background: var(--bg-primary); }
.pf-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.pf-head h2 { margin: 0 0 6px; font-size: 18px; color: var(--text-primary); }
.pf-head p { margin: 0; max-width: 620px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }

.pf-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 980px) { .pf-grid { grid-template-columns: 1fr; } }
.pf-card {
  background: var(--bg-secondary); border: 1px solid var(--border-light);
  border-radius: var(--radius); padding: 14px 16px; margin-bottom: 14px; box-shadow: var(--shadow-sm);
}
.pf-card h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: 13.5px; color: var(--text-primary); }

.pf-avatar-row { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.pf-avatar {
  position: relative; width: 72px; height: 72px; border-radius: 50%;
  overflow: hidden; cursor: pointer; flex-shrink: 0;
  background: var(--bg-tertiary); background-size: cover; background-position: center;
  border: 2px solid var(--border-light);
  display: flex; align-items: center; justify-content: center;
}
.pf-avatar img { width: 100%; height: 100%; object-fit: cover; }
.pf-avatar-ph { font-size: 24px; font-weight: 700; color: var(--accent); }
.pf-avatar-mask {
  position: absolute; inset: auto 0 0 0; background: rgba(0,0,0,0.45);
  color: #fff; font-size: 11px; text-align: center; padding: 2px 0; opacity: 0; transition: opacity .15s;
}
.pf-avatar:hover .pf-avatar-mask { opacity: 1; }
.pf-tip-title { font-size: 12.5px; color: var(--text-primary); }
.pf-tip-sub { font-size: 11px; color: var(--text-muted); margin: 2px 0 6px; }
.pf-form { margin-top: 4px; }

.pf-bg-preview {
  position: relative; height: 150px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-light); overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background-size: cover; background-position: center;
}
.pf-bg-empty { font-size: 12px; color: var(--text-muted); }
.pf-bg-overlay {
  position: absolute; right: 8px; bottom: 8px; font-size: 11px; color: #fff;
  background: rgba(0,0,0,0.4); border-radius: var(--radius-full); padding: 2px 8px;
}
.pf-bg-actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
.pf-sliders { display: flex; flex-direction: column; gap: 6px; }
.pf-slider-row { display: flex; align-items: center; gap: 10px; }
.pf-slider-label { width: 62px; font-size: 12px; color: var(--text-secondary); flex-shrink: 0; }
.pf-slider-row :deep(.el-slider) { flex: 1; }
.pf-slider-val { width: 44px; font-size: 11.5px; color: var(--text-muted); text-align: right; }

.pf-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.pf-stat { background: var(--bg-tertiary); border-radius: var(--radius-sm); padding: 10px 12px; }
.pfs-val { font-size: 22px; font-weight: 700; line-height: 1.15; }
.pfs-label { font-size: 12px; color: var(--text-primary); margin-top: 2px; }
.pfs-sub { font-size: 11px; color: var(--text-muted); }
.pf-hint { font-size: 11.5px; color: var(--text-muted); margin: 12px 0 0; line-height: 1.6; }
</style>
