/**
 * 时间文案格式化（全项目统一实现）
 * formatAgo：列表类场景（刚刚 / N分钟前 / N小时前 / N 天前 / 具体日期）
 * formatDay：回顾 / 时间线场景（今天 / N 天前 / M月D日 / N年M月）
 */

export function formatAgo(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + ' 天前'
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
    + ' '
    + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function formatDay(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 86400000) return '今天'
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + ' 天前'
  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getMonth() + 1}月${d.getDate()}日`
  }
  return `${d.getFullYear()}年${d.getMonth() + 1}月`
}
