import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  // Приложение отдаётся Nginx по пути /app, а не с корня домена.
  base: '/app/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: 'dist',
    sourcemap: true,
    /**
     * Шрифты никогда не вшиваются в CSS.
     *
     * Мелкие подмножества Inter укладывались в порог встраивания и уезжали
     * в `data:`-адреса, а политика безопасности MiniApp разрешает шрифты
     * только со своего домена (`font-src 'self'`). Браузер их молча отбрасывал,
     * и часть глифов набиралась системной гарнитурой вместо фирменной —
     * заметить это на глаз почти невозможно, поймал сквозной обход экранов.
     *
     * Ослаблять политику ради встраивания неправильно: отдельными файлами
     * шрифты ещё и кэшируются между сборками.
     */
    assetsInlineLimit: (filePath) => (/\.(woff2?|ttf|otf|eot)$/.test(filePath) ? false : undefined),
  },
})
