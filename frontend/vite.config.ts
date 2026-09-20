import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

const release = process.env.ROOMBEACON_WEB_RELEASE || randomUUID()
if (!/^[A-Za-z0-9._-]{1,100}$/.test(release)) throw new Error('Invalid ROOMBEACON_WEB_RELEASE')

export default defineConfig({
  plugins: [vue(), { name: 'roombeacon-release', transformIndexHtml: () => [
    { tag: 'meta', attrs: { name: 'roombeacon-release', content: release }, injectTo: 'head' },
  ] }],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  server: { proxy: { '/api': 'http://127.0.0.1:8088' } },
  build: { target: 'chrome106', cssTarget: 'chrome106', rollupOptions: { input: {
    main: resolve(__dirname, 'index.html'),
    roomDisplay: resolve(__dirname, 'room-display.html'),
  } } },
})
