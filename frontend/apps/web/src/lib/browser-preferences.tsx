'use client'

import { detectLanguage, type Language } from '@repibot/core'
import {
  createContext,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

export type Theme = 'light' | 'dark'

interface BrowserPreferences {
  language: Language
  theme: Theme
  setTheme: Dispatch<SetStateAction<Theme>>
}

const BrowserPreferencesContext = createContext<BrowserPreferences | null>(null)

export function BrowserPreferencesProvider({ children }: { children: ReactNode }) {
  // Серверный fallback совпадает с атрибутами root layout и первым кадром.
  const [language, setLanguage] = useState<Language>('ru')
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    setLanguage(detectLanguage(navigator.languages ?? [navigator.language]))
  }, [])

  useEffect(() => {
    const preference = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (preference === undefined) return

    const syncTheme = () => setTheme(preference.matches ? 'dark' : 'light')
    syncTheme()
    preference.addEventListener('change', syncTheme)
    return () => preference.removeEventListener('change', syncTheme)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const value = useMemo(() => ({ language, theme, setTheme }), [language, theme])
  return (
    <BrowserPreferencesContext.Provider value={value}>
      {children}
    </BrowserPreferencesContext.Provider>
  )
}

export function useBrowserPreferences(): BrowserPreferences {
  const preferences = useContext(BrowserPreferencesContext)
  if (preferences === null) throw new Error('BrowserPreferencesProvider не подключён')
  return preferences
}
