/**
 * registry.js 轻量级插件系统：插件注册表 + 插件 API
 */
import { reactive } from 'vue'
import { logError } from '@/utils/resilience'

const context = { graphStore: null, noteStore: null, fileStore: null }

export const plugins = reactive([])

export function setPluginContext(ctx) { Object.assign(context, ctx) }

export function registerPlugin(def) {
  if (!def || !def.id) return
  if (plugins.some(p => p.id === def.id)) return
  plugins.push({ id: def.id, name: def.name || def.id, description: def.description || '', enabled: true, activated: false, exports: [], commands: [], activate: def.activate })
}

export function createPluginAPI(id) {
  return {
    registerExportFormat(label, fn) { const plugin = plugins.find(p => p.id === id); if (plugin && typeof fn === 'function') plugin.exports.push({ label, fn }) },
    registerCommand(label, fn) { const plugin = plugins.find(p => p.id === id); if (plugin && typeof fn === 'function') plugin.commands.push({ label, fn }) },
    getContext: () => context
  }
}

export function activatePlugins() {
  for (const p of plugins) {
    if (!p.enabled || p.activated || typeof p.activate !== 'function') continue
    try { p.activate(createPluginAPI(p.id)); p.activated = true } catch (e) { logError('plugin:' + p.id, 'activatePlugins', e) }
  }
}
