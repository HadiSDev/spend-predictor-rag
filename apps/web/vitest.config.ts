import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import viteReact from '@vitejs/plugin-react'

const src = fileURLToPath(new URL('./src', import.meta.url))

export default defineConfig({
  plugins: [viteReact()],
  resolve: { alias: { '#': src, '@': src } },
  test: {
    environment: 'jsdom',
    globals: true,
    css: false,
  },
})
