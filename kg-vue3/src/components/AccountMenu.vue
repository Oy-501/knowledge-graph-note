<template>
  <div ref="rootRef" class="am-root">
    <!-- 触发按钮：头像首字 + 名字 + 展开箭头 -->
    <button
      type="button"
      class="am-trigger click-scale"
      :aria-expanded="open"
      aria-haspopup="menu"
      :title="`${auth.displayName}（${roleText}）`"
      @click="toggle"
    >
      <span class="am-avatar" aria-hidden="true">{{ initial }}</span>
      <span class="am-name">{{ auth.displayName }}</span>
      <svg class="am-caret" :class="{ 'is-open': open }" viewBox="0 0 24 24"
           width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2">
        <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <!-- 下拉菜单（自定义：与全站风格一致，也省掉一层 Element Plus 弹层的 z-index 纠缠） -->
    <transition name="am-fade">
      <div v-if="open" class="am-menu" role="menu">
        <div class="am-menu-head">
          <div class="am-menu-name">{{ auth.displayName }}</div>
          <div class="am-menu-meta">
            <span class="am-role" :class="auth.isAdmin ? 'is-admin' : 'is-user'">{{ roleText }}</span>
            <span class="am-menu-user">@{{ auth.user?.username }}</span>
          </div>
        </div>

        <button type="button" class="am-item" role="menuitem" @click="openPasswordDialog">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
               stroke="currentColor" stroke-width="1.7">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7.5a4 4 0 0 1 8 0V10" stroke-linecap="round" />
          </svg>
          <span>修改密码</span>
        </button>

        <button type="button" class="am-item am-item-danger" role="menuitem" @click="onLogout">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
               stroke="currentColor" stroke-width="1.7">
            <path d="M15 17l5-5-5-5M20 12H9M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6"
                  stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span>退出登录</span>
        </button>
      </div>
    </transition>

    <!-- 修改密码 -->
    <el-dialog
      v-model="pwdVisible"
      title="修改密码"
      width="380px"
      append-to-body
      :close-on-click-modal="false"
    >
      <div v-if="pwdError" class="am-alert">
        <div class="am-alert-title">{{ pwdError.message }}</div>
        <div v-if="pwdError.hint" class="am-alert-hint">{{ pwdError.hint }}</div>
      </div>

      <label class="am-field">
        <span class="am-label">当前密码</span>
        <input v-model="pwd.oldPassword" class="am-input" type="password"
               autocomplete="current-password" :disabled="pwdBusy" placeholder="现在使用的密码" />
      </label>
      <label class="am-field">
        <span class="am-label">新密码</span>
        <input v-model="pwd.newPassword" class="am-input" type="password"
               autocomplete="new-password" :disabled="pwdBusy" placeholder="至少 6 位" />
      </label>
      <label class="am-field">
        <span class="am-label">确认新密码</span>
        <input v-model="pwd.confirm" class="am-input" type="password"
               autocomplete="new-password" :disabled="pwdBusy" placeholder="再输一次"
               @keydown.enter="submitPassword" />
      </label>

      <p class="am-note">
        改密后本机所有登录都会失效，需要用新密码重新登录。
      </p>

      <template #footer>
        <el-button :disabled="pwdBusy" @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdBusy" @click="submitPassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * AccountMenu.vue
 * 导航栏右侧的账号入口：显示当前登录者，提供「修改密码 / 退出登录」。
 *
 * 为什么必须有它：
 * 登录页把「怎么进来」解决了，但如果界面上没有出口，用户就退不出去 ——
 * 尤其换来一台机器或想换账号时会很尴尬。这是登录功能的一半。
 */
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/store/authStore'

const auth = useAuthStore()

const rootRef = ref(null)
const open = ref(false)
const pwdVisible = ref(false)
const pwdBusy = ref(false)
const pwdError = ref(null)
const pwd = reactive({ oldPassword: '', newPassword: '', confirm: '' })

const initial = computed(() => (auth.displayName || '?').trim().charAt(0).toUpperCase())
const roleText = computed(() => (auth.isAdmin ? '管理员' : '普通用户'))

function toggle() {
  open.value = !open.value
}

/** 点外面或按 Esc 关掉菜单（不自建这两件事，菜单会一直挂在屏幕上） */
function onDocClick(e) {
  if (!open.value) return
  if (!rootRef.value?.contains(e.target)) open.value = false
}
function onDocKeydown(e) {
  if (e.key === 'Escape' && open.value) open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onDocKeydown)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick, true)
  document.removeEventListener('keydown', onDocKeydown)
})

function openPasswordDialog() {
  open.value = false
  pwdError.value = null
  pwd.oldPassword = ''
  pwd.newPassword = ''
  pwd.confirm = ''
  pwdVisible.value = true
}

// 关掉弹窗就把残留的密码清掉，避免下次打开还留着上一次的输入
watch(pwdVisible, v => {
  if (!v) {
    pwd.oldPassword = ''
    pwd.newPassword = ''
    pwd.confirm = ''
    pwdError.value = null
  }
})

async function submitPassword() {
  if (pwdBusy.value) return
  pwdError.value = null

  if (!pwd.oldPassword) { pwdError.value = { message: '请填写当前密码' }; return }
  if (pwd.newPassword.length < 6) { pwdError.value = { message: '新密码至少 6 位' }; return }
  if (pwd.newPassword !== pwd.confirm) {
    pwdError.value = { message: '两次输入的新密码不一致' }
    return
  }
  if (pwd.newPassword === pwd.oldPassword) {
    pwdError.value = { message: '新密码不能与当前密码相同' }
    return
  }

  pwdBusy.value = true
  try {
    const res = await auth.changePassword({
      oldPassword: pwd.oldPassword,
      newPassword: pwd.newPassword,
    })
    pwdVisible.value = false
    // store 里的 changePassword 已经把本地会话清掉了，App 会自动切回登录页
    ElMessage.success(res?.message || '密码已更新，请重新登录')
  } catch (e) {
    pwdError.value = { message: e?.message || '修改失败', hint: e?.hint || '' }
  } finally {
    pwdBusy.value = false
  }
}

async function onLogout() {
  open.value = false
  try {
    await ElMessageBox.confirm('退出后需要重新登录才能进行写操作。', '退出登录', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return   // 用户取消
  }
  await auth.logout()
  ElMessage.success('已退出登录')
}
</script>

<style scoped>
.am-root { position: relative; }

/* ===== 触发按钮 ===== */
.am-trigger {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 8px 0 3px;
  max-width: 160px;
  font-family: inherit;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out),
              color var(--dur-fast) var(--ease-out);
}
.am-trigger:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--border-light);
}
.am-avatar {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--on-accent);
  background: var(--accent-fill);
  border-radius: 50%;
}
.am-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.am-caret {
  flex-shrink: 0;
  opacity: 0.6;
  transition: transform var(--dur-fast) var(--ease-out);
}
.am-caret.is-open { transform: rotate(180deg); }

/* ===== 下拉菜单 ===== */
.am-menu {
  position: absolute;
  top: calc(100% + 7px);
  right: 0;
  z-index: 1200;
  width: 196px;
  padding: 5px;
  /* 弹层必须不透明：它浮在内容之上，透了会看不清（见 main.css 的约定） */
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
}
.am-menu-head {
  padding: 8px 9px 9px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border-light);
}
.am-menu-name {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.am-menu-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
}
.am-role {
  padding: 1px 6px;
  font-size: var(--fs-xs);
  font-weight: 600;
  border-radius: var(--radius-full);
}
.am-role.is-admin { color: var(--accent-fill); background: var(--accent-soft); }
.am-role.is-user { color: var(--violet-text); background: var(--violet-soft); }
.am-menu-user {
  font-size: var(--fs-xs);
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.am-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 9px;
  font-family: inherit;
  font-size: var(--fs-md);
  color: var(--text-secondary);
  text-align: left;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out),
              color var(--dur-fast) var(--ease-out);
}
.am-item:hover { color: var(--text-primary); background: var(--bg-hover); }
.am-item-danger:hover { color: var(--danger); background: var(--danger-soft); }

/* 菜单出现/消失：轻微缩放 + 淡入，避免生硬 */
.am-fade-enter-active, .am-fade-leave-active {
  transition: opacity var(--dur-fast) var(--ease-out),
              transform var(--dur-fast) var(--ease-out);
}
.am-fade-enter-from, .am-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

/* ===== 改密弹窗 ===== */
.am-alert {
  padding: 9px 11px;
  margin-bottom: 13px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
}
.am-alert-title { font-size: var(--fs-md); font-weight: 600; color: var(--danger); }
.am-alert-hint { margin-top: 4px; font-size: var(--fs-sm); color: var(--text-secondary); line-height: 1.55; }

.am-field { display: block; margin-bottom: 12px; }
.am-label {
  display: block;
  margin-bottom: 6px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.am-input {
  width: 100%;
  height: 36px;
  padding: 0 11px;
  font-family: inherit;
  font-size: var(--fs-base);
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out),
              box-shadow var(--dur-fast) var(--ease-out);
}
.am-input:focus {
  border-color: var(--accent-fill);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.am-input:disabled { opacity: 0.6; }

.am-note {
  margin: 4px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-faint);
  line-height: 1.55;
}

@media (prefers-reduced-motion: reduce) {
  .am-fade-enter-active, .am-fade-leave-active { transition: none; }
}
</style>
