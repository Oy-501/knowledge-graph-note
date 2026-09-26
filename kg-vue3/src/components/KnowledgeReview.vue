<template>
  <div class="kr">
    <!-- 空态 -->
    <div v-if="graphStore.nodes.length === 0" class="kr-empty">
      <p>暂无知识数据，上传文件后即可生成每日回顾</p>
    </div>

    <template v-else>
      <!-- 今日概览 -->
      <div class="kr-overview">
        <div class="kr-stat">
          <div class="kr-num">{{ todayNewCount }}</div>
          <div class="kr-label">今日新增</div>
        </div>
        <div class="kr-stat">
          <div class="kr-num">{{ pendingCount }}</div>
          <div class="kr-label">待处理校验</div>
        </div>
        <div class="kr-stat">
          <div class="kr-num">{{ dueReviewCount }}</div>
          <div class="kr-label">待复习</div>
        </div>
      </div>

      <!-- 推荐复习（间隔重复） -->
      <div class="kr-section" v-if="reviewQueue.length">
        <div class="kr-section-title">推荐复习</div>
        <div class="kr-item" v-for="r in reviewQueue" :key="r.id">
          <div class="kr-item-main">
            <span class="kr-item-name">{{ r.title }}</span>
            <span class="kr-item-meta">度 {{ r.degree }} · {{ r.intervalText }}</span>
          </div>
          <button type="button" class="kr-btn kr-btn-primary" @click="onReviewed(r.id)">已复习</button>
        </div>
      </div>
      <div v-else class="kr-section">
        <div class="kr-section-title">推荐复习</div>
        <div class="kr-empty-sm">暂无待复习知识点</div>
      </div>

      <!-- 最近新增 -->
      <div class="kr-section" v-if="recentNodes.length">
        <div class="kr-section-title">最近新增</div>
        <div class="kr-item" v-for="n in recentNodes" :key="n.id">
          <div class="kr-item-main">
            <span class="kr-item-name">{{ n.title }}</span>
            <span class="kr-item-meta">{{ n.timeText }}</span>
          </div>
        </div>
      </div>

      <!-- 待处理校验问题 -->
      <div class="kr-section" v-if="unverifiedNodes.length">
        <div class="kr-section-title">待处理校验问题</div>
        <div class="kr-item" v-for="n in unverifiedNodes" :key="n.id">
          <div class="kr-item-main">
            <span class="kr-item-name">{{ n.title }}</span>
            <span class="kr-item-meta">未校验/待确认</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useLocalStorage } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import { useGraphStore } from '@/store/graphStore'
import { endpointId } from '@/utils/graph'
import { formatDay } from '@/utils/format'

const graphStore = useGraphStore()

// 复习记录：{ [nodeId]: { lastReviewed, interval(天), repetitions } }
const reviewRecords = useLocalStorage('kg-review-records', {})

// 度数表（用于重要性排序）
const degreeMap = computed(() => {
  const map = new Map()
  for (const n of graphStore.nodes) map.set(n.id, 0)
  for (const l of graphStore.links) {
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    map.set(s, (map.get(s) || 0) + 1)
    map.set(t, (map.get(t) || 0) + 1)
  }
  return map
})

// 今日新增（uploadTime 在今天）
const todayNewCount = computed(() => {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  return graphStore.nodes.filter(n => (n.uploadTime || 0) >= start.getTime()).length
})

// 待处理校验（未校验/待确认/错误）
const unverifiedNodes = computed(() => {
  return graphStore.nodes.filter(n => {
    const s = n.validate?.status
    return s === 'pending' || s === 'error' || s === undefined || s === null
  })
})
const pendingCount = computed(() => unverifiedNodes.value.length)

// 间隔重复：到期或从未复习的节点，按度数降序
const INTERVALS = [1, 3, 7, 14, 30, 60]
const reviewQueue = computed(() => {
  const now = Date.now()
  const recs = reviewRecords.value || {}
  return graphStore.nodes
    .filter(n => n.validate?.status !== 'discarded')
    .map(n => {
      const rec = recs[n.id]
      const degree = degreeMap.value.get(n.id) || 0
      if (!rec) return { id: n.id, title: n.title, degree, due: true, intervalText: '未复习' }
      const intervalDays = rec.interval || 1
      const due = now - (rec.lastReviewed || 0) >= intervalDays * 86400000
      return { id: n.id, title: n.title, degree, due, intervalText: `${rec.repetitions || 0} 次 · ${intervalDays} 天` }
    })
    .filter(x => x.due)
    .sort((a, b) => b.degree - a.degree)
    .slice(0, 5)
})
const dueReviewCount = computed(() => {
  const now = Date.now()
  const recs = reviewRecords.value || {}
  return graphStore.nodes.filter(n => {
    if (n.validate?.status === 'discarded') return false
    const rec = recs[n.id]
    if (!rec) return true
    return now - (rec.lastReviewed || 0) >= (rec.interval || 1) * 86400000
  }).length
})

function onReviewed(nodeId) {
  const recs = { ...(reviewRecords.value || {}) }
  const prev = recs[nodeId] || { lastReviewed: 0, interval: 1, repetitions: 0 }
  const repetitions = prev.repetitions + 1
  const interval = INTERVALS[Math.min(repetitions, INTERVALS.length - 1)]
  recs[nodeId] = { lastReviewed: Date.now(), interval, repetitions }
  reviewRecords.value = recs
  ElMessage.success('已记录复习，下次提醒间隔 ' + interval + ' 天')
}

// 最近新增（uploadTime 降序 top 5）
const recentNodes = computed(() => {
  return graphStore.nodes
    .filter(n => n.uploadTime)
    .sort((a, b) => (b.uploadTime || 0) - (a.uploadTime || 0))
    .slice(0, 5)
    .map(n => ({ id: n.id, title: n.title, timeText: formatDay(n.uploadTime) }))
})
</script>

<style scoped>
.kr {
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kr-empty {
  padding: 20px 12px;
  text-align: center;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}

/* 今日概览：3 列统计 */
.kr-overview {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}
.kr-stat {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 10px 8px;
  text-align: center;
}
.kr-num {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--accent);
  line-height: 1.2;
}
.kr-label {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-top: 3px;
}

/* 分区 */
.kr-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kr-section-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}
.kr-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}
.kr-item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.kr-item-name {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kr-item-meta {
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.kr-btn {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.kr-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.kr-btn-primary {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: var(--accent);
}
.kr-btn-primary:hover {
  background: var(--accent-strong);
  color: #fff;
}
.kr-empty-sm {
  padding: 10px;
  text-align: center;
  color: var(--text-muted);
  font-size: var(--fs-xs);
}
</style>
