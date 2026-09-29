<template>
  <div class="lg-view">
    <div class="lg-card" :class="{ 'is-ready': ready }">
      <!-- 品牌 -->
      <header class="lg-brand">
        <span class="lg-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="32" height="32" fill="none">
            <path d="M9 11.5 L23 8 M9 11.5 L16 24 M23 8 L16 24 M9 11.5 L23 20.5"
                  stroke="currentColor" stroke-width="1.3" stroke-linecap="round" opacity=".38" />
            <circle cx="9" cy="11.5" r="3.4" fill="currentColor" />
            <circle cx="23" cy="8" r="2.4" fill="currentColor" opacity=".62" />
            <circle cx="16" cy="24" r="3.0" fill="currentColor" opacity=".82" />
            <circle cx="23" cy="20.5" r="2.1" fill="currentColor" opacity=".45" />
          </svg>
        </span>
        <div class="lg-brand-text">
          <h1 class="lg-title">{{ headline.title }}</h1>
          <p class="lg-sub">{{ headline.sub }}</p>
        </div>
      </header>

      <!-- 后端连不上：不给表单，直接说清楚怎么回事 -->
      <div v-if="auth.probeError" class="lg-blocker">
        <div class="lg-alert lg-alert-danger">
          <div class="lg-alert-icon">!</div>
          <div class="lg-alert-body">
            <div class="lg-alert-title">连不上后端服务</div>
            <div class="lg-alert-text">{{ auth.probeError }}</div>
            <div class="lg-alert-hint">
              请确认后端已启动（项目根目录的 <code>启动服务.bat</code>），
              且前端 <code>VITE_API_BASE</code> 指向它。
            </div>
          </div>
        </div>
        <button type="button" class="lg-btn lg-btn-ghost" :disabled="auth.probing" @click="retryProbe">
          {{ auth.probing ? '重试中…' : '重新连接' }}
        </button>
      </div>

      <template v-else>
        <!-- 初始化提示（只在首次出现） -->
        <div v-if="mode === 'bootstrap'" class="lg-alert lg-alert-info">
          <div class="lg-alert-icon">1</div>
          <div class="lg-alert-body">
            <div class="lg-alert-title">首次使用，先建管理员账号</div>
            <div class="lg-alert-text">
              这一步会创建一个管理员账号。<strong>你已有的文件、节点与笔记都归它所有</strong>，
              不会丢失，也不需要迁移。
            </div>
            <div class="lg-alert-hint">
              密码由你在这里设定，之后用它登录。也可以随时在 <code>backend/.env</code>
              的 <code>ADMIN_TOKEN</code> 之外不再关心任何密钥。
            </div>
          </div>
        </div>

        <!-- 错误 -->
        <div v-if="error" class="lg-alert lg-alert-danger">
          <div class="lg-alert-icon">!</div>
          <div class="lg-alert-body">
            <div class="lg-alert-title">{{ error.message }}</div>
            <div v-if="error.hint" class="lg-alert-hint">{{ error.hint }}</div>
            <div v-if="error.retryAfter" class="lg-alert-hint">
              请等待 <strong>{{ error.retryAfter }}</strong> 秒后重试。
            </div>
          </div>
        </div>

        <form class="lg-form" novalidate @submit.prevent="submit">
          <label class="lg-field">
            <span class="lg-label">用户名</span>
            <input
              ref="userRef"
              v-model.trim="form.username"
              class="lg-input"
              type="text"
              name="username"
              autocomplete="username"
              :placeholder="mode === 'login' ? '你的用户名' : '2~32 个字符'"
              :disabled="busy"
              @keydown="onFieldKey"
            />
          </label>

          <label v-if="mode !== 'login'" class="lg-field">
            <span class="lg-label">
              显示名称
              <em class="lg-optional">可选</em>
            </span>
            <input
              v-model.trim="form.displayName"
              class="lg-input"
              type="text"
              name="nickname"
              autocomplete="nickname"
              placeholder="界面上展示的称呼，留空就用用户名"
              :disabled="busy"
            />
          </label>

          <label class="lg-field">
            <span class="lg-label">密码</span>
            <span class="lg-input-wrap">
              <input
                ref="pwdRef"
                v-model="form.password"
                class="lg-input"
                :type="showPassword ? 'text' : 'password'"
                name="password"
                :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
                :placeholder="mode === 'login' ? '你的密码' : '至少 6 位'"
                :disabled="busy"
                @keydown="onFieldKey"
                @keyup="onFieldKey"
              />
              <button
                type="button"
                class="lg-eye"
                :title="showPassword ? '隐藏密码' : '显示密码'"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                :aria-pressed="showPassword"
                tabindex="-1"
                @click="showPassword = !showPassword"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
                     stroke="currentColor" stroke-width="1.7">
                  <path v-if="!showPassword"
                        d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" />
                  <circle v-if="!showPassword" cx="12" cy="12" r="2.6" />
                  <path v-else d="M4 4l16 16M9.9 5.7A9.8 9.8 0 0 1 12 5.5c6.4 0 10 6.5 10 6.5a17 17 0 0 1-3.6 4.2M6.3 7.2A16.6 16.6 0 0 0 2 12s3.6 6.5 10 6.5c1.2 0 2.3-.2 3.3-.6" />
                </svg>
              </button>
            </span>
            <!-- 大写锁定是密码输错最常见的原因，实时提示比事后报「密码不正确」有用 -->
            <span v-if="capsOn" class="lg-caps">已开启大写锁定 Caps Lock</span>
          </label>

          <label v-if="mode !== 'login'" class="lg-field">
            <span class="lg-label">确认密码</span>
            <input
              v-model="form.confirm"
              class="lg-input"
              :type="showPassword ? 'text' : 'password'"
              name="confirm"
              autocomplete="new-password"
              placeholder="再输一次"
              :disabled="busy"
              @keydown="onFieldKey"
            />
          </label>

          <button type="submit" class="lg-btn lg-btn-primary" :disabled="busy || !canSubmit">
            <span v-if="busy" class="lg-spin" aria-hidden="true"></span>
            <span>{{ busy ? busyText : submitText }}</span>
          </button>
        </form>

        <!-- 登录 / 注册 切换：只有开放注册时才显示 -->
        <footer v-if="auth.registrationOpen" class="lg-foot">
          <template v-if="mode === 'login'">
            <span class="lg-foot-text">还没有账号？</span>
            <button type="button" class="lg-link" @click="switchMode('register')">注册一个</button>
          </template>
          <template v-else>
            <span class="lg-foot-text">已经有账号了？</span>
            <button type="button" class="lg-link" @click="switchMode('login')">去登录</button>
          </template>
        </footer>

        <p class="lg-note">
          <template v-if="mode === 'bootstrap'">
            密码只保存在本机后端（bcrypt 哈希），不会上传到任何地方。
          </template>
          <template v-else>
            登录后本机记住会话，{{ auth.sessionTtlDays }} 天内不用重复登录。
          </template>
        </p>
      </template>
    </div>
  </div>
</template>

<script setup>
/**
 * LoginView.vue
 * 登录页：把「首次初始化 / 登录 / 注册」三种形态合在一张卡片里。
 *
 * 为什么要合成一个页面而不是三个路由：
 * 三者互斥且都由同一个探测结果决定（need_bootstrap / registration_open），
 * 分成三个页面就要各自再探一次，还会出现「探测没回来先渲染错表单」的闪烁。
 *
 * 视觉上刻意保持**容器透明**：背景层（.app-tex）在 App.vue 里，登录页
 * 直接用用户自己设置的背景，看起来和应用是一体的，而不是另一个系统。
 */
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useAuthStore } from '@/store/authStore'

const auth = useAuthStore()

const mode = ref('login')          // login | bootstrap | register
const busy = ref(false)
const error = ref(null)
const showPassword = ref(false)
const capsOn = ref(false)
const userRef = ref(null)
const pwdRef = ref(null)

const form = reactive({ username: '', password: '', confirm: '', displayName: '' })

// 探测完成前不渲染表单：否则会先闪一下「登录」，再跳成「初始化」
const ready = computed(() => auth.ready)

const headline = computed(() => {
  if (!ready.value) return { title: '知识图谱笔记', sub: '正在检查登录状态…' }
  if (mode.value === 'bootstrap') return { title: '初始化系统', sub: '创建你的管理员账号，然后开始使用' }
  if (mode.value === 'register') return { title: '注册账号', sub: '创建一个普通账号用于查看数据' }
  return { title: '登录', sub: '登录后继续整理你的知识图谱' }
})

const submitText = computed(() => (
  mode.value === 'bootstrap' ? '创建管理员账号'
    : mode.value === 'register' ? '注册并登录'
      : '登录'
))

const busyText = computed(() => (
  mode.value === 'bootstrap' ? '正在创建…'
    : mode.value === 'register' ? '正在注册…'
      : '正在登录…'
))

const canSubmit = computed(() => {
  if (!form.username || !form.password) return false
  if (mode.value !== 'login' && form.password !== form.confirm) return false
  if (mode.value !== 'login' && form.password.length < 6) return false
  return true
})

/** 探测结果决定初始形态：未初始化 → 直接进初始化，否则登录 */
function syncModeFromProbe() {
  if (auth.needBootstrap) mode.value = 'bootstrap'
  else if (mode.value === 'bootstrap') mode.value = 'login'
}

watch(() => auth.needBootstrap, syncModeFromProbe)

onMounted(async () => {
  await auth.probe()
  syncModeFromProbe()
  await nextTick()
  // 光标直接落在第一个待填字段：少一次点击
  const target = mode.value === 'bootstrap' ? userRef.value : (form.username ? pwdRef.value : userRef.value)
  target?.focus?.()
})

function switchMode(next) {
  mode.value = next
  error.value = null
  form.password = ''
  form.confirm = ''
  nextTick(() => userRef.value?.focus?.())
}

/** 大写锁定检测（keyup 才能拿到 getModifierState 的准确值） */
function onFieldKey(e) {
  try {
    capsOn.value = !!e.getModifierState?.('CapsLock')
  } catch {
    capsOn.value = false   // 老浏览器没有该方法，静默忽略
  }
}

function retryProbe() {
  auth.probeError = ''
  auth.probe()
}

/** 把后端的 ApiError 拆成「原因 + 怎么办」两块来展示 */
function toFormError(e) {
  const retryAfter = e?.hint?.match(/(\d+)\s*秒/)?.[1] || null
  return {
    message: e?.message || '操作失败，请重试',
    hint: e?.hint || '',
    retryAfter,
  }
}

async function submit() {
  if (busy.value) return
  error.value = null

  // 本地先做一遍校验，省一次必然失败的往返（后端的校验仍然保留）
  if (!form.username) { error.value = { message: '请填写用户名' }; return }
  if (!form.password) { error.value = { message: '请填写密码' }; return }
  if (mode.value !== 'login') {
    if (form.password.length < 6) { error.value = { message: '密码至少 6 位' }; return }
    if (form.password !== form.confirm) { error.value = { message: '两次输入的密码不一致', hint: '请确认「确认密码」与上面完全一致。' }; return }
  }

  busy.value = true
  try {
    if (mode.value === 'bootstrap') {
      await auth.bootstrap({
        username: form.username,
        password: form.password,
        displayName: form.displayName,
      })
    } else if (mode.value === 'register') {
      await auth.register({ username: form.username, password: form.password })
    } else {
      await auth.login({ username: form.username, password: form.password })
    }
    // 成功后不需要跳转：App.vue 以 auth.isAuthed 为门禁，store 一变就切到应用
    form.password = ''
    form.confirm = ''
  } catch (e) {
    error.value = toFormError(e)
    // 失败后把密码清掉并聚焦回去：多数失败是打错了，留着更容易连错
    form.password = ''
    form.confirm = ''
    nextTick(() => pwdRef.value?.focus?.())
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
/* ===== 容器：透明，让用户自己的背景透上来 ===== */
.lg-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  padding: 28px 20px 40px;
}

/* ===== 卡片 ===== */
.lg-card {
  width: 100%;
  max-width: 396px;
  /*
   * 用 margin:auto 居中，**不要**用 align-items:center ——
   * 这是 flex 居中一个很常见的坑：当卡片比容器高时（窗口小、或初始化表单字段多，
   * 必然发生），align-items:center 会把溢出部分顶到容器上方，
   * 而滚动条只能往下滚 → **卡片顶部永远看不到**（品牌和标题被切掉）。
   * margin:auto 在空间充足时同样居中，空间不足时退化成正常文档流，能滚到顶。
   * 实测：566px 高的窗口里卡片 672px，用 align-items 时顶部被裁掉约 106px。
   */
  margin: auto;
  padding: 24px 24px 20px;
  /* 半透明 + 毛玻璃：与全站「视图透明、面板半透明」的约定一致。
     0.92 而不是更低，是为了保住表单文字的对比度（见 main.css 的 --surface-* 说明） */
  background: color-mix(in srgb, var(--bg-secondary) 92%, transparent);
  backdrop-filter: blur(20px) saturate(1.25);
  -webkit-backdrop-filter: blur(20px) saturate(1.25);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  /* 入场：轻微上浮。响应 prefers-reduced-motion，见文件末尾 */
  opacity: 0;
  transform: translateY(10px);
  animation: lg-in var(--dur-base) var(--ease-out) forwards;
}
.lg-card.is-ready { opacity: 1; }

@keyframes lg-in {
  to { opacity: 1; transform: none; }
}

/* ===== 品牌 ===== */
.lg-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.lg-mark {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  color: var(--accent-fill);
  background: var(--accent-soft);
  border-radius: var(--radius);
}
.lg-brand-text { min-width: 0; }
.lg-title {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}
.lg-sub {
  margin: 3px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-muted);
  line-height: 1.5;
}

/* ===== 提示条 ===== */
.lg-alert {
  display: flex;
  gap: 10px;
  padding: 11px 13px;
  margin-bottom: 14px;
  border-radius: var(--radius);
  border: 1px solid transparent;
  border-left-width: 3px;
}
.lg-alert-info {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.lg-alert-danger {
  background: var(--danger-soft);
  border-color: var(--danger);
}
.lg-alert-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: var(--fs-sm);
  font-weight: 700;
  color: #fff;
  background: var(--accent);
}
.lg-alert-danger .lg-alert-icon { background: var(--danger); }
.lg-alert-body { min-width: 0; flex: 1; }
.lg-alert-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.45;
}
.lg-alert-text {
  margin-top: 4px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}
.lg-alert-hint {
  margin-top: 5px;
  font-size: var(--fs-sm);
  color: var(--text-muted);
  line-height: 1.6;
}
.lg-alert code {
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* ===== 表单 ===== */
.lg-form {
  display: flex;
  flex-direction: column;
  gap: 13px;
}
.lg-field { display: block; }
.lg-label {
  display: block;
  margin-bottom: 6px;
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-secondary);
}
.lg-optional {
  margin-left: 5px;
  font-style: normal;
  font-size: var(--fs-xs);
  color: var(--text-faint);
}
.lg-input-wrap { position: relative; display: block; }

.lg-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  font-family: inherit;
  font-size: var(--fs-base);
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out),
              box-shadow var(--dur-fast) var(--ease-out),
              background-color var(--dur-fast) var(--ease-out);
}
.lg-input::placeholder { color: var(--text-faint); }
.lg-input:hover:not(:disabled) { border-color: var(--accent-light); }
.lg-input:focus {
  background: var(--bg-secondary);
  border-color: var(--accent-fill);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.lg-input:disabled { opacity: 0.6; cursor: not-allowed; }

/* 密码框右侧的显示/隐藏按钮：给输入框留出空间，别压到文字 */
.lg-input-wrap .lg-input { padding-right: 40px; }
.lg-eye {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out),
              background-color var(--dur-fast) var(--ease-out);
}
.lg-eye:hover { color: var(--text-primary); background: var(--bg-hover); }

.lg-caps {
  display: block;
  margin-top: 5px;
  font-size: var(--fs-sm);
  color: var(--warning);
}

/* ===== 按钮 ===== */
.lg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 42px;
  padding: 0 16px;
  font-family: inherit;
  font-size: var(--fs-base);
  font-weight: 600;
  border-radius: var(--radius);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out),
              box-shadow var(--dur-fast) var(--ease-out),
              transform var(--dur-fast) var(--ease-out);
}
.lg-btn-primary {
  width: 100%;
  margin-top: 5px;
  color: var(--on-accent);
  background: var(--accent-fill);
}
.lg-btn-primary:hover:not(:disabled) {
  background: var(--accent-strong);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.lg-btn-primary:active:not(:disabled) { transform: none; }
.lg-btn-primary:disabled { opacity: 0.55; cursor: not-allowed; }
.lg-btn-ghost {
  width: 100%;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border-color: var(--border);
}
.lg-btn-ghost:hover:not(:disabled) { background: var(--bg-hover); }
.lg-btn-ghost:disabled { opacity: 0.6; cursor: not-allowed; }

.lg-spin {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: lg-spin 0.7s linear infinite;
}
@keyframes lg-spin { to { transform: rotate(360deg); } }

/* ===== 底部 ===== */
.lg-foot {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
  text-align: center;
}
.lg-foot-text { font-size: var(--fs-sm); color: var(--text-muted); }
.lg-link {
  margin-left: 5px;
  padding: 2px 4px;
  font-family: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--accent-fill);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.lg-link:hover { text-decoration: underline; }

.lg-note {
  margin: 14px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-faint);
  line-height: 1.6;
  text-align: center;
}

.lg-blocker { display: flex; flex-direction: column; gap: 4px; }

/* 窄屏：卡片贴边一点，别浪费横向空间 */
@media (max-width: 460px) {
  .lg-view { padding: 18px 12px 28px; }
  .lg-card { padding: 22px 18px 18px; }
}

/*
 * 矮窗口（笔记本分屏、浏览器非最大化时很常见）：
 * 压缩纵向留白，让初始化表单（字段最多的一种形态）尽量一屏放下，
 * 不用为了点「创建管理员账号」先滚一下。
 */
@media (max-height: 720px) {
  .lg-view { padding: 16px 20px 22px; }
  .lg-card { padding: 18px 20px 16px; }
  .lg-brand { margin-bottom: 14px; }
  .lg-mark { width: 38px; height: 38px; }
  .lg-mark svg { width: 26px; height: 26px; }
  .lg-title { font-size: var(--fs-lg); }
  .lg-form { gap: 10px; }
  .lg-alert { padding: 9px 11px; margin-bottom: 11px; }
  .lg-input { height: 36px; }
  .lg-btn { height: 38px; }
  .lg-foot { margin-top: 12px; padding-top: 11px; }
  .lg-note { margin-top: 10px; }
}

/* 尊重「减少动态效果」的系统设置：不做位移与动画 */
@media (prefers-reduced-motion: reduce) {
  .lg-card { animation: none; opacity: 1; transform: none; }
  .lg-btn-primary:hover:not(:disabled) { transform: none; }
  .lg-spin { animation-duration: 1.4s; }
}
</style>
