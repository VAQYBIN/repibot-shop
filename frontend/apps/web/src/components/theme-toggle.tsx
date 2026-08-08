'use client'

import { Button } from '@repibot/ui'

import { useBrowserPreferences } from '@/lib/browser-preferences'

export function ThemeToggle() {
  const { theme, setTheme } = useBrowserPreferences()

  return (
    <Button
      variant="secondary"
      size="md"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
    >
      {theme === 'light' ? 'Тёмная тема' : 'Светлая тема'}
    </Button>
  )
}
