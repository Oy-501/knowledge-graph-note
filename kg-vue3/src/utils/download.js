/**
 * 浏览器端文本下载唯一实现
 * 供学习路径导出（learningPath）、图谱导出插件（export-graph）、笔记导出（NoteManageView）复用
 */
export function downloadText(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
