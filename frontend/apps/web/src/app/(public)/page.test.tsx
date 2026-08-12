import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useBrowserPreferences } from '@/lib/browser-preferences'
import { renderWithProviders } from '@/test/providers'
import HomePage from './page'

function DetectedLanguage() {
  const { language } = useBrowserPreferences()
  return <output aria-label="detected language">{language}</output>
}

afterEach(() => {
  document.documentElement.lang = 'ru'
})

describe('главная страница', () => {
  it('не помечает статический русский текст как английский', async () => {
    vi.stubGlobal('navigator', {
      ...navigator,
      languages: ['en-US', 'en'],
      language: 'en-US',
    })
    document.documentElement.lang = 'ru'

    renderWithProviders(
      <>
        <HomePage />
        <DetectedLanguage />
      </>,
    )

    expect(await screen.findByText('Магазин ещё готовится')).toBeVisible()
    expect(await screen.findByLabelText('detected language')).toHaveTextContent('en')
    expect(document.documentElement.lang).toBe('ru')
  })
})
