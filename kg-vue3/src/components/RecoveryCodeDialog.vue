<!--
  一次性恢复码弹窗
  ------------------------------------------------------------
  注册 / 首次初始化 / 重置密码成功后，后端会返回一枚恢复码 ——
  它是「忘记密码」时唯一的自助出口，**库里只有哈希，这是唯一一次显示**。

  所以这个弹窗刻意不可跳过：
    · 没有右上角关闭按钮、点遮罩不关闭 —— 顺手点掉就永久丢失；
    · 必须点「我已保存」才消失，且按钮文案明确告诉用户后果。
  复制按钮走 navigator.clipboard，失败时降级为「选中文本」，
  本地 http 下 clipboard 可能不可用（非安全上下文），不能让用户卡住。
-->
<template>
  <el-dialog
    :model-value="!!auth.pendingRecovery"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    width="460px"
    align-center
    class="rc-dialog"
    append-to-body
  >
    <div class="rc">
      <div class="rc-head">
        <span class="rc-seal" aria-hidden="true">谱</span>
        <div>
          <h3 class="rc-title">{{ title }}</h3>
          <p class="rc-sub">请把这串恢复码保存到安全的地方</p>
        </div>
      </div>

      <div class="rc-code" ref="codeRef" @click="selectAll">{{ code }}</div>

      <div class="rc-actions">
        <button type="button" class="rc-btn rc-btn-ghost" @click="copy">
          {{ copied ? '已复制' : '复制恢复码' }}
        </button>
        <button type="button" class="rc-btn rc-btn-primary" @click="confirm">
          我已保存
        </button>
      </div>

      <p class="rc-warn">
        关闭后无法再次查看。忘记密码时，在登录页点「忘记密码」，
        用<strong>用户名 + 这串恢复码</strong>重设密码。
      </p>
    </div>
  </el-dialog>
</template>

<script setup>
/**
 * RecoveryCodeDialog.vue
 * 展示一次性恢复码。数据来自 authStore.pendingRecovery（{code, reason}）。
 */
import { computed, ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/store/authStore'

const auth = useAuthStore()
const codeRef = ref(null)
const copied = ref(false)

const code = computed(() => auth.pendingRecovery?.code || '')

const title = computed(() => {
  const reason = auth.pendingRecovery?.reason
  if (reason === 'bootstrap') return '系统已初始化'
  if (reason === 'register') return '账号已创建'
  if (reason === 'reset') return '密码已重置'
  if (reason === 'admin_create') return '账号已创建'
  if (reason === 'admin_reset') return '密码已重置'
  return '恢复码'
})

async function copy() {
  const text = code.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    ElMessage.success('恢复码已复制')
  } catch (e) {
    // 非安全上下文（http + 非 localhost）下 clipboard 不可用：
    // 降级为选中文本，用户按 Ctrl+C 即可，不要在这里报一个他无法处理的错误
    await nextTick()
    selectAll()
    ElMessage.warning('浏览器不允许自动复制，已为你选中文本，请按 Ctrl+C')
  }
}

function selectAll() {
  const el = codeRef.value
  if (!el) return
  const range = document.createRange()
  range.selectNodeContents(el)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

function confirm() {
  auth.dismissRecovery()
  copied.value = false
}
</script>

<style scoped>
.rc { padding: 2px 2px 0; }
.rc-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}
/* 印章：与导航、登录页同一枚，继续强化「同一个产品」的连续性 */
.rc-seal {
  flex: none;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  background: var(--seal);
  color: var(--seal-ink);
  font-family: var(--font-display);
  font-weight: 900;
  font-size: 20px;
  line-height: 1;
  border-radius: 2px;
  transform: rotate(-3deg);
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.35);
}
.rc-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-primary);
}
.rc-sub {
  margin: 2px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-muted);
}

/* 恢复码本体：等宽 + 字距，方便逐段核对；点击即全选 */
.rc-code {
  font-family: var(--font-mono);
  font-size: var(--fs-xl);
  font-weight: 700;
  letter-spacing: 0.14em;
  text-align: center;
  padding: 18px 12px;
  margin-bottom: 16px;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  cursor: text;
  user-select: all;
  word-break: break-all;
}

.rc-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.rc-btn {
  height: 40px;
  border-radius: var(--radius);
  font-size: var(--fs-md);
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--dur-fast) var(--ease-out),
              border-color var(--dur-fast) var(--ease-out);
}
.rc-btn-ghost {
  background: var(--bg-tertiary);
  border-color: var(--border);
  color: var(--text-primary);
}
.rc-btn-ghost:hover { background: var(--bg-hover); }
.rc-btn-primary {
  background: var(--accent-fill);
  color: var(--on-accent);
}
.rc-btn-primary:hover { background: var(--accent-strong); }

.rc-warn {
  margin: 14px 0 0;
  font-size: var(--fs-sm);
  line-height: 1.7;
  color: var(--text-muted);
}
.rc-warn strong { color: var(--text-secondary); }
</style>
