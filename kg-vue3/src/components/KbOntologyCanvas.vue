<template>
  <div ref="wrapRef" class="kb-onto" :style="{ height: height + 'px' }">
    <svg ref="svgRef" class="kb-onto-svg"></svg>
    <div v-if="!nodes.length" class="kb-onto-empty">暂无可展示的知识点</div>
    <div v-if="hovered" class="kb-onto-tip" :style="tipStyle">
      <div class="kt-title">{{ hovered.entity }}</div>
      <div class="kt-meta">
        {{ hovered.domain || 'general' }} · L{{ hovered.level }}
        <span v-if="hovered.degree"> · 连接 {{ hovered.degree }}</span>
      </div>
      <div class="kt-def">{{ hovered.definition || '（知识库暂无定义）' }}</div>
    </div>
  </div>
</template>

<script setup>
/**
 * KbOntologyCanvas.vue
 * 知识库本体图：把知识库自身当作一张图渲染（知识点 + 知识库关系边）。
 * 与图谱视图的区别：这里画的是「知识库」，不是用户笔记。
 */
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import * as d3Force from 'd3-force'
import { select } from 'd3-selection'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  links: { type: Array, default: () => [] },
  height: { type: Number, default: 360 },
  colorMode: { type: String, default: 'domain' } // domain | level
})

const wrapRef = ref(null)
const svgRef = ref(null)
const hovered = ref(null)
const tipPos = ref({ x: 0, y: 0 })
let simulation = null

const tipStyle = computed(() => ({
  left: `${tipPos.value.x + 12}px`,
  top: `${tipPos.value.y + 8}px`
}))

const DOMAIN_COLORS = ['#4F6F8F', '#7CB8A0', '#D4A574', '#9C7BB8', '#5E9CB8', '#B87B7B', '#7BA85E', '#8F7B4F']
const LEVEL_COLORS = { 1: '#4F6F8F', 2: '#7CB8A0', 3: '#D4A574', 4: '#9C7BB8' }

const domainOf = (node) => node.domain || 'general'
const domainColor = (node) => {
  const name = domainOf(node)
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) % 997
  return DOMAIN_COLORS[hash % DOMAIN_COLORS.length]
}

function nodeColor(node) {
  if (props.colorMode === 'level') return LEVEL_COLORS[node.level] || '#9AA7B5'
  return domainColor(node)
}

function nodeRadius(node) {
  const degree = node.degree || 0
  return Math.min(16, 5 + Math.sqrt(degree) * 1.6)
}

function render() {
  const wrap = wrapRef.value
  const svg = svgRef.value
  if (!wrap || !svg) return

  const width = wrap.clientWidth || 640
  const height = props.height
  const sel = select(svg)
  sel.selectAll('*').remove()
  sel.attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height)

  if (!props.nodes.length) return

  // 度数（没有被后端算过时前端兜底）
  const degreeMap = {}
  for (const l of props.links) {
    degreeMap[l.source] = (degreeMap[l.source] || 0) + 1
    degreeMap[l.target] = (degreeMap[l.target] || 0) + 1
  }
  const nodes = props.nodes.map(n => ({ ...n, degree: n.degree || degreeMap[n.id] || 0 }))
  const ids = new Set(nodes.map(n => n.id))
  const links = props.links
    .filter(l => ids.has(l.source) && ids.has(l.target))
    .map(l => ({ ...l, source: l.source, target: l.target }))

  const defs = sel.append('defs')
  defs.append('marker')
    .attr('id', 'kb-arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 14)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', 'var(--text-muted)')
    .attr('opacity', 0.5)

  const root = sel.append('g')

  const linkSel = root.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', 'var(--border)')
    .attr('stroke-width', d => 0.6 + Math.min(1.6, (d.weight || 0.5) * 1.6))
    .attr('stroke-dasharray', d => (d.origin === 'derived' ? '3 3' : null))
    .attr('marker-end', 'url(#kb-arrow)')

  const nodeSel = root.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('r', nodeRadius)
    .attr('fill', nodeColor)
    .attr('fill-opacity', d => (d.isolated ? 0.35 : 0.9))
    .attr('stroke', d => (d.isolated ? 'var(--text-muted)' : 'var(--bg-secondary)'))
    .attr('stroke-width', 1.2)
    .style('cursor', 'pointer')

  const labelSel = root.append('g')
    .selectAll('text')
    .data(nodes.filter(n => n.degree > 0).slice(0, 80))
    .join('text')
    .text(d => d.entity)
    .attr('font-size', 9.5)
    .attr('fill', 'var(--text-secondary)')
    .attr('text-anchor', 'middle')
    .attr('dy', d => -nodeRadius(d) - 3)
    .style('pointer-events', 'none')

  nodeSel
    .on('mouseenter', (event, d) => {
      hovered.value = d
      const rect = wrap.getBoundingClientRect()
      tipPos.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    })
    .on('mousemove', (event) => {
      const rect = wrap.getBoundingClientRect()
      tipPos.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    })
    .on('mouseleave', () => { hovered.value = null })

  simulation?.stop()
  simulation = d3Force.forceSimulation(nodes)
    .force('link', d3Force.forceLink(links).id(d => d.id).distance(58).strength(0.35))
    .force('charge', d3Force.forceManyBody().strength(-110))
    .force('center', d3Force.forceCenter(width / 2, height / 2))
    .force('collide', d3Force.forceCollide().radius(d => nodeRadius(d) + 6))
    .on('tick', () => {
      linkSel
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      nodeSel.attr('cx', d => d.x).attr('cy', d => d.y)
      labelSel.attr('x', d => d.x).attr('y', d => d.y)
    })
}

function onResize() {
  render()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  simulation?.stop()
  window.removeEventListener('resize', onResize)
})

watch(() => [props.nodes, props.links, props.colorMode], render, { deep: true })
</script>

<style scoped>
.kb-onto {
  position: relative;
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  overflow: hidden;
}
.kb-onto-svg { display: block; }
.kb-onto-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}
.kb-onto-tip {
  position: absolute;
  z-index: 5;
  max-width: 260px;
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  pointer-events: none;
}
.kt-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.kt-meta { font-size: 11px; color: var(--text-muted); margin: 2px 0 4px; }
.kt-def { font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; }
</style>
