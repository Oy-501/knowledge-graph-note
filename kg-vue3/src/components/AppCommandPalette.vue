<!--
  命令面板（⌘K / Ctrl+K）
  ------------------------------------------------------------
  只做一件事：把「去哪个视图」和「几个常用动作」收进一个可搜索的浮层，
  从而让顶栏不必再摆 8 个页签。分组只是标签，排序按输入过滤后的原顺序。
-->
<template>
  <Transition name="palette-fade">
    <div v-if="visible" class="cmd-overlay" @click.self="$emit('close')">
      <div class="cmd-panel" role="dialog" aria-label="命令面板" aria-modal="true">
        <input
          ref="inputRef"
          v-model="keyword"
          class="cmd-input"
          type="text"
          placeholder="搜索节点 / 文件 / 操作…"
          spellcheck="false"
          @keydown.down.prevent="move(1)"
          @keydown.up.prevent="move(-1)"
          @keydown.enter.prevent="runAt(cursor)"
          @keydown.esc.prevent="$emit('close')"
        />

        <div class="cmd-list">
          <button
            v-for="(item, i) in filtered"
            :key="item.id"
            type="button"
            class="cmd-item"
            :class="{ 'is-active': i === cursor }"
            @click="runAt(i)"
            @mouseenter="cursor = i"
          >
            <span class="cmd-group">{{ item.group }}</span>
            <span class="cmd-label">{{ item.label }}</span>
            <kbd v-if="item.hint" class="cmd-hint">{{ item.hint }}</kbd>
          </button>

          <p v-if="!filtered.length" class="cmd-empty">没有匹配项</p>
        </div>

        <div class="cmd-foot">
          <span>↑↓ 选择</span><span>回车执行</span><span>Esc 关闭</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  /** [{ id, group, label, hint?, type, payload? }] */
  items: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'run'])

const keyword = ref('')
const cursor = ref(0)
const inputRef = ref(null)

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return props.items
  return props.items.filter(it =>
    it.label.toLowerCase().includes(k) || (it.group || '').toLowerCase().includes(k))
})

watch(() => props.visible, async v => {
  if (!v) return
  keyword.value = ''
  cursor.value = 0
  await nextTick()
  inputRef.value?.focus()
})

watch(filtered, () => { cursor.value = 0 })

function move(step) {
  const n = filtered.value.length
  if (!n) return
  cursor.value = (cursor.value + step + n) % n
}

function runAt(i) {
  const item = filtered.value[i]
  if (!item) return
  emit('run', item)
}
</script>

<style scoped>
.cmd-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 14vh;
  background: rgba(6, 10, 18, 0.28);
}
.cmd-panel {
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: 60vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.cmd-input {
  width: 100%;
  height: 44px;
  padding: 0 16px;
  border: 0;
  border-bottom: 1px solid var(--border-light);
  background: transparent;
  color: var(--text-primary);
  font-size: var(--fs-base);
  outline: none;
}
.cmd-input::placeholder { color: var(--text-faint); }

.cmd-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}
.cmd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-primary);
  font-size: var(--fs-md);
  text-align: left;
  cursor: pointer;
}
.cmd-item.is-active {
  background: var(--bg-hover);
  border-color: var(--border);
}
.cmd-group {
  flex: none;
  min-width: 34px;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.cmd-label { flex: 1; }
.cmd-hint {
  flex: none;
  font-size: var(--fs-xs);
  color: var(--text-faint);
  font-family: var(--font-mono);
}
.cmd-empty {
  margin: 0;
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: var(--fs-md);
}
.cmd-foot {
  display: flex;
  gap: 14px;
  padding: 7px 14px;
  border-top: 1px solid var(--border-light);
  font-size: var(--fs-xs);
  color: var(--text-faint);
}
.palette-fade-enter-active,
.palette-fade-leave-active { transition: opacity 0.14s var(--ease-out); }
.palette-fade-enter-from,
.palette-fade-leave-to { opacity: 0; }
</style>
