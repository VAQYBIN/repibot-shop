'use client'

import { detectLanguage, type Language } from '@repibot/core'
import {
  createContext,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useCallback,
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
  // До определения JS тема остаётся без атрибута: первый paint выбирает CSS
  // media fallback, поэтому dark-система не получает промежуточный light-кадр.
  const [language, setLanguage] = useState<Language>('ru')
  const [resolvedTheme, setResolvedTheme] = useState<Theme | null>(null)

  useEffect(() => {
    setLanguage(detectLanguage(navigator.languages ?? [navigator.language]))
  }, [])

  useEffect(() => {
    const preference = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (preference === undefined) return

    const syncTheme = () => setResolvedTheme(preference.matches ? 'dark' : 'light')
    syncTheme()
    preference.addEventListener('change', syncTheme)
    return () => preference.removeEventListener('change', syncTheme)
  }, [])

  useEffect(() => {
    if (resolvedTheme !== null) document.documentElement.dataset.theme = resolvedTheme
  }, [resolvedTheme])

  const setTheme: Dispatch<SetStateAction<Theme>> = useCallback((next) => {
    setResolvedTheme((current) => {
      const theme = current ?? 'light'
      return typeof next === 'function' ? next(theme) : next
    })
  }, [])
  const theme = resolvedTheme ?? 'light'
  const value = useMemo(() => ({ language, theme, setTheme }), [language, setTheme, theme])
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
