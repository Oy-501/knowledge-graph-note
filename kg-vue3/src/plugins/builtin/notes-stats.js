/**
 * notes-stats.js 内置插件「笔记统计」
 */
import { ElMessage } from 'element-plus'
import { registerPlugin } from '../registry'

registerPlugin({
  id: 'notes-stats',
  name: '笔记统计',
  description: '统计当前所有笔记的数量与总字数',
  activate(api) {
    api.registerCommand('统计笔记字数', () => {
      const noteStore = api.getContext().noteStore
      const notes = noteStore?.notes || []
      let totalChars = 0
      for (const n of notes) totalChars += (n.content || '').length
      ElMessage.success(`共 ${notes.length} 篇笔记 · 总字数 ${totalChars}`)
    })
  }
})
