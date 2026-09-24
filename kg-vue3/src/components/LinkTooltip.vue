<template>
  <div
    v-if="visible"
    class="link-tooltip"
    :style="{ left: x + 'px', top: y + 'px' }"
  >
    <h4>🔗 关联溯源</h4>

    <!-- 证据强度 -->
    <div class="lt-evidence" v-if="data.evidence_level">
      <span class="lt-evi-icon">{{ data.evidence_icon || '🔴' }}</span>
      <span class="lt-evi-label" :style="{ color: data.evidence_color || '#f87086' }">
        证据强度：{{ data.evidence_label || '无证据' }}
      </span>
    </div>

    <!-- 关系类型 -->
    <div class="lt-relation" v-if="data.relation_type">
      <span class="lt-rel-badge" :style="{ background: data.relation_color || '#8a93b0' }">
        {{ data.relation_icon || '~' }} {{ data.relation_label || '关联' }}
      </span>
      <span class="lt-rel-code" v-if="data.relation_type">({{ data.relation_type }})</span>
    </div>

    <div class="lt-row">
      <span class="lt-k">关联总得分</span>
      <span class="lt-v" :style="{ color: scoreColor }">{{ (data.score * 100).toFixed(1) }}%</span>
    </div>
    <div class="lt-row">
      <span class="lt-k">来源类型</span>
      <span class="lt-v">{{ sourceTypeLabel }}</span>
    </div>

    <!-- 上下文信息 -->
    <div class="lt-section" v-if="data.context_type">
      <div class="lt-section-title">上下文信息</div>
      <div class="lt-row">
        <span class="lt-k">上下文类型</span>
        <span class="lt-v">{{ contextTypeLabel }}</span>
      </div>
      <div class="lt-row" v-if="source?.fileId && target?.fileId">
        <span class="lt-k">文件关系</span>
        <span class="lt-v">{{ source.fileId === target.fileId ? '同一文件' : '不同文件' }}</span>
      </div>
    </div>

    <!-- 知识层级 -->
    <div class="lt-section" v-if="sourceLevel || targetLevel">
      <div class="lt-section-title">知识层级</div>
      <div class="lt-row">
        <span class="lt-k">A: {{ source?.title?.slice(0, 16) || '?' }}</span>
        <span class="lt-v">{{ sourceLevelLabel }}</span>
      </div>
      <div class="lt-row">
        <span class="lt-k">B: {{ target?.title?.slice(0, 16) || '?' }}</span>
        <span class="lt-v">{{ targetLevelLabel }}</span>
      </div>
    </div>

    <!-- 判定依据原文 -->
    <div class="lt-section" v-if="data.relation_evidence">
      <div class="lt-section-title">判定依据原文</div>
      <div class="lt-source">{{ data.relation_evidence }}</div>
    </div>

    <div class="lt-section" v-else-if="data.evidence">
      <div class="lt-section-title">知识库桥接原文</div>
      <div class="lt-source">{{ data.evidence }}</div>
    </div>

    <!-- 四维权重明细 -->
    <div class="lt-section">
      <div class="lt-section-title">四项权重明细</div>
      <div class="lt-row">
        <span class="lt-k">α 关键词 Jaccard</span>
        <span class="lt-v">{{ (data.breakdown?.sim_text * 100).toFixed(1) }}%</span>
      </div>
      <div class="lt-row">
        <span class="lt-k">β 语义向量余弦</span>
        <span class="lt-v">{{ (data.breakdown?.sim_vector * 100).toFixed(1) }}%</span>
      </div>
      <div class="lt-row">
        <span class="lt-k">γ 知识库推理</span>
        <span class="lt-v">{{ (data.breakdown?.sim_corpus * 100).toFixed(1) }}%</span>
      </div>
      <div class="lt-row">
        <span class="lt-k">δ 拓扑邻居重叠</span>
        <span class="lt-v">{{ (data.breakdown?.sim_topology * 100).toFixed(1) }}%</span>
      </div>
    </div>

    <!-- 重合关键词 -->
    <div class="lt-section" v-if="data.overlap_keywords && data.overlap_keywords.length">
      <div class="lt-section-title">重合关键词</div>
      <div class="lt-badges">
        <span class="lt-badge" v-for="k in data.overlap_keywords.slice(0, 8)" :key="k">#{{ k }}</span>
      </div>
    </div>

    <!-- 重合实体 -->
    <div class="lt-section" v-if="data.overlap_entities && data.overlap_entities.length">
      <div class="lt-section-title">重合实体</div>
      <div class="lt-badges">
        <span class="lt-badge" v-for="e in data.overlap_entities.slice(0, 8)" :key="e" style="color:var(--warning)">{{ e }}</span>
      </div>
    </div>

    <!-- 双向节点上下文 -->
    <div class="lt-section" v-if="source && target">
      <div class="lt-section-title">双向知识点</div>
      <div class="lt-source">A · {{ source.title || source.description?.slice(0, 40) }}</div>
      <div class="lt-source" style="border-left-color:var(--warning)">B · {{ target.title || target.description?.slice(0, 40) }}</div>
    </div>

    <!-- 判定方法 -->
    <div class="lt-section" v-if="data.relation_method">
      <div class="lt-section-title">判定方法</div>
      <div class="lt-source" style="border-left-color:var(--text-muted); font-size:10px">{{ data.relation_method }}</div>
    </div>

    <!-- 桥接类型说明 -->
    <div class="lt-section" v-if="data.bridge_type">
      <div class="lt-section-title">桥接类型</div>
      <div class="lt-source" style="border-left-color:var(--text-muted); font-size:10px">{{ bridgeTypeLabel }}</div>
    </div>

    <!-- 语义桥接说明 -->
    <div class="lt-section" v-if="data.semantic_bridge">
      <div class="lt-section-title">机制说明</div>
      <div class="lt-source" style="border-left-color:var(--text-muted)">{{ data.relation_evidence || data.evidence || '孤儿节点自动收养桥接' }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getLevelInfo } from '@/utils/mdParser'

const props = defineProps({
  visible: { type: Boolean, default: false },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  data: { type: Object, default: () => ({}) },
  source: { type: Object, default: null },
  target: { type: Object, default: null }
})

const scoreColor = computed(() => {
  const s = props.data?.score || 0
  if (s >= 0.6) return '#6dd48a'
  if (s >= 0.3) return '#f5b462'
  return '#f87086'
})

const sourceTypeLabel = computed(() => {
  const t = props.data?.source_type
  if (t === 'semantic_strong') return '语义强关联（文本0但向量>0.7）'
  if (t === 'cross_temporal') return '跨时序语义桥接'
  if (t === 'corpus_bridge') return '用户文档+系统知识库桥接'
  if (t === 'semantic_bridge') return '系统孤儿收养桥接'
  return '用户文档互关联'
})

const sourceLevel = computed(() => props.source?.level || props.data?.source_level)
const targetLevel = computed(() => props.target?.level || props.data?.target_level)
const sourceLevelLabel = computed(() => {
  if (!sourceLevel.value) return '未知'
  const info = getLevelInfo(sourceLevel.value)
  return info ? `L${sourceLevel.value}: ${info.label}` : `L${sourceLevel.value}`
})
const targetLevelLabel = computed(() => {
  if (!targetLevel.value) return '未知'
  const info = getLevelInfo(targetLevel.value)
  return info ? `L${targetLevel.value}: ${info.label}` : `L${targetLevel.value}`
})

const bridgeTypeLabel = computed(() => {
  const t = props.data?.bridge_type
  const map = {
    same_level: '同层级桥接（相似知识点关联）',
    upper_level: '上层理论支撑（理论基础关联）',
    lower_level: '下层实现示例（实现关系关联）',
    fallback: '跨层级兜底桥接'
  }
  return map[t] || t || '未知'
})

const contextTypeLabel = computed(() => {
  const t = props.data?.context_type
  const map = {
    same_file: '同一文件内（强关联）',
    same_group_bridged: '同分组 + 知识库桥接',
    same_group_no_bridge: '同分组（无桥接）',
    same_period: '同时期内（≤7天）',
    cross_window: '跨窗口（禁止关联）',
    unknown: '未知上下文'
  }
  return map[t] || t || '未知'
})
</script>

<style scoped>
.link-tooltip {
  position: fixed;
  z-index: 999;
  background: var(--bg-glass, var(--bg-primary));
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 14px;
  min-width: 260px;
  max-width: 380px;
  box-shadow: var(--shadow-card);
  pointer-events: none;
  font-size: 12px;
  line-height: 1.5;
}
.link-tooltip h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px 0;
  padding-left: 8px;
  border-left: 3px solid var(--accent);
  border-radius: 1px;
  color: var(--text-primary);
}
.lt-relation {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.lt-evidence {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
}
.lt-evi-icon {
  font-size: 12px;
}
.lt-evi-label {
  font-size: 12px;
  font-weight: 600;
}
.lt-rel-badge {
  font-size: 11px;
  color: #fff;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  font-weight: 500;
}
.lt-rel-code {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.lt-row {
  display: flex;
  justify-content: space-between;
  margin: 3px 0;
}
.lt-k {
  color: var(--text-secondary);
  font-size: 11px;
}
.lt-v {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
}
.lt-section {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--border-light);
}
.lt-section-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: 4px;
}
.lt-source {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  margin: 3px 0;
  word-break: break-all;
}
.lt-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}
.lt-badge {
  font-size: 10px;
  background: var(--bg-tertiary);
  color: var(--accent-light);
  padding: 1px 8px;
  border-radius: var(--radius-full);
}
</style>