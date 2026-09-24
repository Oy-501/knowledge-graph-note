<template>
  <div v-if="hasError" class="error-boundary">
    <div class="error-boundary-card">
      <div class="error-boundary-icon">⚠️</div>
      <h3>该模块暂时不可用</h3>
      <p class="error-boundary-msg">{{ errorMessage }}</p>
      <p class="error-boundary-hint">{{ countdown > 0 ? `${countdown} 秒后自动恢复...` : '正在恢复...' }}</p>
      <div class="error-boundary-actions">
        <button type="button" class="btn" @click="retry">立即重试</button>
        <button type="button" class="btn btn-sm" @click="showDetail = !showDetail">{{ showDetail ? '收起详情' : '查看详情' }}</button>
      </div>
      <div v-if="showDetail" class="error-boundary-detail"><pre>{{ errorStack }}</pre></div>
    </div>
  </div>
  <slot v-else />
</template>

<script setup>
import { ref, onMounted, onUnmounted, onErrorCaptured } from 'vue'
import { logError } from '@/utils/resilience'

const props = defineProps({ name: { type: String, default: '未知组件' }, autoRetry: { type: Boolean, default: true }, retryDelay: { type: Number, default: 3000 } })
const hasError = ref(false)
const errorMessage = ref('')
const errorStack = ref('')
const showDetail = ref(false)
const countdown = ref(0)
let _timer = null
let _countdownTimer = null

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorMessage.value = err?.message || '组件发生未知错误'
  errorStack.value = err?.stack || ''
  logError(`ErrorBoundary:${props.name}`, info, err)
  if (props.autoRetry) startAutoRetry()
  return false
})

function startAutoRetry() {
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
  countdown.value = Math.ceil(props.retryDelay / 1000)
  _countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) { clearInterval(_countdownTimer); retry() }
  }, 1000)
  _timer = setTimeout(() => retry(), props.retryDelay)
}

function retry() {
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
  hasError.value = false
  errorMessage.value = ''
  errorStack.value = ''
  countdown.value = 0
}

onMounted(() => {})
onUnmounted(() => { clearTimeout(_timer); clearInterval(_countdownTimer) })
</script>

<style scoped>
.error-boundary { display: flex; align-items: center; justify-content: center; min-height: 120px; padding: 16px; }
.error-boundary-card { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 20px; text-align: center; max-width: 400px; }
.error-boundary-icon { font-size: 32px; margin-bottom: 8px; }
.error-boundary-card h3 { margin: 0 0 6px; font-size: 14px; color: var(--text-primary); }
.error-boundary-msg { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; word-break: break-all; }
.error-boundary-hint { font-size: 11px; color: var(--text-muted); margin-bottom: 10px; }
.error-boundary-actions { display: flex; gap: 8px; justify-content: center; }
.error-boundary-detail { margin-top: 10px; text-align: left; background: var(--bg-tertiary); border-radius: 4px; padding: 8px; max-height: 150px; overflow: auto; }
.error-boundary-detail pre { margin: 0; font-size: 10px; color: var(--text-muted); white-space: pre-wrap; word-break: break-all; }
</style>
