import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { type Subscription, SubscriptionCard } from './subscription-card'

const BASE: Subscription = {
  plan_code: 'month',
  plan_name: { ru: 'Месяц', en: 'Month' },
  status: 'active',
  started_at: '2026-08-01T00:00:00Z',
  expires_at: '2026-09-01T00:00:00Z',
  subscription_url: null,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
}

describe('SubscriptionCard', () => {
  it('показывает название тарифа заголовком раздела', () => {
    render(<SubscriptionCard subscription={BASE} language="ru" />)

    expect(screen.getByRole('heading', { name: 'Месяц' })).toBeInTheDocument()
  })

  it('истёкшая подписка не выглядит так же, как действующая', () => {
    /* До правки оба состояния были набраны одним акцентным цветом и
       отличались только словом. */
    const { container: active } = render(<SubscriptionCard subscription={BASE} language="ru" />)
    const { container: expired } = render(
      <SubscriptionCard subscription={{ ...BASE, status: 'expired' }} language="ru" />,
    )

    const tone = (root: HTMLElement) =>
      root.querySelector('span.inline-flex.rounded-full')?.className ?? ''
    expect(tone(active)).not.toBe(tone(expired))
  })
})
