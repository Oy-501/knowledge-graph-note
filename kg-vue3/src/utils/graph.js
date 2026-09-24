/**
 * 图谱通用小工具
 */
export function endpointId(ref) {
  if (ref == null) return null
  return typeof ref === 'object' ? ref.id : ref
}

export function degreeOf(nodeRef, links) {
  const id = endpointId(nodeRef)
  if (id == null) return 0
  let d = 0
  for (const l of links || []) { if (endpointId(l.source) === id || endpointId(l.target) === id) d++ }
  return d
}
