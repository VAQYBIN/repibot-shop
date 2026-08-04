import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Приложение отдаётся Nginx по пути /app, а не с корня домена.
  base: '/app/',
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', sourcemap: true },
})
