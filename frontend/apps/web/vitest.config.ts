import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  // Псевдоним «@» описан в tsconfig, но Vite его оттуда не читает: без этой
  // строки тесты не находят модули, которые Next собирает без нареканий.
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // И .ts тоже: разметки в тестах хелперов нет, а без второго расширения
    // такой файл молча не запускается — падение показалось бы «зелёным».
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
