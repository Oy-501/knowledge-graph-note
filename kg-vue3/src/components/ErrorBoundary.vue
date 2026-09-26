<template>
  <!-- 兜底 UI：局部崩溃只影响这一块，用户仍有可走的路径 -->
  <div v-if="hasError" class="error-boundary">
    <div class="error-boundary-card">
      <div class="error-boundary-icon">⚠️</div>
      <h3>{{ name }} 暂时不可用</h3>
      <p class="error-boundary-msg">{{ errorMessage }}</p>
      <p class="error-boundary-hint">{{ hintText }}</p>
      <div class="error-boundary-actions">
        <button type="button" class="btn" @click="retry">立即重试</button>
        <button type="button" class="btn btn-sm" @click="$emit('recover')">
          回到知识图谱
        </button>
        <button type="button" class="btn btn-sm" @click="showDetail = !showDetail">
          {{ showDetail ? '收起详情' : '查看详情' }}
        </button>
      </div>
      <div v-if="showDetail" class="error-boundary-detail">
        <div class="eb-detail-head">
          已自动上报后端，可在「后台管理 → 操作审计」按来源 frontend 查看
        </div>
        <pre>{{ errorStack || errorMessage }}</pre>
      </div>
    </div>
  </div>
  <slot v-else />
</template>

<script setup>
/**
 * ErrorBoundary —— 局部错误边界
 *
 * 用 onErrorCaptured 拦住子组件树的异常，把「整个应用白屏」降级为
 * 「只有一个面板不可用」，并保留重试与退回入口。
 *
 * 关键约束（此前版本缺的一道防线）：
 *   自动重试必须有**次数上限**。若故障是持续性的（例如接口 500），
 *   无上限的定时重试会变成每 3 秒一次的错误震荡：用户看到界面反复闪，
 *   后端被反复打，日志被刷满。超过上限后改为纯手动重试。
 */
import { ref, computed, onMounted, onUnmounted, onErrorCaptured } from 'vue'
import { logError } from '@/utils/resilience'

const props = defineProps({
  name: { type: String, default: '该模块' },
  autoRetry: { type: Boolean, default: true },
  retryDelay: { type: Number, default: 3000 },
  maxAutoRetries: { type: Number, default: 2 }
})
defineEmits(['recover'])

const hasError = ref(false)
const errorMessage = ref('')
const errorStack = ref('')
const showDetail = ref(false)
const countdown = ref(0)
const autoRetryCount = ref(0)

let _timer = null
let _countdownTimer = null

const canAutoRetry = computed(
  () => props.autoRetry && autoRetryCount.value < props.maxAutoRetries
)

const hintText = computed(() => {
  if (canAutoRetry.value && countdown.value > 0) {
    return `${countdown.value} 秒后自动恢复（第 ${autoRetryCount.value + 1}/${props.maxAutoRetries} 次）…`
  }
  if (props.autoRetry && !canAutoRetry.value) {
    return '自动重试已达上限，为免界面反复刷新已暂停；请手动重试或先处理上方原因。'
  }
  return '请手动重试。'
})

onErrorCaptured((err, instance, info) => {
  hasError.value = true
  errorMessage.value = err?.message || '组件发生未知错误'
  errorStack.value = err?.stack || ''
  logError(`ErrorBoundary:${props.name}`, info, err)

  if (canAutoRetry.value) {
    startAutoRetry()
  }
  return false // 阻止错误继续向上传播，保护应用的其余部分
})

function startAutoRetry() {
  // 先清旧的定时器再重新武装，避免错误反复发生时旧 interval 泄漏、retry 重复触发
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
  autoRetryCount.value += 1
  countdown.value = Math.ceil(props.retryDelay / 1000)
  _countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      clearInterval(_countdownTimer)
      retry()
    }
  }, 1000)
  _timer = setTimeout(() => retry(), props.retryDelay)
}

/** 手动重试会重置自动重试额度，让用户可以再试一轮 */
function retry() {
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
  if (autoRetryCount.value >= props.maxAutoRetries) {
    autoRetryCount.value = 0
  }
  hasError.value = false
  errorMessage.value = ''
  errorStack.value = ''
  countdown.value = 0
}

defineExpose({ retry })

onMounted(() => {
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
})

onUnmounted(() => {
  clearTimeout(_timer)
  clearInterval(_countdownTimer)
})
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  height: 100%;
  padding: 16px;
}
.error-boundary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: 20px;
  text-align: center;
  max-width: 420px;
}
.error-boundary-icon { font-size: 32px; margin-bottom: 8px; }
.error-boundary-card h3 {
  margin: 0 0 6px;
  font-size: var(--fs-base);
  color: var(--text-primary);
}
.error-boundary-msg {
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  margin-bottom: 4px;
  word-break: break-word;
}
.error-boundary-hint {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-bottom: 10px;
  line-height: 1.6;
}
.error-boundary-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}
.error-boundary-detail {
  margin-top: 10px;
  text-align: left;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  padding: 8px;
  max-height: 180px;
  overflow: auto;
}
.eb-detail-head {
  font-size: var(--fs-xs);
  color: var(--accent);
  margin-bottom: 6px;
}
.error-boundary-detail pre {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
