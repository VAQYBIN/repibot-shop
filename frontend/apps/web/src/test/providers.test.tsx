import { describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from './providers'

describe('renderWithProviders', () => {
  it('восстанавливает fetch при размонтировании тестового дерева', () => {
    vi.unstubAllGlobals()
    const originalFetch = globalThis.fetch

    const view = renderWithProviders(<div />)
    expect(globalThis.fetch).not.toBe(originalFetch)

    view.unmount()
    expect(globalThis.fetch).toBe(originalFetch)
  })
})
