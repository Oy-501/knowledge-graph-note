import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    strictPort: false,
    fs: { strict: false }
  },
  optimizeDeps: {
    include: ['d3-selection', 'd3-force', 'd3-zoom', 'd3-drag'],
    exclude: ['@xenova/transformers']
  },
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 4096,
    rollupOptions: {
      output: {
        manualChunks: {
          d3: ['d3-selection', 'd3-force', 'd3-zoom', 'd3-drag'],
          vendor: ['vue', 'pinia', 'axios', '@vueuse/core']
        }
      }
    }
  }
})
