/**
 * 图谱通用小工具
 * 连线端点可能是节点对象或 id 字符串，全项目此前散落 11 处解析逻辑，统一收口
 */
export function endpointId(ref) {
  if (ref == null) return null
  return typeof ref === 'object' ? ref.id : ref
}

/**
 * 节点度数（无向）
 * @param {string|object} nodeRef 节点 id 或节点对象
 * @param {Array} links 连线数组
 */
export function degreeOf(nodeRef, links) {
  const id = endpointId(nodeRef)
  if (id == null) return 0
  let d = 0
  for (const l of links || []) {
    if (endpointId(l.source) === id || endpointId(l.target) === id) d++
  }
  return d
}
