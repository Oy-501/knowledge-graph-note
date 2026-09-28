/**
 * authStore.js
 * 登录状态：会话令牌、当前用户、初始化/注册开关。
 *
 * 为什么要有这一层（而不是继续用管理口令）：
 * 旧做法是让用户在前端输入 backend/.env 里的 ADMIN_TOKEN。它有三个问题：
 *   ① 那个口令是**明文配置项**，输在前端等于把配置文件内容搬到浏览器里；
 *   ② 口令没有有效期、不能吊销、改一次要通知所有用的人；
 *   ③ 用户得先去翻 .env 才知道该输什么 —— 这是纯粹的摩擦。
 * 现在改成标准的「登录拿会话令牌」：口令只在登录那一刻传输，
 * 服务端存的是 bcrypt 哈希；会话可过期、可吊销、可滑动续期。
 *
 * 令牌存储：localStorage（与旧的 ADMIN_TOKEN 同一个思路）。
 * 这是**已知的取舍** —— 能挡住「别人打开你的浏览器」，挡不住
 * 「有人能读你的 localStorage」。要彻底解决需要 httpOnly Cookie + CSRF 防护，
 * 那是一次较大的改造，当前单机场景下不做。
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { authAPI, setSessionToken, onSessionExpired } from '@/api'

/** 会话令牌在 localStorage 里的键 */
export const SESSION_KEY = 'kg-session-token'

function readStoredToken() {
  try {
    return localStorage.getItem(SESSION_KEY) || ''
  } catch {
    return ''   // 隐私模式下可能读不到，当作未登录
  }
}

function writeStoredToken(v) {
  try {
    if (v) localStorage.setItem(SESSION_KEY, v)
    else localStorage.removeItem(SESSION_KEY)
  } catch { /* 存不了就只在内存里活着，本次会话仍然可用 */ }
}

export const useAuthStore = defineStore('auth', () => {
  // ---- state ----
  const token = ref(readStoredToken())
  const user = ref(null)
  /** 登录页要靠这些开关决定展示哪一种形态 */
  const needBootstrap = ref(false)
  const registrationOpen = ref(false)
  const sessionTtlDays = ref(7)
  /** 首次探测是否已完成 —— 未完成时不要渲染登录页，否则会先闪一下登录表单 */
  const ready = ref(false)
  const probing = ref(false)
  const busy = ref(false)
  /** 探测失败的原因（登录页据此提示「后端没启动」这类问题） */
  const probeError = ref('')

  // 内存里的令牌与 localStorage 保持同步，避免两处各写一遍
  setSessionToken(token.value)
  // 任意请求收到「会话失效」时自动清理本地状态（令牌被吊销 / 过期 / 被踢下线）
  onSessionExpired(() => { clearLocal() })

  // ---- getters ----
  const isAuthed = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => (user.value?.role || 'user') === 'admin')
  const displayName = computed(() => user.value?.display_name || user.value?.username || '')

  // ---- actions ----

  function setSession(newToken, newUser) {
    token.value = newToken || ''
    user.value = newUser || null
    writeStoredToken(token.value)
    setSessionToken(token.value)
  }

  /** 只清本地状态（不调后端）。会话失效回调会走这里 */
  function clearLocal() {
    token.value = ''
    user.value = null
    writeStoredToken('')
    setSessionToken('')
  }

  /**
   * 页面加载时探测一次：是否要初始化、是否开放注册、我是否还登录着。
   *
   * 刻意做成「一次请求拿到全部」——分两次请求会让登录页先按未登录渲染、
   * 再跳成已登录，用户能看见闪烁。
   */
  async function probe() {
    if (probing.value) return
    probing.value = true
    try {
      const data = await authAPI.status()
      needBootstrap.value = !!data.need_bootstrap
      registrationOpen.value = !!data.registration_open
      sessionTtlDays.value = data.session_ttl_days ?? 7
      if (data.authenticated && data.user) {
        user.value = data.user
      } else {
        // 本地有令牌但服务端不认（过期/被吊销/服务端重置）→ 清掉，别留着误导用户
        clearLocal()
      }
    } catch (e) {
      // 探测失败不能把用户卡在 loading：标记 ready，让登录页去显示错误
      probeError.value = e?.fullMessage || e?.message || '无法连接后端服务'
    } finally {
      probing.value = false
      ready.value = true
    }
  }

  async function bootstrap({ username, password, displayName = '' }) {
    const data = await authAPI.bootstrap({ username, password, displayName })
    // 初始化完成后本机不再是「未初始化」态 —— 立刻翻掉，
    // 否则登出后又会回到初始化表单，而它已经被后端 403 拒了
    needBootstrap.value = false
    setSession(data.token, data.user)
    return data
  }

  async function login({ username, password }) {
    const data = await authAPI.login({ username, password })
    setSession(data.token, data.user)
    return data
  }

  async function register({ username, password }) {
    const data = await authAPI.register({ username, password })
    setSession(data.token, data.user)
    return data
  }

  /** 登出：先尽力通知后端吊销，再清本地（后端失败也必须清，否则退不出去） */
  async function logout() {
    try {
      await authAPI.logout()
    } catch (e) {
      // 令牌可能已过期，后端返回 401 属于正常情况，不该拦住登出
      console.warn('[auth] 登出接口失败，仍然清理本地会话：', e?.message || e)
    } finally {
      clearLocal()
    }
  }

  /** 刷新当前用户信息（改角色/头像后同步用） */
  async function refreshMe() {
    if (!token.value) return null
    const data = await authAPI.me()
    user.value = data.user
    return data.user
  }

  async function changePassword({ oldPassword, newPassword }) {
    const data = await authAPI.changePassword({ oldPassword, newPassword })
    // 后端改密后会吊销全部会话（含当前这个），本地必须同步清掉
    clearLocal()
    return data
  }

  return {
    token, user, needBootstrap, registrationOpen, sessionTtlDays,
    ready, probing, busy, probeError,
    isAuthed, isAdmin, displayName,
    probe, setSession, clearLocal,
    bootstrap, login, register, logout, refreshMe, changePassword,
  }
})
