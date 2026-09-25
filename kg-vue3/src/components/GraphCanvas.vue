<template>
  <div class="canvas-wrap" ref="wrapRef">
    <!-- 分组快速筛选 -->
    <div v-if="graphStore.nodes.length > 0" class="canvas-group-filter">
      <select class="cfs-select" :value="groupStore.currentGroupId" @change="onGroupFilterChange($event.target.value)">
        <option value="all">全部节点 ({{ graphStore.nodeCount }})</option>
        <option v-for="g in groupStore.groups" :key="g.id" :value="g.id">
          {{ g.name }} ({{ g.count }})
        </option>
      </select>
    </div>

    <!-- 图谱样式面板（左上角） -->
    <div v-if="graphStore.nodes.length > 0" class="canvas-style-panel">
      <div class="csp-row">
        <span class="csp-label">颜色</span>
        <select
          class="cfs-select csp-select"
          :value="graphStore.graphFilters.colorMode"
          @change="graphStore.setGraphFilters({ colorMode: $event.target.value })"
        >
          <option value="type">按类型</option>
          <option value="folder">按文件夹</option>
          <option value="single">单色</option>
        </select>
      </div>
      <div class="csp-row">
        <span class="csp-label">大小</span>
        <select
          class="cfs-select csp-select"
          :value="graphStore.graphFilters.sizeMode"
          @change="graphStore.setGraphFilters({ sizeMode: $event.target.value })"
        >
          <option value="degree">按度数</option>
          <option value="weight">按权重</option>
          <option value="fixed">固定</option>
        </select>
      </div>
      <div class="csp-row">
        <span class="csp-label">文件夹</span>
        <select
          class="cfs-select csp-select"
          :value="graphStore.graphFilters.folders[0] || ''"
          @change="onFolderFilterChange($event.target.value)"
        >
          <option value="">全部文件夹</option>
          <option v-for="o in graphStore.folderOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="csp-row">
        <span class="csp-label">标签</span>
        <select
          class="cfs-select csp-select"
          :value="graphStore.graphFilters.tags[0] || ''"
          @change="onTagFilterChange($event.target.value)"
        >
          <option value="">全部标签</option>
          <option v-for="o in graphStore.tagOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="csp-row csp-rel-row">
        <span class="csp-label">关系</span>
        <div class="csp-chips">
          <label
            v-for="o in graphStore.relationTypeOptions"
            :key="o.value"
            class="csp-chip"
            :class="{ 'is-active': graphStore.graphFilters.relationTypes.includes(o.value) }"
          >
            <input
              type="checkbox"
              :value="o.value"
              :checked="graphStore.graphFilters.relationTypes.includes(o.value)"
              @change="onRelationTypeToggle(o.value, $event.target.checked)"
            />
            <span>{{ o.label }}</span>
          </label>
        </div>
      </div>
      <div class="csp-row csp-rel-row">
        <span class="csp-label">节点</span>
        <div class="csp-chips">
          <label
            v-for="o in graphStore.nodeTypeOptions"
            :key="o.value"
            class="csp-chip"
            :class="{ 'is-active': graphStore.graphFilters.nodeTypes.includes(o.value) }"
          >
            <input
              type="checkbox"
              :value="o.value"
              :checked="graphStore.graphFilters.nodeTypes.includes(o.value)"
              @change="onNodeTypeToggle(o.value, $event.target.checked)"
            />
            <span>{{ o.label }}</span>
          </label>
        </div>
      </div>
      <div class="csp-row">
        <span class="csp-label">强度≥{{ graphStore.graphFilters.minScore.toFixed(2) }}</span>
        <input
          type="range"
          class="csp-range"
          min="0"
          max="1"
          step="0.05"
          :value="graphStore.graphFilters.minScore"
          @input="onMinScoreChange($event.target.value)"
        />
      </div>
    </div>

    <svg ref="svgRef"></svg>

    <div class="empty-overlay" v-if="graphStore.nodes.length === 0">
      <div class="icon">🧠</div>
      <h2>知识关联图谱</h2>
      <p>左侧拖拽上传 .md/.txt 文件，自动解析知识点并构建六种关系类型关联</p>
    </div>

    <LinkTooltip
      :visible="tooltip.visible"
      :x="tooltip.x"
      :y="tooltip.y"
      :data="tooltip.data"
      :source="tooltip.source"
      :target="tooltip.target"
    />

    <!-- 节点详情抽屉 -->
    <NodeDetailDrawer
      :visible="drawer.visible"
      :node="drawer.node"
      :links="drawer.links"
      :allNodes="graphStore.nodes"
      @close="closeDrawer"
    />

    <!-- 右键菜单 -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <div class="ctx-item" @click="onContextMenuIsolate">🚫 互相隔离</div>
      <div class="ctx-item ctx-cancel" @click="onContextMenuClose">取消</div>
    </div>

    <!-- 隔离模式提示 -->
    <div v-if="waitingForIsolateTarget !== null" class="isolate-mode-hint">
      🔒 请点击目标节点以完成隔离
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { select } from 'd3-selection'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { zoom } from 'd3-zoom'
import { drag } from 'd3-drag'
import { ElMessage } from 'element-plus'
import { useGraphStore } from '@/store/graphStore'
import { useConfigStore } from '@/store/configStore'
import { useGroupStore } from '@/store/groupStore'
import LinkTooltip from './LinkTooltip.vue'
import NodeDetailDrawer from './NodeDetailDrawer.vue'
import { getRelationColor, getRelationLineStyle } from '@/utils/relationClassifier'
import { getLevelBorderWidth } from '@/utils/mdParser'
import { getNodeValidationStatus } from '@/utils/noteValidator'

const graphStore = useGraphStore()
const cfg = useConfigStore()
const groupStore = useGroupStore()

const wrapRef = ref(null)
const svgRef = ref(null)

let svg, gRoot, gLinks, gNodes, simulation, zoomBehavior
let nodeSel, linkSel

const width = ref(0), height = ref(0)

const tooltip = ref({
  visible: false,
  x: 0,
  y: 0,
  data: {},
  source: null,
  target: null
})

const drawer = ref({
  visible: false,
  node: null,
  links: []
})

// 右键菜单状态
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  nodeId: null
})

let highlightActive = false
let highlightNodeId = null

onMounted(() => {
  initSvg()
  window.addEventListener('resize', onResize)
  render()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (simulation) simulation.stop()
})

function onResize() {
  if (!wrapRef.value) return
  width.value = wrapRef.value.clientWidth
  height.value = wrapRef.value.clientHeight
  if (svg) {
    svg.attr('viewBox', `0 0 ${width.value} ${height.value}`)
  }
  if (simulation) {
    simulation.force('center', forceCenter(width.value / 2, height.value / 2))
    simulation.alpha(0.3).restart()
  }
}

function initSvg() {
  width.value = wrapRef.value.clientWidth
  height.value = wrapRef.value.clientHeight

  svg = select(svgRef.value)
    .attr('viewBox', `0 0 ${width.value} ${height.value}`)

  // defs - 渐变发光
  const defs = svg.append('defs')
  const grad = defs.append('radialGradient').attr('id', 'nodeGlow')
  grad.append('stop').attr('offset', '0%').attr('stop-color', '#7eb0ff')
  grad.append('stop').attr('offset', '100%').attr('stop-color', '#5b9bf3')

  const gradGhost = defs.append('radialGradient').attr('id', 'nodeGhost')
  gradGhost.append('stop').attr('offset', '0%').attr('stop-color', '#8a93b0')
  gradGhost.append('stop').attr('offset', '100%').attr('stop-color', '#5a6582')

  const gradCorpus = defs.append('radialGradient').attr('id', 'nodeCorpus')
  gradCorpus.append('stop').attr('offset', '0%').attr('stop-color', '#a0a8c0')
  gradCorpus.append('stop').attr('offset', '100%').attr('stop-color', '#6a7388')

  // 节点类型渐变（用户蓝紫→薄荷 / 知识库灰 / 笔记暖杏）
  const mkLinear = (id, c1, c2) => {
    const g = defs.append('linearGradient').attr('id', id)
      .attr('x1', 0).attr('y1', 0).attr('x2', 1).attr('y2', 1)
    g.append('stop').attr('offset', '0%').attr('stop-color', c1)
    g.append('stop').attr('offset', '100%').attr('stop-color', c2)
  }
  mkLinear('kgGradUser', '#4F6F8F', '#7CB8A0')
  mkLinear('kgGradCorpus', '#8A9AA8', '#B8C4D0')
  mkLinear('kgGradNote', '#D4A574', '#E8C9A0')

  // 极淡网格背景 pattern（中性色，明暗主题通用）
  const gridPat = defs.append('pattern')
    .attr('id', 'kgGrid')
    .attr('width', 28).attr('height', 28)
    .attr('patternUnits', 'userSpaceOnUse')
  gridPat.append('path')
    .attr('d', 'M28 0H0V28')
    .attr('fill', 'none')
    .attr('stroke', 'rgba(128,138,152,0.07)')
    .attr('stroke-width', 1)

  gRoot = svg.append('g')
  // 网格背景层：置于最底层，随缩放平移，不遮挡节点
  gRoot.append('rect')
    .attr('class', 'kg-grid-bg')
    .attr('x', -10000).attr('y', -10000)
    .attr('width', 20000).attr('height', 20000)
    .attr('fill', 'url(#kgGrid)')
  zoomBehavior = zoom().scaleExtent([0.2, 5]).on('zoom', e => {
    gRoot.attr('transform', e.transform)
  })
  svg.call(zoomBehavior)

  gLinks = gRoot.append('g').attr('class', 'links')
  gNodes = gRoot.append('g').attr('class', 'nodes')

  // 大图谱下降低斥力、加快收敛：几千节点的力导向若用默认参数会长时间占满主线程
  const nodeTotal = graphStore.nodes?.length || 0

  simulation = forceSimulation()
    .force('link', forceLink().id(d => d.id).distance(d => linkDistance(d)).strength(d => linkStrength(d)))
    .force('charge', forceManyBody().strength(nodeTotal > 1500 ? -60 : (nodeTotal > 800 ? -110 : -180)))
    .force('center', forceCenter(width.value / 2, height.value / 2))
    .force('collide', forceCollide().radius(d => nodeRadius(d) + 4))
    .on('tick', onTick)
  if (nodeTotal > 800) simulation.alphaDecay(0.05)
}

function linkDistance(d) {
  const w = Math.max(0.05, d.score || 0.3)
  return Math.max(60, 220 - w * 160)
}
function linkStrength(d) {
  const w = Math.max(0.05, d.score || 0.3)
  return 0.05 + w * 0.4
}
function nodeRadius(d) {
  const f = graphStore.graphFilters
  if (f.sizeMode === 'fixed') return 14
  if (f.sizeMode === 'weight') return Math.max(10, 10 + Math.min(20, (d._weight || 0) * 6))
  let deg = (d._deg || 0)
  return Math.max(10, 10 + Math.min(20, deg * 2))
}

function onTick() {
  if (!gLinks || !gNodes) return
  gLinks.selectAll('path.link-line')
    .attr('d', d => linkPath(d))
  gNodes.selectAll('g.node-group')
    .attr('transform', d => `translate(${d.x},${d.y})`)
}

/* ============ 渲染主入口（D3 通用更新模式 + 渐进式渲染）============ */
function render() {
  if (!svg) return
  const allNodes = graphStore.nodes
  // 根据当前分组过滤节点
  let nodes = allNodes
  if (groupStore.currentGroupId !== 'all') {
    nodes = allNodes.filter(n => n.groupId === groupStore.currentGroupId)
  }
  // 过滤掉隐藏分组中的节点
  const hiddenNodeIds = groupStore.getHiddenNodeIds()
  if (hiddenNodeIds.size > 0) {
    nodes = nodes.filter(n => !hiddenNodeIds.has(n.id))
  }
  // 过滤掉已丢弃节点
  nodes = nodes.filter(n => n.validate?.status !== 'discarded')
  // 图谱交互增强：按文件夹 / 标签 / 节点类型过滤节点
  const f = graphStore.graphFilters
  if (f.folders.length) nodes = nodes.filter(n => f.folders.includes(n.fileId))
  if (f.tags.length) {
    nodes = nodes.filter(
      n => (n.keywords || []).some(k => f.tags.includes(k))
        || (n.entities || []).some(e => f.tags.includes(e))
    )
  }
  if (f.nodeTypes.length) nodes = nodes.filter(n => f.nodeTypes.includes(nodeCategory(n)))
  const nodeIds = new Set(nodes.map(n => n.id))
  let links = graphStore.links.filter(l => {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    return nodeIds.has(s) && nodeIds.has(t)
  }).map(l => ({ ...l }))
  // 按关系类型过滤连线
  if (f.relationTypes.length) links = links.filter(l => f.relationTypes.includes(l.relation_type))
  // 按关联强度阈值过滤连线（只显示 score >= minScore）
  if (f.minScore > 0) links = links.filter(l => (l.score || 0) >= f.minScore)

  // 标记隔离连线
  markIsolatedLinks(links)

  // 计算度数 / 权重
  const deg = new Map()
  const nodeById = new Map()
  for (const n of nodes) { deg.set(n.id, 0); n._weight = 0; nodeById.set(n.id, n) }
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    deg.set(s, (deg.get(s) || 0) + 1)
    deg.set(t, (deg.get(t) || 0) + 1)
    const w = l.final_weight || l.score || 1
    const sn = nodeById.get(s)
    const tn = nodeById.get(t)
    if (sn) sn._weight += w
    if (tn) tn._weight += w
  }
  for (const n of nodes) n._deg = deg.get(n.id) || 0

  // === 渐进式渲染：>200 节点时分批 ===
  const useProgressive = nodes.length > 200

  // === 大图谱保护：每个节点要画 2 个 <text>，几千节点会明显拖慢甚至卡死浏览器，
  //     因此节点多时只给度数最高的若干节点画文字标签 ===
  const labelCap = nodes.length > 1200 ? 120 : (nodes.length > 600 ? 260 : Infinity)
  const labelIds = labelCap === Infinity
    ? null
    : new Set([...nodes].sort((a, b) => (b._deg || 0) - (a._deg || 0))
        .slice(0, labelCap).map(n => n.id))
  const showLabel = (d) => !labelIds || labelIds.has(d.id)

  // === 连线（按关系类型着色，贝塞尔曲线）==========
  linkSel = gLinks
    .selectAll('path.link-line')
    .data(links, d => d.id || (d.source.id || d.source) + '|' + (d.target.id || d.target))
  linkSel.exit().remove()
  linkSel = linkSel.enter()
    .append('path')
    .attr('class', d => linkClass(d))
    .attr('fill', 'none')
    .attr('stroke', d => linkColor(d))
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke-dasharray', d => linkDashArray(d))
    .attr('stroke-linecap', 'round')
    .on('mouseover', onLinkHover)
    .on('mousemove', onLinkMove)
    .on('mouseout', onLinkOut)
    .merge(linkSel)
  linkSel
    .attr('class', d => linkClass(d))
    .attr('fill', 'none')
    .attr('stroke', d => linkColor(d))
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke-dasharray', d => linkDashArray(d))

  // === 节点 ==========
  nodeSel = gNodes.selectAll('g.node-group').data(nodes, d => d.id)
  nodeSel.exit().remove()
  const nodeEnter = nodeSel.enter()
    .append('g')
    .attr('class', 'node-group')
    .call(drag()
      .on('start', dragStart)
      .on('drag', dragDuring)
      .on('end', dragEnd)
    )
    .on('mouseover', onNodeHover)
    .on('mouseout', onNodeOut)
    .on('click', onNodeClick)
    .on('contextmenu', onNodeContextMenu)

  nodeEnter.append('path')
    .attr('class', 'node-shape')
    .attr('d', d => nodeShapePath(d, nodeRadius(d)))
    .attr('fill', d => nodeFill(d))
    .attr('stroke', d => nodeStroke(d))
    .attr('stroke-width', d => getLevelBorderWidth(d.level || 3))

  // 分组颜色指示环
  nodeEnter.append('circle')
    .attr('class', 'node-group-ring')
    .attr('r', d => nodeRadius(d) + 4)
    .attr('fill', 'none')
    .attr('stroke', d => groupColorForNode(d))
    .attr('stroke-width', 2.5)
    .attr('stroke-dasharray', d => groupColorForNode(d) === 'none' ? 'none' : '3,2')
    .style('opacity', d => groupColorForNode(d) === 'none' ? 0 : 0.7)

  // 校验状态指示器
  nodeEnter.append('circle')
    .attr('class', 'node-validation-indicator')
    .attr('r', 4)
    .attr('cx', d => nodeRadius(d) - 2)
    .attr('cy', d => -nodeRadius(d) + 2)
    .attr('fill', d => validationColor(d))
    .attr('stroke', 'var(--bg-primary)')
    .attr('stroke-width', 1)
    .style('opacity', d => validationColor(d) === 'none' ? 0 : 1)

  // 节点文字标签：大图谱只画度数最高的一批
  nodeEnter.filter(showLabel)
    .append('text')
    .attr('class', 'node-label')
    .attr('dy', d => nodeRadius(d) + 12)
    .style('font-size', d => labelFontSize(d))
    .style('fill', 'var(--text-secondary)')
    .text(d => d.title ? (d.title.length > 14 ? d.title.slice(0, 14) + '…' : d.title) : (d.id.slice(0, 8)))

  // 分组名标签（节点右上角小色块+名称）：大图谱下省略，避免噪声与开销
  nodeEnter.filter(d => !labelIds)
    .append('text')
    .attr('class', 'node-group-label')
    .attr('x', d => nodeRadius(d) + 2)
    .attr('y', d => -nodeRadius(d) - 2)
    .attr('font-size', '8px')
    .attr('fill', d => groupColorForNode(d))
    .attr('text-anchor', 'start')
    .attr('dy', '0.3em')
    .text(d => groupLabelForNode(d))
    .style('opacity', d => groupLabelForNode(d) ? 0.85 : 0)
    .style('pointer-events', 'none')

  nodeSel = nodeEnter.merge(nodeSel)
  nodeSel.select('path.node-shape')
    .attr('d', d => nodeShapePath(d, nodeRadius(d)))
    .attr('fill', d => nodeFill(d))
    .attr('stroke', d => nodeStroke(d))
    .attr('stroke-width', d => getLevelBorderWidth(d.level || 3))
  nodeSel.select('circle.node-group-ring')
    .attr('r', d => nodeRadius(d) + 4)
    .attr('stroke', d => groupColorForNode(d))
    .style('opacity', d => groupColorForNode(d) === 'none' ? 0 : 0.7)
  nodeSel.select('circle.node-validation-indicator')
    .attr('cx', d => nodeRadius(d) - 2)
    .attr('cy', d => -nodeRadius(d) + 2)
    .attr('fill', d => validationColor(d))
    .style('opacity', d => validationColor(d) === 'none' ? 0 : 1)
  nodeSel.select('text.node-label').text(d =>
    d.title
      ? (d.title.length > 14 ? d.title.slice(0, 14) + '…' : d.title)
      : d.id.slice(0, 8)
  )
    .style('font-size', d => labelFontSize(d))
    .style('fill', 'var(--text-secondary)')
  nodeSel.select('text.node-group-label')
    .attr('x', d => nodeRadius(d) + 2)
    .attr('y', d => -nodeRadius(d) - 2)
    .attr('fill', d => groupColorForNode(d))
    .text(d => groupLabelForNode(d))
    .style('opacity', d => groupLabelForNode(d) ? 0.85 : 0)
  nodeSel.classed('is-orphan', d => d._deg === 0)
  // 收养节点集合（语义桥接端点），同时用于样式与半透明填充
  const adoptedIds = new Set()
  for (const l of graphStore.links) {
    if (!l.semantic_bridge) continue
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    adoptedIds.add(s)
    adoptedIds.add(t)
  }
  for (const n of nodes) n._adopted = adoptedIds.has(n.id)
  nodeSel.classed('is-adopted', d => d._adopted)
  // 孤儿/收养节点：叠加半透明填充
  nodeSel.select('path.node-shape').style('fill-opacity', d => nodeFillOpacity(d))
  nodeSel.classed('dim', false)

  // === 启动仿真 ==========
  if (useProgressive) {
    // 渐进式：分 5 批加入节点
    simulation.nodes([])
    simulation.force('link').links([])
    const batchSize = Math.ceil(nodes.length / 5)
    for (let batch = 0; batch < 5; batch++) {
      const slice = nodes.slice(0, (batch + 1) * batchSize)
      const sliceLinks = links.filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source
        const t = typeof l.target === 'object' ? l.target.id : l.target
        return slice.some(n => n.id === s) && slice.some(n => n.id === t)
      })
      setTimeout(() => {
        simulation.nodes(slice)
        simulation.force('link').links(sliceLinks)
        simulation.alpha(0.6).restart()
      }, batch * 300)
    }
  } else {
    simulation.nodes(nodes)
    simulation.force('link').links(links)
    simulation.alpha(0.6).restart()
  }

  applyHighlight()
}

/* ========== 节点填充色（按类型渐变） ========== */
function nodeFill(d) {
  const f = graphStore.graphFilters
  if (f.colorMode === 'single') return 'url(#kgGradUser)'
  if (f.colorMode === 'folder') return folderColor(d.fileId)
  if (d.semantic_bridge) return 'url(#nodeGhost)'
  if (d._corpusNode || d.type === 'corpus' || d.type === 'kb') return 'url(#kgGradCorpus)'
  if (d.type === 'note') return 'url(#kgGradNote)'
  return 'url(#kgGradUser)'
}
/* 文件夹维度着色：对 fileId 求稳定哈希取 hue */
function folderColor(fileId) {
  if (!fileId) return '#8A9AA8'
  let hash = 0
  const s = String(fileId)
  for (let i = 0; i < s.length; i++) {
    hash = (hash * 31 + s.charCodeAt(i)) | 0
  }
  const hue = ((hash % 360) + 360) % 360
  return `hsl(${hue}, 55%, 55%)`
}
function nodeStroke(d) {
  if (d.semantic_bridge) return '#5a6582'
  if (d._corpusNode || d.type === 'corpus' || d.type === 'kb') return '#7A8A98'
  if (d.type === 'note') return '#B98D5C'
  return '#3D5A75'
}
/* 孤儿/收养节点半透明填充 */
function nodeFillOpacity(d) {
  if (d._deg === 0 || d._adopted) return 0.5
  return 1
}
/* 标签字号随节点半径自适应（10–14px） */
function labelFontSize(d) {
  const r = nodeRadius(d)
  return r >= 22 ? '13px' : r >= 15 ? '12px' : '11px'
}

/** 获取节点所属分组的颜色，默认分组不显示 */
function groupColorForNode(d) {
  if (!d.groupId || d.groupId === 'default') return 'none'
  const colorMap = groupStore.groupColorMap
  return colorMap[d.groupId] || 'none'
}

/** 获取节点分组名标签（非默认分组且非全部分组视图时显示） */
function groupLabelForNode(d) {
  if (!d.groupId || d.groupId === 'default') return ''
  if (d.groupName) return d.groupName.length > 6 ? d.groupName.slice(0, 6) + '…' : d.groupName
  const group = groupStore.groups.find(g => g.id === d.groupId)
  return group ? (group.name.length > 6 ? group.name.slice(0, 6) + '…' : group.name) : ''
}

/** 分组快速筛选 */
function onGroupFilterChange(groupId) {
  groupStore.switchGroup(groupId)
  graphStore.version++
  graphStore.restartTick++
}

/** 图谱样式面板：文件夹筛选（单选） */
function onFolderFilterChange(fileId) {
  graphStore.setGraphFilters({ folders: fileId ? [fileId] : [] })
}
/** 图谱样式面板：标签筛选（单选） */
function onTagFilterChange(tag) {
  graphStore.setGraphFilters({ tags: tag ? [tag] : [] })
}
/** 图谱样式面板：关系类型筛选（多选） */
function onRelationTypeToggle(relationType, checked) {
  const cur = [...graphStore.graphFilters.relationTypes]
  const idx = cur.indexOf(relationType)
  if (checked && idx === -1) cur.push(relationType)
  if (!checked && idx !== -1) cur.splice(idx, 1)
  graphStore.setGraphFilters({ relationTypes: cur })
}
/** 图谱样式面板：节点类型筛选（多选，user/kb/note） */
function onNodeTypeToggle(nodeType, checked) {
  const cur = [...graphStore.graphFilters.nodeTypes]
  const idx = cur.indexOf(nodeType)
  if (checked && idx === -1) cur.push(nodeType)
  if (!checked && idx !== -1) cur.splice(idx, 1)
  graphStore.setGraphFilters({ nodeTypes: cur })
}
/** 图谱样式面板：关联强度阈值筛选 */
function onMinScoreChange(val) {
  graphStore.setGraphFilters({ minScore: Number(val) || 0 })
}
/** 节点类别：user=用户/默认知识节点；kb=知识库/语料节点；note=笔记节点 */
function nodeCategory(d) {
  if (d.type === 'corpus' || d.type === 'kb') return 'kb'
  if (d.type === 'note') return 'note'
  return 'user'
}

/** 获取节点校验状态颜色 */
function validationColor(d) {
  if (!d.accuracyScore && !d.validationReport) return 'none'
  const vs = getNodeValidationStatus(d)
  return vs.color || 'none'
}

/**
 * 根据节点层级生成不同形状的路径
 * L1 元概念 → 六边形
 * L2 核心理论 → 圆角矩形
 * L3 具体技术 → 圆形
 * L4 实现/工具 → 菱形
 */
function nodeShapePath(d, r) {
  const level = d.level || 3
  switch (level) {
    case 1: { // 六边形
      const points = []
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6
        points.push([r * Math.cos(angle), r * Math.sin(angle)])
      }
      return 'M' + points.map(p => p.join(',')).join('L') + 'Z'
    }
    case 2: { // 圆角矩形
      const cr = r * 0.3
      return `M${-r + cr},${-r} h${2*r - 2*cr} a${cr},${cr} 0 0 1 ${cr},${cr}`
        + ` v${2*r - 2*cr} a${cr},${cr} 0 0 1 ${-cr},${cr}`
        + ` h${-2*r + 2*cr} a${cr},${cr} 0 0 1 ${-cr},${-cr}`
        + ` v${-2*r + 2*cr} a${cr},${cr} 0 0 1 ${cr},${-cr}Z`
    }
    case 4: { // 菱形
      return `M0,${-r} L${r},0 L0,${r} L${-r},0 Z`
    }
    default: { // 圆形 (L3)
      return `M0,${-r} A${r},${r} 0 1,1 0,${r} A${r},${r} 0 1,1 0,${-r}`
    }
  }
}

/* ========== 连线样式（按关系类型） ========== */
function linkClass(d) {
  let cls = 'link-line '
  // 隔离连线标记
  if (d._isolated) { cls += 'isolated-link'; return cls }
  if (d.semantic_bridge) cls += 'semantic-bridge'
  else if (d.source_type === 'cross_temporal') cls += 'cross-temporal'
  else if (d.relation_type === 'is_a') cls += 'rel-is-a'
  else if (d.relation_type === 'depends_on') cls += 'rel-depends'
  else if (d.relation_type === 'implements') cls += 'rel-implements'
  else if (d.relation_type === 'synonym') cls += 'rel-synonym'
  else if (d.relation_type === 'analogy') cls += 'rel-analogy'
  else if (cfg.corpusEnabled && (d.sources || []).includes('corpus_bridge')) cls += 'corpus-link'
  else cls += 'user-link'
  return cls
}

function linkColor(d) {
  if (d._isolated) return '#f87086'
  if (d.semantic_bridge) return '#6d7896'
  if (d.relation_color) return d.relation_color
  if (d.relation_type) return getRelationColor(d.relation_type)
  return 'rgba(79, 111, 143, 0.55)'
}

/* 贝塞尔曲线路径：轻微弧度，随距离自适应 */
function linkPath(d) {
  const sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
  const dx = tx - sx, dy = ty - sy
  const len = Math.hypot(dx, dy) || 1
  const off = Math.min(26, len * 0.12)
  const mx = (sx + tx) / 2 - (dy / len) * off
  const my = (sy + ty) / 2 + (dx / len) * off
  return `M${sx},${sy} Q${mx},${my} ${tx},${ty}`
}

/* 线宽与得分正比，clamp 1–4px */
function linkWidth(d) {
  const w = Math.max(0.05, d.score || 0.3)
  const base = 1 + w * 2.6
  // 按证据强度调整
  let width = base
  switch (d.evidence_level) {
    case 'strong': width = base * 1.2; break
    case 'medium': width = base; break
    case 'weak': width = base * 0.7; break
    case 'none': width = base * 0.4; break
  }
  return Math.max(1, Math.min(4, width))
}
/* 整体透明度 clamp 0.3–1（dim 语义由 CSS class 保留） */
function linkOpacity(d) {
  const w = Math.max(0.05, d.score || 0.3)
  const base = Math.max(0.35, Math.min(0.9, 0.35 + w * 0.55))
  let o = base
  switch (d.evidence_level) {
    case 'strong': o = base * 1.1; break
    case 'medium': o = base; break
    case 'weak': o = base * 0.65; break
    case 'none': o = base * 0.35; break
  }
  return Math.max(0.3, Math.min(1, o))
}

/* ========== 连线虚线样式 ========== */
function linkDashArray(d) {
  const style = d.relation_lineStyle || getRelationLineStyle(d.relation_type)
  if (style === 'dashed') return '8,4'
  if (style === 'dotted') return '3,3'
  if (style === 'double') return '1,2'
  if (style === 'red-block') return '12,4'
  if (d.semantic_bridge) return '6,4'
  // 弱证据/无证据使用虚线
  if (d.evidence_level === 'weak') return '5,5'
  if (d.evidence_level === 'none') return '3,7'
  return null
}

/* ========== Tooltip ========== */
function onLinkHover(ev, d) {
  const nodes = graphStore.nodes
  const sid = typeof d.source === 'object' ? d.source.id : d.source
  const tid = typeof d.target === 'object' ? d.target.id : d.target
  const sn = nodes.find(n => n.id === sid)
  const tn = nodes.find(n => n.id === tid)
  tooltip.value = {
    visible: true,
    x: ev.clientX + 14,
    y: ev.clientY + 14,
    data: d,
    source: sn,
    target: tn
  }
  select(ev.currentTarget).attr('stroke-opacity', 0.95).attr('stroke-width', linkWidth(d) + 1.5)
}
function onLinkMove(ev) {
  tooltip.value.x = ev.clientX + 14
  tooltip.value.y = ev.clientY + 14
}
function onLinkOut(ev) {
  tooltip.value.visible = false
  select(ev.currentTarget)
    .attr('stroke-opacity', function(d) { return linkOpacity(d) })
    .attr('stroke-width', function(d) { return linkWidth(d) })
}

/* ========== 节点交互 ========== */
function onNodeHover(ev, d) {
  if (highlightActive) return
  highlightActive = true
  highlightNodeId = d.id
  applyHighlight()
}
function onNodeOut() {
  if (!highlightActive) return
  highlightActive = false
  highlightNodeId = null
  applyHighlight()
}
function onNodeClick(ev, d) {
  ev.stopPropagation()
  // 打开节点详情抽屉
  const nodeLinks = graphStore.links.filter(l => {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    return s === d.id || t === d.id
  })
  drawer.value = {
    visible: true,
    node: d,
    links: nodeLinks
  }
}

function closeDrawer() {
  drawer.value.visible = false
}

// === 右键菜单 ===
function onNodeContextMenu(ev, d) {
  ev.preventDefault()
  ev.stopPropagation()
  contextMenu.value = {
    visible: true,
    x: ev.clientX,
    y: ev.clientY,
    nodeId: d.id
  }
}

function onContextMenuIsolate() {
  const sourceId = contextMenu.value.nodeId
  contextMenu.value.visible = false
  ElMessage.info('请点击图谱中的另一个节点以完成隔离设置')
  waitingForIsolateTarget = sourceId
}

function onContextMenuClose() {
  contextMenu.value.visible = false
}

let waitingForIsolateTarget = null

// 修改 onNodeClick 处理隔离目标选择
const originalOnNodeClick = onNodeClick
onNodeClick = function(ev, d) {
  if (waitingForIsolateTarget) {
    ev.stopPropagation()
    const sourceId = waitingForIsolateTarget
    waitingForIsolateTarget = null
    if (sourceId === d.id) {
      ElMessage.warning('不能与自身隔离')
      return
    }
    const res = graphStore.addIsolate(sourceId, d.id)
    if (res.ok) {
      ElMessage.success('已设置互相隔离，系统自动连线已移除')
    } else {
      ElMessage.error('隔离设置失败')
    }
    return
  }
  originalOnNodeClick(ev, d)
}

// 标记隔离节点对之间的连线
function markIsolatedLinks(links) {
  const pairs = graphStore.isolatedPairs
  const pairSet = new Set()
  for (const p of pairs) {
    pairSet.add(p.key)
  }
  for (const l of links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    const key = s < t ? s + '|' + t : t + '|' + s
    l._isolated = pairSet.has(key)
  }
}

function applyHighlight() {
  if (!gLinks || !gNodes) return
  if (!highlightActive || !highlightNodeId) {
    gLinks.selectAll('path.link-line').classed('dim', false)
    gNodes.selectAll('g.node-group').classed('dim', false)
    return
  }
  const nid = highlightNodeId
  const neighbors = new Set([nid])
  const activeLinks = new Set()
  for (const l of graphStore.links) {
    const s = typeof l.source === 'object' ? l.source.id : l.source
    const t = typeof l.target === 'object' ? l.target.id : l.target
    if (s === nid) { neighbors.add(t); activeLinks.add(l.id) }
    if (t === nid) { neighbors.add(s); activeLinks.add(l.id) }
  }
  gLinks.selectAll('path.link-line').classed('dim', d => !activeLinks.has(d.id))
  gNodes.selectAll('g.node-group').classed('dim', d => !neighbors.has(d.id))
}

/* ========== 拖拽 ========== */
function dragStart(ev, d) {
  if (!ev.active) simulation.alphaTarget(0.3).restart()
  d.fx = d.x
  d.fy = d.y
}
function dragDuring(ev, d) {
  d.fx = ev.x
  d.fy = ev.y
}
function dragEnd(ev, d) {
  if (!ev.active) simulation.alphaTarget(0)
  d.fx = null
  d.fy = null
}

/* ========== watch 触发热更新 ========== */
watch(() => graphStore.version, () => {
  render()
})
watch(() => graphStore.restartTick, () => {
  if (simulation) simulation.alpha(0.5).restart()
})
// 权重变化 → 重算连线粗细 / 透明度 / 颜色
watch(() => [cfg.w_alpha, cfg.w_beta, cfg.w_gamma, cfg.w_delta, cfg.threshold, cfg.corpusEnabled].join('|'), () => {
  if (!gLinks) return
  gLinks.selectAll('path.link-line')
    .attr('stroke-width', d => linkWidth(d))
    .attr('stroke-opacity', d => linkOpacity(d))
    .attr('stroke', d => linkColor(d))
    .attr('stroke-dasharray', d => linkDashArray(d))
    .attr('class', d => linkClass(d))
})
</script>

<style scoped>
/* 分组快速筛选 */
.canvas-group-filter {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 50;
}
.cfs-select {
  padding: 4px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 11px;
  cursor: pointer;
  outline: none;
  min-width: 160px;
}
.cfs-select:hover {
  border-color: var(--accent);
}
.cfs-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(91, 155, 243, 0.2);
}

/* 图谱样式面板（左上角浮动） */
.canvas-style-panel {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--bg-glass-strong);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  max-width: 260px;
}
.csp-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.csp-label {
  flex: 0 0 auto;
  min-width: 36px;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.csp-select {
  flex: 1 1 auto;
  min-width: 0;
  background: var(--bg-secondary);
}
.csp-rel-row {
  align-items: flex-start;
  flex-direction: column;
}
.csp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
}
.csp-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  cursor: pointer;
  transition: color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
  user-select: none;
}
.csp-chip input {
  display: none;
}
.csp-chip:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}
.csp-chip.is-active {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(91, 155, 243, 0.12);
}
.csp-range {
  flex: 1 1 auto;
  min-width: 0;
  accent-color: var(--accent);
  cursor: pointer;
}

/* ===== D3 生成元素（经 :deep 穿透 scoped 作用域） ===== */
/* 网格背景层不拦截交互 */
.canvas-wrap :deep(.kg-grid-bg) {
  pointer-events: none;
}
/* 节点 hover：放大 1.1 + 光晕（path 以节点中心为原点，scale 即放大） */
.canvas-wrap :deep(g.node-group path.node-shape) {
  transition: filter 0.18s var(--ease-out);
  stroke-linejoin: round;
}
.canvas-wrap :deep(g.node-group:hover path.node-shape) {
  transform: scale(1.1);
  filter: drop-shadow(0 2px 8px rgba(79, 111, 143, 0.5));
}
.canvas-wrap :deep(g.node-group:hover circle.node-group-ring) {
  opacity: 0.95;
}
/* 孤儿节点：虚线描边（对齐 main.css 原有语义） */
.canvas-wrap :deep(g.node-group.is-orphan path.node-shape) {
  stroke: var(--text-muted);
  stroke-dasharray: 3 3;
}
/* 收养节点：灰虚线描边 */
.canvas-wrap :deep(g.node-group.is-adopted path.node-shape) {
  stroke: #8a93b0;
  stroke-dasharray: 5 3;
  stroke-width: 2;
}
/* 连线可点击感 */
.canvas-wrap :deep(path.link-line) {
  cursor: pointer;
}

</style>