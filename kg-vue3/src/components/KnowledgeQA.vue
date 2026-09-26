<template>
  <div class="kqa">
    <!-- 输入区 -->
    <div class="kqa-input-row">
      <input
        v-model="question"
        class="kqa-input"
        placeholder="如：JVM 和 GC 有什么关系？"
        @keyup.enter="onAsk"
      />
      <button type="button" class="kqa-btn kqa-btn-primary" @click="onAsk">提问</button>
    </div>

    <!-- 示例问题 -->
    <div class="kqa-examples">
      <span class="kqa-examples-label">试试：</span>
      <button type="button"
        v-for="ex in examples"
        :key="ex"
        class="kqa-chip"
        @click="question = ex; onAsk()"
      >{{ ex }}</button>
    </div>

    <!-- 空态 -->
    <div v-if="!result && !loading" class="kqa-empty">
      <p>输入问题，系统将基于你的知识图谱回答</p>
      <p class="kqa-empty-sub">支持「X 和 Y 有什么关系」「我学过哪些关于 X 的知识」</p>
    </div>

    <!-- 回答区 -->
    <div v-if="result" class="kqa-result">
      <!-- 关系类 -->
      <template v-if="result.type === 'relation'">
        <div class="kqa-summary">{{ pathDesc.summary }}</div>
        <div v-if="pathDesc.hops.length" class="kqa-path">
          <div v-for="(hop, i) in pathDesc.hops" :key="i" class="kqa-hop">
            <div class="kqa-hop-node">{{ hop.from }}</div>
            <div class="kqa-hop-mid">
              <span class="kqa-hop-label" :style="{ color: relColor(hop.type) }">
                — {{ hop.label }} →
              </span>
              <span class="kqa-hop-score">{{ (hop.score * 100).toFixed(0) }}%</span>
            </div>
            <div class="kqa-hop-node kqa-hop-last">{{ hop.to }}</div>
          </div>
        </div>
        <div v-if="pathDesc.hops.length" class="kqa-evidence-list">
          <div class="kqa-evidence-title">证据原文</div>
          <div v-for="(hop, i) in pathDesc.hops.filter(h => h.evidence)" :key="'e' + i" class="kqa-evidence">
            <span class="kqa-evidence-rel">{{ hop.from }} → {{ hop.to }}：</span>{{ hop.evidence }}
          </div>
        </div>
      </template>

      <!-- 主题类 -->
      <template v-else-if="result.type === 'topic'">
        <div class="kqa-summary" v-if="result.related.length">
          找到 {{ result.related.length }} 个与「{{ result.query }}」相关的知识点
        </div>
        <div class="kqa-summary" v-else>未找到与「{{ result.query }}」相关的知识点</div>
        <div v-if="result.related.length" class="kqa-topic-list">
          <div v-for="r in result.related" :key="r.node.id" class="kqa-topic-item">
            <div class="kqa-topic-head">
              <span class="kqa-topic-name">{{ r.node.title }}</span>
              <span class="kqa-topic-badge">L{{ r.node.level || 3 }} · 度 {{ r.degree }}</span>
            </div>
            <div v-if="r.node.description" class="kqa-topic-desc">{{ r.node.description.slice(0, 90) }}</div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { RELATION_COLORS } from '@/utils/palette'
import { useGraphStore } from '@/store/graphStore'
import { answer, describePath } from '@/utils/qa'
import { endpointId } from '@/utils/graph'

const graphStore = useGraphStore()

const question = ref('')
const result = ref(null)
const loading = ref(false)

const examples = computed(() => {
  // 从图谱里挑两个度最高的节点作为示例，找不到就用占位
  const nodes = graphStore.nodes.filter(n => n.validate?.status !== 'discarded')
  const top = [...nodes].sort((a, b) => degree(b) - degree(a)).slice(0, 3).map(n => n.title)
  if (top.length >= 2) {
    return [`${top[0]} 和 ${top[1]} 有什么关系？`, `我学过哪些关于 ${top[0]} 的知识？`]
  }
  return ['JVM 和 GC 有什么关系？', '我学过哪些关于并发的知识？']
})

function degree(n) {
  let d = 0
  for (const l of graphStore.links) {
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (s === n.id) d++
    if (t === n.id) d++
  }
  return d
}

function onAsk() {
  if (!question.value.trim()) return
  loading.value = true
  result.value = answer(question.value, graphStore.nodes, graphStore.links)
  loading.value = false
}

const pathDesc = computed(() => {
  if (!result.value || result.value.type !== 'relation') return { summary: '', hops: [] }
  return describePath(result.value.a, result.value.b, result.value.path, graphStore.nodes)
})

function relColor(type) {
  // 关系配色统一来自 utils/palette.js 的 RELATION_COLORS
  return RELATION_COLORS[type] || RELATION_COLORS.default
}
</script>

<style scoped>
.kqa {
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.kqa-input-row {
  display: flex;
  gap: 8px;
}
.kqa-input {
  flex: 1;
  min-width: 0;
  padding: 7px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--text-primary);
  font-size: var(--fs-sm);
  outline: none;
  transition: border-color var(--dur-fast);
}
.kqa-input:focus {
  border-color: var(--accent);
}
.kqa-btn {
  flex-shrink: 0;
  padding: 7px 14px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-light);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.kqa-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.kqa-btn-primary {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: var(--accent);
}
.kqa-btn-primary:hover {
  background: var(--accent-strong);
  color: #fff;
}

.kqa-examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.kqa-examples-label {
  font-size: var(--fs-xs);
  color: var(--text-muted);
}
.kqa-chip {
  font-size: var(--fs-xs);
  padding: 3px 9px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--dur-fast);
}
.kqa-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.kqa-empty {
  text-align: center;
  padding: 20px 12px;
  color: var(--text-muted);
  font-size: var(--fs-sm);
}
.kqa-empty-sub {
  font-size: var(--fs-xs);
  margin-top: 4px;
  opacity: 0.75;
}

.kqa-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kqa-summary {
  font-size: var(--fs-sm);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 9px 12px;
  line-height: 1.6;
}
.kqa-path {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kqa-hop {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.kqa-hop-node {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--accent-strong);
  background: var(--accent-soft);
  padding: 3px 10px;
  border-radius: var(--radius-full);
}
.kqa-hop-last {
  color: var(--apricot-strong, var(--warning));
  background: var(--apricot-soft, rgba(212, 165, 116, 0.15));
}
.kqa-hop-mid {
  display: flex;
  align-items: center;
  gap: 4px;
}
.kqa-hop-label {
  font-size: var(--fs-xs);
  font-weight: 500;
}
.kqa-hop-score {
  font-size: var(--fs-xs);
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.kqa-evidence-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 2px;
}
.kqa-evidence-title {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-secondary);
}
.kqa-evidence {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-left: 2px solid var(--accent);
  padding: 6px 9px;
  border-radius: var(--radius-sm);
  line-height: 1.5;
}
.kqa-evidence-rel {
  color: var(--accent-strong);
  font-weight: 500;
}

.kqa-topic-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kqa-topic-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 8px 11px;
}
.kqa-topic-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.kqa-topic-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kqa-topic-badge {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.kqa-topic-desc {
  margin-top: 4px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
