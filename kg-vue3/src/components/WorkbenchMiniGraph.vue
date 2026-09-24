<template>
  <div class="mini-graph-panel">
    <div class="mg-header">
      <span class="mg-title">🕸️ 当前笔记的知识网络</span>
      <div class="mg-mode">
        <span class="mg-depth-label">深度</span>
        <button type="button"
          v-for="d in [1, 2, 3]"
          :key="d"
          class="mg-mode-btn"
          :class="{ active: depth === d }"
          @click="setDepth(d)"
        >{{ d }}跳</button>
        <span class="mg-info">
          <span class="mg-dot mg-linked"></span> 已关联
          <span class="mg-dot mg-pending"></span> 待确认
          <span class="mg-dot mg-unlinked"></span> 扩展
        </span>
      </div>
    </div>
    <div ref="svgContainer" class="mg-svg-container">
      <svg ref="svgEl" class="mg-svg"></svg>
      <div v-if="!hasNodes" class="mg-empty">暂无关联知识点</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { select } from 'd3-selection'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { drag } from 'd3-drag'
import { useGraphStore } from '@/store/graphStore'
import { useNoteStore } from '@/store/noteStore'
import { useFileStore } from '@/store/fileStore'

const props = defineProps({
  linkedNodeIds: { type: Array, default: () => [] },
  linkedFileIds: { type: Array, default: () => [] },
  currentNoteTitle: { type: String, default: '当前笔记' },
  matchedNodeIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['node-click'])

const graphStore = useGraphStore()
const noteStore = useNoteStore()
const fileStore = useFileStore()

const svgContainer = ref(null)
const svgEl = ref(null)
let simulation = null
let resizeObserver = null

const depth = ref(1) // 显示深度：1=直接关联；2/3=向外扩展 1/2 跳
function setDepth(d) {
  depth.value = d
}

const hasNodes = computed(() => {
  return graphNodes.value.length > 0
})

/** 种子：已关联 + 待确认节点（层 1） */
const seedIds = computed(() => new Set([...props.linkedNodeIds, ...props.matchedNodeIds]))
/** 从种子出发向外 BFS（depth-1）跳，返回 邻居 id -> 层数（2..depth） */
const expandedNeighbors = computed(() => {
  const result = new Map()
  if (depth.value < 2) return result
  const adj = new Map()
  for (const l of graphStore.links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (!adj.has(s)) adj.set(s, [])
    if (!adj.has(t)) adj.set(t, [])
    adj.get(s).push(t)
    adj.get(t).push(s)
  }
  const seen = new Set(seedIds.value)
  let frontier = [...seedIds.value]
  for (let d = 1; d < depth.value; d++) {
    const next = []
    for (const id of frontier) {
      for (const nb of (adj.get(id) || [])) {
        if (!seen.has(nb)) {
          seen.add(nb)
          result.set(nb, d + 1)
          next.push(nb)
        }
      }
    }
    frontier = next
  }
  return result
})

const graphNodes = computed(() => {
  const allIds = new Set()
  const nodes = []

  // 当前笔记节点
  nodes.push({
    id: 'current_note',
    title: props.currentNoteTitle || '当前笔记',
    isNote: true,
    _color: '#f5b462'
  })
  allIds.add('current_note')

  // 已关联的知识点
  for (const nid of props.linkedNodeIds) {
    const node = graphStore.nodes.find(n => n.id === nid)
    if (node && !allIds.has(node.id)) {
      nodes.push({
        id: node.id,
        title: node.title,
        _color: '#4caf50',
        _linked: true,
        _node: node
      })
      allIds.add(node.id)
    }
  }

  // 匹配到的知识点（待确认）
  for (const nid of props.matchedNodeIds) {
    if (allIds.has(nid)) continue
    const node = graphStore.nodes.find(n => n.id === nid)
    if (node) {
      nodes.push({
        id: node.id,
        title: node.title,
        _color: '#e8a020',
        _pending: true,
        _node: node
      })
      allIds.add(node.id)
    }
  }

  // 扩展邻居节点（BFS 层 2..depth，灰色，半径随层递减）
  for (const [nid, layer] of expandedNeighbors.value) {
    if (allIds.has(nid)) continue
    const node = graphStore.nodes.find(n => n.id === nid)
    if (node) {
      nodes.push({
        id: node.id,
        title: node.title,
        _color: '#8A9AA8',
        _neighbor: true,
        _depth: layer,
        _node: node
      })
      allIds.add(node.id)
    }
  }

  return nodes
})

// 连线：当前笔记 → 已关联节点；邻里模式额外加 seed↔邻里 连线
const graphLinks = computed(() => {
  const links = []
  for (const nid of props.linkedNodeIds) {
    links.push({ source: 'current_note', target: nid, _linked: true })
  }
  // 虚线：待确认节点
  for (const nid of props.matchedNodeIds) {
    if (!props.linkedNodeIds.includes(nid)) {
      links.push({ source: 'current_note', target: nid, _pending: true })
    }
  }
  // 扩展连线：allowed 集合内（种子 + 扩展邻居），至少一端是扩展邻居的边
  if (depth.value >= 2) {
    const allowed = new Set(['current_note', ...seedIds.value, ...expandedNeighbors.value.keys()])
    const seenLinks = new Set()
    for (const l of graphStore.links) {
      const s = typeof l.source === 'object' ? l.source.id : l.source
      const t = typeof l.target === 'object' ? l.target.id : l.target
      if (!allowed.has(s) || !allowed.has(t)) continue
      if (!expandedNeighbors.value.has(s) && !expandedNeighbors.value.has(t)) continue
      const key = s < t ? s + '|' + t : t + '|' + s
      if (seenLinks.has(key)) continue
      seenLinks.add(key)
      links.push({ source: s, target: t, _neighbor: true })
    }
  }
  return links
})

function render() {
  if (!svgEl.value) return
  const svg = select(svgEl.value)
  svg.selectAll('*').remove()

  const container = svgContainer.value
  if (!container) return
  const width = container.clientWidth || 400
  const height = container.clientHeight || 140

  svg.attr('width', width).attr('height', height)

  // 类型渐变 defs（与主图配色一致）
  const defs = svg.append('defs')
  const mkLinear = (id, c1, c2) => {
    const g = defs.append('linearGradient').attr('id', id)
      .attr('x1', 0).attr('y1', 0).attr('x2', 1).attr('y2', 1)
    g.append('stop').attr('offset', '0%').attr('stop-color', c1)
    g.append('stop').attr('offset', '100%').attr('stop-color', c2)
  }
  mkLinear('mgGradNote', '#D4A574', '#E8C9A0')
  mkLinear('mgGradUser', '#4F6F8F', '#7CB8A0')

  const nodes = graphNodes.value
  const links = graphLinks.value
  if (nodes.length === 0) return

  // 创建力模拟
  if (simulation) simulation.stop()

  const g = svg.append('g')

  simulation = forceSimulation(nodes)
    .force('link', forceLink(links).id(d => d.id).distance(60))
    .force('charge', forceManyBody().strength(-200))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collision', forceCollide(20))

  // 连线
  const link = g.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', d => {
      if (d._linked) return 'rgba(124, 184, 160, 0.8)'
      if (d._neighbor) return 'rgba(138, 154, 168, 0.55)'
      return 'rgba(212, 165, 116, 0.75)'
    })
    .attr('stroke-width', d => d._linked ? 1.5 : 1)
    .attr('stroke-dasharray', d => d._pending || d._neighbor ? '4,3' : null)
    .attr('stroke-linecap', 'round')
    .attr('opacity', 0.7)

  // 节点组
  const node = g.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'mini-node')
    .call(drag()
      .on('start', (ev, d) => {
        if (!ev.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (ev, d) => {
        d.fx = ev.x
        d.fy = ev.y
      })
      .on('end', (ev, d) => {
        if (!ev.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })
    )

  node.append('circle')
    .attr('r', d => {
      if (d.isNote) return 8
      if (d._neighbor) return Math.max(3.5, 6 - (d._depth || 2) * 1.2)
      return 6
    })
    .attr('fill', d => {
      if (d.isNote) return 'url(#mgGradNote)'
      if (d._linked) return 'url(#mgGradUser)'
      if (d._neighbor) return '#8A9AA8'
      return '#D4A574'
    })
    .attr('stroke', 'var(--bg-primary)')
    .attr('stroke-width', 1.5)
    .style('cursor', 'pointer')
    .style('opacity', d => d._neighbor ? 0.7 : 1)

  node.append('text')
    .text(d => d.title.length > 12 ? d.title.slice(0, 12) + '..' : d.title)
    .attr('font-size', 9)
    .attr('fill', 'var(--text-secondary)')
    .attr('text-anchor', 'middle')
    .attr('dy', 16)

  node.on('click', (ev, d) => {
    if (!d.isNote) {
      emit('node-click', d.id)
    }
  })

  node.append('title')
    .text(d => d.title)

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)

    node.attr('transform', d => `translate(${d.x},${d.y})`)
  })
}

watch([graphNodes, graphLinks], () => {
  nextTick(() => render())
})

onMounted(() => {
  nextTick(() => render())
  if (svgContainer.value) {
    resizeObserver = new ResizeObserver(() => {
      nextTick(() => render())
    })
    resizeObserver.observe(svgContainer.value)
  }
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  if (resizeObserver) resizeObserver.disconnect()
})
</script>

<style scoped>
.mini-graph-panel {
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.mg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-light);
}
.mg-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}
.mg-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 9px;
  color: var(--text-muted);
}
.mg-mode {
  display: flex;
  align-items: center;
  gap: 4px;
}
.mg-depth-label {
  font-size: 9px;
  color: var(--text-muted);
}
.mg-mode-btn {
  border: 1px solid var(--border-light);
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-size: 9px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.mg-mode-btn:hover {
  color: var(--text-primary);
}
.mg-mode-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.mg-mode .mg-info {
  margin-left: 6px;
}
.mg-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 2px;
}
.mg-linked { background: var(--mint); }
.mg-pending { background: var(--apricot); }
.mg-unlinked { background: #8A9AA8; }
.mg-svg-container {
  height: 140px;
  position: relative;
}
.mg-svg {
  width: 100%;
  height: 100%;
}
.mg-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
}
/* D3 生成节点：hover 光晕 */
.mg-svg-container :deep(g.mini-node circle) {
  transition: filter 0.15s var(--ease-out);
}
.mg-svg-container :deep(g.mini-node:hover circle) {
  filter: drop-shadow(0 0 5px rgba(79, 111, 143, 0.5));
}
</style>