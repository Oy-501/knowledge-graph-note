<template>
  <div class="kt">
    <div v-if="events.length === 0" class="kt-empty">
      暂无时间线数据，该知识点尚未记录时间轨迹
    </div>
    <div v-else class="kt-list">
      <div v-for="(ev, i) in events" :key="i" class="kt-event">
        <div class="kt-rail">
          <span class="kt-dot" :class="'kt-dot-' + ev.type"></span>
          <span v-if="i < events.length - 1" class="kt-line"></span>
        </div>
        <div class="kt-body">
          <div class="kt-head">
            <span class="kt-label">{{ ev.label }}</span>
            <span class="kt-time">{{ ev.timeText }}</span>
          </div>
          <div v-if="ev.desc" class="kt-desc">{{ ev.desc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { useGraphStore } from '@/store/graphStore'
import { endpointId } from '@/utils/graph'
import { formatDay } from '@/utils/format'

const props = defineProps({
  node: { type: Object, default: null }
})

const graphStore = useGraphStore()
const reviewRecords = useLocalStorage('kg-review-records', {})

const events = computed(() => {
  const node = props.node
  if (!node) return []
  const list = []

  // 1. 首次出现
  if (node.uploadTime) {
    list.push({ time: node.uploadTime, type: 'create', label: '首次出现', desc: '知识点首次进入知识图谱' })
  }

  // 2. 关联建立（相关连线，用对端节点 uploadTime 近似建立时间）
  for (const l of graphStore.links) {
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (s !== node.id && t !== node.id) continue
    const otherId = s === node.id ? t : s
    const other = graphStore.nodes.find(n => n.id === otherId)
    const time = other?.uploadTime || node.uploadTime || 0
    list.push({
      time,
      type: 'link',
      label: `${l.relation_label || '关联'}：${other ? other.title : otherId}`,
      desc: l.relation_evidence || l.evidence || ''
    })
  }

  // 3. 校验确认
  if (node.validate?.confirmedAt) {
    list.push({ time: node.validate.confirmedAt, type: 'validate', label: '校验确认', desc: '知识点校验通过' })
  }
  if (node.validate?.issues?.length) {
    list.push({
      time: node.validate.confirmedAt || node.uploadTime || 0,
      type: 'validate',
      label: `校验问题 ${node.validate.issues.length} 项`,
      desc: node.validate.issues.map(i => i.type || i.reason).slice(0, 3).join('、')
    })
  }

  // 4. 复习轨迹
  const rec = (reviewRecords.value || {})[node.id]
  if (rec?.lastReviewed) {
    list.push({
      time: rec.lastReviewed,
      type: 'review',
      label: `复习 ${rec.repetitions || 0} 次`,
      desc: `最近复习 · 间隔 ${rec.interval || 1} 天`
    })
  }

  // 按时间排序，附格式化的时间文本
  return list
    .sort((a, b) => a.time - b.time)
    .map(ev => ({ ...ev, timeText: formatDay(ev.time) }))
})
</script>

<style scoped>
.kt {
  padding: 4px 0;
}
.kt-empty {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  padding: 12px 0;
}
.kt-list {
  display: flex;
  flex-direction: column;
}
.kt-event {
  display: flex;
  gap: 10px;
}
.kt-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 14px;
}
.kt-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}
.kt-dot-create { background: var(--accent); }
.kt-dot-link { background: var(--mint); }
.kt-dot-validate { background: var(--warning); }
.kt-dot-review { background: var(--apricot, #D4A574); }
.kt-line {
  flex: 1;
  width: 1px;
  background: var(--border-light);
  margin: 3px 0;
}
.kt-body {
  flex: 1;
  min-width: 0;
  padding-bottom: 12px;
}
.kt-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.kt-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kt-time {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.kt-desc {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.5;
  word-break: break-all;
}
</style>
