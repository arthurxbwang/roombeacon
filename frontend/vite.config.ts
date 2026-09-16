import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  server: { proxy: { '/api': 'http://127.0.0.1:8088' } },
  build: { rollupOptions: { input: {
    main: resolve(__dirname, 'index.html'),
    roomDisplay: resolve(__dirname, 'room-display.html'),
  } } },
})
