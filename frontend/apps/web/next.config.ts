import type { NextConfig } from 'next'

const config: NextConfig = {
  // standalone нужен образу: он забирает только необходимое,
  // а не весь node_modules размером в сотни мегабайт.
  output: 'standalone',
  transpilePackages: ['@repibot/ui', '@repibot/core'],
}

export default config
