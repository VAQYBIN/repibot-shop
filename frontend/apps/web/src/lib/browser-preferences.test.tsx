import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ThemeToggle } from '@/components/theme-toggle'
import { BrowserPreferencesProvider } from './browser-preferences'

function systemTheme(initial: boolean) {
  let matches = initial
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const addEventListener = vi.fn(
    (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
  )
  const removeEventListener = vi.fn(
    (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    },
  )
  const preference = {
    get matches() {
      return matches
    },
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener,
    removeEventListener,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList

  return {
    preference,
    addEventListener,
    removeEventListener,
    set(next: boolean) {
      matches = next
      const event = { matches: next, media: preference.media } as MediaQueryListEvent
      for (const listener of listeners) listener(event)
    },
  }
}

afterEach(() => {
  document.documentElement.removeAttribute('data-theme')
})

describe('browser preferences', () => {
  it('не записывает промежуточную light-тему при холодной dark-загрузке', async () => {
    const system = systemTheme(true)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => system.preference),
    )
    document.documentElement.removeAttribute('data-theme')
    const mutations: MutationRecord[] = []
    const observer = new MutationObserver((records) => mutations.push(...records))
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
      attributeOldValue: true,
    })

    render(
      <BrowserPreferencesProvider>
        <div />
      </BrowserPreferencesProvider>,
    )
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    await Promise.resolve()
    observer.disconnect()

    expect(mutations.some((mutation) => mutation.oldValue === 'light')).toBe(false)
  })

  it('сохраняет единый state для системной смены и ручного переключателя', async () => {
    const system = systemTheme(true)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => system.preference),
    )

    render(
      <BrowserPreferencesProvider>
        <ThemeToggle />
      </BrowserPreferencesProvider>,
    )
    expect(await screen.findByRole('button', { name: 'Светлая тема' })).toBeVisible()

    act(() => system.set(false))
    expect(await screen.findByRole('button', { name: 'Тёмная тема' })).toBeVisible()
    expect(document.documentElement.dataset.theme).toBe('light')

    fireEvent.click(screen.getByRole('button', { name: 'Тёмная тема' }))
    expect(await screen.findByRole('button', { name: 'Светлая тема' })).toBeVisible()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('снимает media listener при размонтировании', () => {
    const system = systemTheme(false)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => system.preference),
    )

    const view = render(
      <BrowserPreferencesProvider>
        <div />
      </BrowserPreferencesProvider>,
    )
    const listener = system.addEventListener.mock.calls[0]?.[1]
    expect(listener).toBeDefined()

    view.unmount()
    expect(system.removeEventListener).toHaveBeenCalledWith('change', listener)
  })
})
