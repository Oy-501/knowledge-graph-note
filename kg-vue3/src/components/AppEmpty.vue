<template>
  <!--
    统一空态。
    为什么需要它：此前各处空态各写各的 —— 有的是 Element Plus 默认的灰色
    3D 方块插图（与全站暖色扁平风格明显冲突），有的是 emoji 🧠
    （跨平台渲染不一致，Windows 上还会退化成彩色表情符号）。
    统一成同一套：柔和的线性图标 + 主文案 + 可选说明 + 可选操作。
  -->
  <div class="app-empty" :class="{ 'is-compact': compact }">
    <div class="ae-art" aria-hidden="true">
      <svg viewBox="0 0 72 52" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- 三个节点与连线：呼应「知识图谱」的意象，而不是通用占位图 -->
        <path d="M20 22 L36 12 M20 22 L36 34 M36 12 L52 26"
              stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity="0.42" />
        <circle cx="20" cy="22" r="5.5" stroke="currentColor" stroke-width="1.4" fill="none" opacity="0.75" />
        <circle cx="36" cy="12" r="4" stroke="currentColor" stroke-width="1.4" fill="none" opacity="0.75" />
        <circle cx="36" cy="34" r="4" stroke="currentColor" stroke-width="1.4" fill="none" opacity="0.75" />
        <circle cx="52" cy="26" r="5.5" stroke="currentColor" stroke-width="1.4" fill="none" opacity="0.75" />
        <!-- 底部虚线底座，暗示「这里将来会有内容」 -->
        <path d="M8 46 H64" stroke="currentColor" stroke-width="1.2"
              stroke-linecap="round" stroke-dasharray="3 4" opacity="0.28" />
      </svg>
    </div>
    <div class="ae-text">{{ text }}</div>
    <div v-if="hint" class="ae-hint">{{ hint }}</div>
    <div v-if="$slots.action" class="ae-action"><slot name="action" /></div>
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, required: true },
  hint: { type: String, default: '' },
  compact: { type: Boolean, default: false }
})
</script>

<style scoped>
.app-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 28px 20px;
  color: var(--accent);
}
.app-empty.is-compact { padding: 16px 12px; }

.ae-art { color: var(--accent); opacity: 0.85; }
.ae-art svg { width: 72px; height: 52px; display: block; }
.is-compact .ae-art svg { width: 52px; height: 38px; }

.ae-text {
  margin-top: 10px;
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
}
.is-compact .ae-text { font-size: var(--fs-sm); margin-top: 6px; }

.ae-hint {
  margin-top: 5px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  line-height: 1.65;
  max-width: 34em;
}

.ae-action { margin-top: 12px; }
</style>
