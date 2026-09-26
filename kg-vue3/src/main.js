import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPersist from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import './styles/main.css'
// 素材层：真实纹理与摄影背景（来源与许可证见 src/assets/CREDITS.md）
import './styles/texture.css' // 注释此行即可去掉所有素材，回到纯令牌视觉
import './styles/ai-ui.css' // AI 交互增强层（悬停/聚焦/过渡/动效），注释此行即可整体回退
import { reportClientError, installGlobalErrorHooks } from './utils/errorReporter'

const app = createApp(App)

// ============================================================
// 全局错误兜底（防御机制第 4 层：前端）
// ------------------------------------------------------------
// 没有这一层时，任何组件渲染/生命周期里的异常都会中断整棵组件树的更新，
// 用户看到的是「白屏 + 控制台红字」，而且现场（组件名、生命周期阶段）
// 一旦刷新就没了。这里做三件事：
//   1. 兜住 Vue 组件内异常 → 标注组件与阶段 → 上报后端（后台可查）
//   2. 兜住非组件异常（window.onerror / unhandledrejection）
//   3. 上报失败绝不影响渲染（reportClientError 内部静默）
// ============================================================
app.config.errorHandler = (err, instance, info) => {
  const name = instance?.$options?.name
    || instance?.$options?.__name
    || instance?.$?.type?.name
    || '(匿名组件)'
  reportClientError({
    message: err?.message || String(err),
    stack: err?.stack || '',
    source: 'vue',
    component: name,
    info
  })
  // 仍然打一份到控制台，便于本地调试
  console.error(`[Vue] ${name} 在 ${info} 阶段抛错:`, err)
}

// 开发期把 Vue 警告也收进来（生产构建时该分支会被摇掉）
if (import.meta.env.DEV) {
  app.config.warnHandler = (msg, instance, trace) => {
    console.warn(`[Vue warn] ${msg}${trace || ''}`)
  }
}

installGlobalErrorHooks()

const pinia = createPinia()
pinia.use(piniaPersist)
app.use(pinia)
app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
