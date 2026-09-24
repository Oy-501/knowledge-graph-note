/**
 * index.js
 * 插件系统入口：副作用导入内置插件即可完成注册。
 * 宿主（ControlPanel）通过 `import '@/plugins'` 引入，随后调用 activatePlugins()。
 */

import './builtin/export-graph'
import './builtin/notes-stats'
