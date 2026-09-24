/**
 * export-graph.js 内置插件「知识图谱导出」
 */
import { registerPlugin } from '../registry'
import { downloadText } from '@/utils/download'
import { endpointId } from '@/utils/graph'

function buildMarkdown(nodes, links) {
  const lines = []
  lines.push('# 知识图谱导出')
  lines.push('')
  lines.push('> 导出时间：' + new Date().toISOString())
  lines.push('')
  lines.push('## 节点清单（' + nodes.length + '）')
  lines.push('')
  if (nodes.length) {
    lines.push('| 标题 | 类型 | 分组 | 描述 |')
    lines.push('| --- | --- | --- | --- |')
    for (const n of nodes) {
      const title = (n.title || '').replace(/\|/g, '\\|')
      const desc = (n.description || '').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
      lines.push(`| ${title} | ${n.type || ''} | ${n.groupName || n.groupId || ''} | ${desc} |`)
    }
  } else lines.push('_暂无节点_')
  lines.push('')
  lines.push('## 连线清单（' + links.length + '）')
  lines.push('')
  if (links.length) {
    lines.push('| 源节点 | 关系 | 目标节点 |')
    lines.push('| --- | --- | --- |')
    for (const l of links) {
      const s = endpointId(l.source); const t = endpointId(l.target)
      const label = l.relation_label || l.relation_type || '关联'
      lines.push(`| ${s} | ${label} | ${t} |`)
    }
  } else lines.push('_暂无连线_')
  return lines.join('\n')
}

registerPlugin({
  id: 'export-graph',
  name: '知识图谱导出',
  description: '将当前知识图谱导出为 JSON 或 Markdown 文件',
  activate(api) {
    api.registerExportFormat('导出 JSON', () => {
      const graphStore = api.getContext().graphStore
      if (!graphStore) return
      downloadText('knowledge-graph.json', JSON.stringify({ nodes: graphStore.nodes, links: graphStore.links, exportedAt: new Date().toISOString() }, null, 2), 'application/json')
    })
    api.registerExportFormat('导出 Markdown', () => {
      const graphStore = api.getContext().graphStore
      if (!graphStore) return
      const md = buildMarkdown(graphStore.nodes || [], graphStore.links || [])
      downloadText('knowledge-graph.md', md, 'text/markdown')
    })
  }
})
