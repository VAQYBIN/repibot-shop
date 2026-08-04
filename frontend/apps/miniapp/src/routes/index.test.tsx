import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Home } from './index'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('главная MiniApp', () => {
  it('показывает название и подзаголовок', () => {
    render(<Home />)

    expect(screen.getByRole('heading', { name: 'Re:Pibot' })).toBeInTheDocument()
    expect(screen.getByText('Магазин ещё готовится')).toBeInTheDocument()
  })

  it('сообщает, что открыт вне Telegram, когда SDK недоступен', () => {
    render(<Home />)

    expect(screen.getByText('Telegram: вне приложения')).toBeInTheDocument()
  })

  it('сообщает о подключении, когда initData получен', () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'query_id=AAA' } })

    render(<Home />)

    expect(screen.getByText('Telegram: подключён')).toBeInTheDocument()
  })
})
