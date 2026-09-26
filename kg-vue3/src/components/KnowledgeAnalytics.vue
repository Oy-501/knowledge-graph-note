<template>
  <div class="ka">
    <!-- 空态 -->
    <div v-if="graph.nodes.length === 0" class="ka-empty">
      <svg class="ka-empty-icon" viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <circle cx="16" cy="14" r="4" stroke="currentColor" stroke-width="1.6" />
        <circle cx="34" cy="20" r="4" stroke="currentColor" stroke-width="1.6" />
        <circle cx="22" cy="34" r="4" stroke="currentColor" stroke-width="1.6" />
        <circle cx="38" cy="36" r="3" stroke="currentColor" stroke-width="1.6" />
        <path
          d="M19 16 L30 21 M18 17 L21 30 M26 33 L35 34"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
        />
      </svg>
      <p>暂无图谱数据，先上传文件构建知识图谱</p>
    </div>

    <template v-else>
      <!-- 基础指标（2 列小卡片） -->
      <div class="ka-metrics">
        <div class="ka-card" v-for="m in metrics" :key="m.label">
          <div class="ka-num">{{ m.value }}</div>
          <div class="ka-label">{{ m.label }}</div>
        </div>
      </div>

      <!-- 中心度 Top -->
      <div class="ka-section">
        <div class="ka-section-title">中心度 Top</div>

        <div class="ka-subtitle">度中心度</div>
        <div class="ka-rank" v-for="(it, i) in degreeTop" :key="it.id">
          <span class="ka-rank-idx">{{ i + 1 }}</span>
          <span class="ka-rank-name">{{ it.title }}</span>
          <span class="ka-rank-val">{{ it.degree }}</span>
        </div>

        <template v-if="betweennessTop.length">
          <div class="ka-subtitle">介数中心度</div>
          <div class="ka-rank" v-for="(it, i) in betweennessTop" :key="it.id">
            <span class="ka-rank-idx">{{ i + 1 }}</span>
            <span class="ka-rank-name">{{ it.title }}</span>
            <span class="ka-rank-val">{{ it.bc }}</span>
          </div>
        </template>
        <div v-if="betweennessSkipped" class="ka-skip">节点数超过 300，已跳过介数中心度计算</div>

        <template v-if="pagerankTop.length">
          <div class="ka-subtitle">PageRank 核心枢纽</div>
          <div class="ka-rank" v-for="(it, i) in pagerankTop" :key="it.id">
            <span class="ka-rank-idx">{{ i + 1 }}</span>
            <span class="ka-rank-name">{{ it.title }}</span>
            <span class="ka-rank-val">{{ it.pr.toFixed(3) }}</span>
          </div>
        </template>
      </div>

      <!-- 知识断层区域 -->
      <div class="ka-section" v-if="faultZones.length">
        <div class="ka-section-title">知识断层区域</div>
        <div class="ka-rank" v-for="(z, i) in faultZones" :key="i">
          <span class="ka-rank-idx">{{ z.size }}</span>
          <span class="ka-rank-name">{{ z.titles.join(' / ') }}</span>
        </div>
      </div>

      <!-- 薄弱环节 -->
      <div class="ka-section" v-if="weakNodes.length">
        <div class="ka-section-title">薄弱环节（低连接度）</div>
        <div class="ka-rank" v-for="(w, i) in weakNodes" :key="w.id">
          <span class="ka-rank-idx">{{ i + 1 }}</span>
          <span class="ka-rank-name">{{ w.title }}</span>
          <span class="ka-rank-val">度 {{ w.degree }}</span>
        </div>
      </div>

      <!-- 报告按钮 -->
      <button class="ka-report-btn" type="button" @click="dialogVisible = true">生成知识结构报告</button>
    </template>

    <!-- 知识结构报告对话框 -->
    <el-dialog
      v-model="dialogVisible"
      title="知识结构报告"
      width="480px"
      :append-to-body="true"
      class="ka-dialog"
    >
      <div class="ka-report" v-if="report">
        <p class="ka-report-overview">{{ report.overview }}</p>
        <p class="ka-report-hub">{{ report.hub }}</p>
        <p class="ka-report-structure">{{ report.structure }}</p>
        <div class="ka-report-suggestions" v-if="report.suggestions.length">
          <div class="ka-report-sugg-title">优化建议</div>
          <ul>
            <li v-for="(s, i) in report.suggestions" :key="i">{{ s }}</li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useGraphStore } from '@/store/graphStore'
import { endpointId } from '@/utils/graph'

const graphStore = useGraphStore()

// 有效子图：丢弃节点用 validate.status === 'discarded' 判断（不是 status）
const graph = computed(() => {
  const nodes = graphStore.nodes.filter(n => n.validate?.status !== 'discarded')
  const idSet = new Set(nodes.map(n => n.id))
  const links = []
  for (const l of graphStore.links || []) {
    // source/target 可能是字符串 id，也可能被 D3 改写成对象
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    if (idSet.has(s) && idSet.has(t)) {
      links.push({ s, t })
    }
  }
  return { nodes, links }
})

const N = computed(() => graph.value.nodes.length)
const E = computed(() => graph.value.links.length)

// 每个节点的度数
const degreeMap = computed(() => {
  const map = new Map()
  for (const n of graph.value.nodes) map.set(n.id, 0)
  for (const l of graph.value.links) {
    map.set(l.s, (map.get(l.s) || 0) + 1)
    map.set(l.t, (map.get(l.t) || 0) + 1)
  }
  return map
})

const density = computed(() =>
  N.value > 1 ? (2 * E.value) / (N.value * (N.value - 1)) : 0
)
const avgDegree = computed(() =>
  N.value > 0 ? (2 * E.value) / N.value : 0
)

const isolatedCount = computed(() => {
  let c = 0
  for (const d of degreeMap.value.values()) if (d === 0) c++
  return c
})

// 连通分量：并查集（union-find）分组，返回 [{ size, members }]（members 按度降序）
const componentGroups = computed(() => {
  const parent = new Map()
  for (const n of graph.value.nodes) parent.set(n.id, n.id)
  const find = x => {
    while (parent.get(x) !== x) {
      parent.set(x, parent.get(parent.get(x)))
      x = parent.get(x)
    }
    return x
  }
  for (const l of graph.value.links) {
    const ra = find(l.s)
    const rb = find(l.t)
    if (ra !== rb) parent.set(ra, rb)
  }
  const groups = new Map()
  for (const n of graph.value.nodes) {
    const root = find(n.id)
    if (!groups.has(root)) groups.set(root, [])
    groups.get(root).push(n)
  }
  return Array.from(groups.values())
    .map(members => ({
      size: members.length,
      members: members.sort((a, b) => (degreeMap.value.get(b.id) || 0) - (degreeMap.value.get(a.id) || 0))
    }))
    .sort((a, b) => b.size - a.size)
})
const componentCount = computed(() => componentGroups.value.length)

const metrics = computed(() => [
  { label: '节点数', value: N.value },
  { label: '连线数', value: E.value },
  { label: '网络密度', value: density.value.toFixed(3) },
  { label: '平均度', value: avgDegree.value.toFixed(1) },
  { label: '连通分量', value: componentCount.value },
  { label: '孤立节点', value: isolatedCount.value },
])

// 度中心度 Top5（降序）
const degreeTop = computed(() =>
  graph.value.nodes
    .map(n => ({ id: n.id, title: n.title || n.id, degree: degreeMap.value.get(n.id) || 0 }))
    .sort((a, b) => b.degree - a.degree)
    .slice(0, 5)
)

// 介数中心度 Top3（Brandes，无向无权；节点数 > 300 跳过）
const betweennessSkipped = computed(() => N.value > 300)
const betweennessTop = computed(() => {
  if (betweennessSkipped.value || N.value === 0) return []
  const nodeIds = graph.value.nodes.map(n => n.id)
  const edges = graph.value.links.map(l => [l.s, l.t])
  const bc = brandesBetweenness(nodeIds, edges)
  return graph.value.nodes
    .map(n => ({ id: n.id, title: n.title || n.id, bc: bc.get(n.id) || 0 }))
    .sort((a, b) => b.bc - a.bc)
    .filter(x => x.bc > 0)
    .slice(0, 3)
})

// Brandes 介数中心度（无向无权图，结果除以 2 修正无向重复计数）
function brandesBetweenness(nodeIds, edges) {
  const C = new Map()
  const adj = new Map()
  for (const id of nodeIds) {
    C.set(id, 0)
    adj.set(id, [])
  }
  for (const [u, v] of edges) {
    adj.get(u).push(v)
    adj.get(v).push(u)
  }

  for (const s of nodeIds) {
    const S = []
    const P = new Map()
    const sigma = new Map()
    const d = new Map()
    for (const id of nodeIds) {
      P.set(id, [])
      sigma.set(id, 0)
      d.set(id, -1)
    }
    sigma.set(s, 1)
    d.set(s, 0)
    const Q = [s]

    while (Q.length) {
      const v = Q.shift()
      S.push(v)
      for (const w of adj.get(v)) {
        if (d.get(w) < 0) {
          Q.push(w)
          d.set(w, d.get(v) + 1)
        }
        if (d.get(w) === d.get(v) + 1) {
          sigma.set(w, sigma.get(w) + sigma.get(v))
          P.get(w).push(v)
        }
      }
    }

    const delta = new Map()
    for (const id of nodeIds) delta.set(id, 0)
    while (S.length) {
      const w = S.pop()
      for (const v of P.get(w)) {
        delta.set(v, delta.get(v) + (sigma.get(v) / sigma.get(w)) * (1 + delta.get(w)))
      }
      if (w !== s) C.set(w, C.get(w) + delta.get(w))
    }
  }

  // 无向图：每条最短路径被两端各计一次，修正
  for (const id of nodeIds) C.set(id, C.get(id) / 2)
  return C
}

// PageRank 中心度（无向图幂迭代，阻尼 0.85，40 次收敛）Top 10
const pagerankTop = computed(() => {
  const nodeIds = graph.value.nodes.map(n => n.id)
  if (!nodeIds.length) return []
  const idx = new Map()
  nodeIds.forEach((id, i) => idx.set(id, i))
  const n = nodeIds.length
  const adj = Array.from({ length: n }, () => [])
  const outdeg = new Array(n).fill(0)
  for (const l of graph.value.links) {
    const iu = idx.get(l.s), iv = idx.get(l.t)
    if (iu == null || iv == null) continue
    adj[iu].push(iv)
    adj[iv].push(iu)
    outdeg[iu]++
    outdeg[iv]++
  }
  let pr = new Array(n).fill(1 / n)
  const damp = 0.85
  for (let iter = 0; iter < 40; iter++) {
    const next = new Array(n).fill((1 - damp) / n)
    for (let i = 0; i < n; i++) {
      if (outdeg[i] === 0) continue
      const share = (damp * pr[i]) / outdeg[i]
      for (const j of adj[i]) next[j] += share
    }
    const sum = next.reduce((a, b) => a + b, 0) || 1
    for (let i = 0; i < n; i++) next[i] /= sum
    pr = next
  }
  return nodeIds
    .map((id, i) => ({ id, title: graph.value.nodes.find(x => x.id === id)?.title || id, pr: pr[i] }))
    .sort((a, b) => b.pr - a.pr)
    .slice(0, 10)
})

// 知识断层区域：规模 2~4 的小型孤立簇（关联稀疏，尚未融入主网络）
const faultZones = computed(() => {
  return componentGroups.value
    .filter(g => g.size >= 2 && g.size <= 4)
    .map(g => ({ size: g.size, titles: g.members.map(m => m.title || m.id) }))
})

// 薄弱环节：度 ≤1 的边缘节点（有连接但连接薄弱），按 level 高优先取前 5
const weakNodes = computed(() => {
  return graph.value.nodes
    .map(n => ({ id: n.id, title: n.title || n.id, degree: degreeMap.value.get(n.id) || 0, level: n.level || 3 }))
    .filter(x => x.degree === 1)
    .sort((a, b) => (b.level - a.level) || (b.degree - a.degree))
    .slice(0, 5)
})

// 知识结构报告
const dialogVisible = ref(false)
const report = computed(() => {
  const n = N.value
  if (n === 0) return null
  const e = E.value
  const d = density.value

  let densityLevel
  if (d < 0.05) densityLevel = '偏低'
  else if (d < 0.2) densityLevel = '适中'
  else densityLevel = '较高'

  const prHub = pagerankTop.value[0]
  const k = componentCount.value
  const m = isolatedCount.value
  const fz = faultZones.value
  const wk = weakNodes.value

  const suggestions = []
  if (d < 0.05) suggestions.push('建议补充跨主题关联')
  if (m > 0) suggestions.push(`有 ${m} 个孤立知识点，建议为其建立关联`)
  if (k > 1) suggestions.push(`存在 ${k} 个互不连通的知识簇，建议建立桥接知识点`)
  if (fz.length > 0) suggestions.push(`发现 ${fz.length} 个关联稀疏的知识断层区域，建议优先打通`)
  if (wk.length > 0) suggestions.push(`「${wk.map(w => w.title).slice(0, 3).join('、')}」等边缘知识点连接薄弱，建议补充关联`)
  if (n < 10) suggestions.push('知识库规模较小，建议持续录入')

  return {
    overview: `共 ${n} 个知识点、${e} 条关联，网络密度 ${d.toFixed(3)}（${densityLevel}）`,
    hub: prHub ? `核心枢纽节点是「${prHub.title}」（PageRank ${prHub.pr.toFixed(4)}）` : '暂无枢纽节点',
    structure: `网络包含 ${k} 个连通分量，${m} 个孤立知识点，${fz.length} 个知识断层区域`,
    suggestions,
  }
})
</script>

<style scoped>
.ka {
  padding: 12px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 空态 */
.ka-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 28px 16px;
  color: var(--text-muted);
}
.ka-empty-icon {
  width: 44px;
  height: 44px;
  color: var(--apricot);
  opacity: 0.75;
  margin-bottom: 10px;
}
.ka-empty p {
  font-size: var(--fs-sm);
  line-height: 1.6;
}

/* 基础指标：2 列小卡片网格 */
.ka-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.ka-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 10px 12px;
  text-align: center;
  transition: box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.ka-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.ka-num {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--accent);
  line-height: 1.2;
}
.ka-label {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-top: 3px;
}

/* 中心度 Top */
.ka-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ka-section-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.ka-subtitle {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  margin-top: 4px;
}
.ka-rank {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  transition: background var(--dur-fast);
}
.ka-rank:hover {
  background: var(--bg-tertiary);
}
.ka-rank-idx {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 50%;
}
.ka-rank-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}
.ka-rank-val {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  /* 深色下 --mint-strong 别名指向深紫，只有 3.2:1，文字场景改用浅紫 */
  color: var(--violet-text);
}
.ka-skip {
  font-size: var(--fs-xs);
  color: var(--text-muted);
  padding: 4px 2px;
}

/* 胶囊主按钮 */
.ka-report-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 8px 14px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}
.ka-report-btn:hover {
  background: var(--accent-strong);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.ka-report-btn:active {
  transform: scale(0.97);
}

/* 报告内容 */
.ka-report {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: var(--fs-md);
  line-height: 1.7;
  color: var(--text-primary);
}
.ka-report-overview {
  color: var(--text-primary);
}
.ka-report-hub {
  color: var(--text-secondary);
}
.ka-report-structure {
  color: var(--text-secondary);
}
.ka-report-suggestions {
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid var(--border-light);
}
.ka-report-sugg-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.ka-report-suggestions ul {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ka-report-suggestions li {
  position: relative;
  padding: 7px 10px 7px 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.ka-report-suggestions li::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
}
</style>
