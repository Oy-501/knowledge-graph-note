import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    open: true,
  },
  optimizeDeps: {
    // transformers.js 需要跳过预构建（包含 WASM）
    exclude: ['@xenova/transformers'],
  },
  // 允许加载 .md 文件作为文本
  assetsInclude: ['**/*.md'],
})
