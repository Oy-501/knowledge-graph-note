/**
 * registry.js
 * 轻量级插件系统：插件注册表 + 插件 API
 *
 * 设计目标：
 *  - 最小可用：一个 reactive 插件列表 + 极简注册/激活流程
 *  - 能力扩展：插件通过 activate(api) 注册「导出格式」与「命令」
 *  - 松耦合：插件通过 getContext() 访问各 Pinia store，不直接 import
 */

import { reactive } from 'vue'
import { logError } from '@/utils/resilience'

/**
 * 插件运行上下文（由宿主在 onMounted 时注入）
 * graphStore / noteStore / fileStore 均为 Pinia store 实例
 */
const context = {
  graphStore: null,
  noteStore: null,
  fileStore: null
}

/**
 * 已注册插件列表（响应式，供 ControlPanel 渲染）
 * 每项结构：
 *   { id, name, description, enabled, activated, exports: [{label, fn}], commands: [{label, fn}], activate }
 */
export const plugins = reactive([])

/**
 * 注入插件运行上下文（合并而非替换，便于渐进补全）
 */
export function setPluginContext(ctx) {
  Object.assign(context, ctx)
}

/**
 * 注册一个插件定义
 * def = { id, name, description, activate }
 * 同 id 已存在则跳过（幂等，避免热更新重复注册）
 */
export function registerPlugin(def) {
  if (!def || !def.id) return
  if (plugins.some(p => p.id === def.id)) return

  plugins.push({
    id: def.id,
    name: def.name || def.id,
    description: def.description || '',
    enabled: true,
    activated: false,
    exports: [],
    commands: [],
    activate: def.activate
  })
}

/**
 * 创建某插件的 API 句柄
 * registerExportFormat / registerCommand 把 {label, fn} 挂到对应插件的数组上
 */
export function createPluginAPI(id) {
  return {
    registerExportFormat(label, fn) {
      const plugin = plugins.find(p => p.id === id)
      if (plugin && typeof fn === 'function') {
        plugin.exports.push({ label, fn })
      }
    },
    registerCommand(label, fn) {
      const plugin = plugins.find(p => p.id === id)
      if (plugin && typeof fn === 'function') {
        plugin.commands.push({ label, fn })
      }
    },
    getContext: () => context
  }
}

/**
 * 激活所有已启用且带 activate 的插件
 * 幂等：已成功激活的插件跳过（activated 标记），防止 exports/commands 重复累积；
 * 单个插件激活失败不阻断其它插件
 */
export function activatePlugins() {
  for (const p of plugins) {
    if (!p.enabled || p.activated || typeof p.activate !== 'function') continue
    try {
      p.activate(createPluginAPI(p.id))
      p.activated = true
    } catch (e) {
      logError('plugin:' + p.id, 'activatePlugins', e)
    }
  }
}
