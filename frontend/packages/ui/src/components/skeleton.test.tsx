import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Skeleton } from './skeleton'

describe('Skeleton', () => {
  it('от скринридера скрыт', () => {
    /* Заглушка не содержит сведений. Объявлять её вслух — значит читать
       человеку пустоту; о загрузке сообщает Spinner или role=status рядом. */
    const { container } = render(<Skeleton />)

    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('принимает форму снаружи', () => {
    const { container } = render(<Skeleton className="h-10 w-full" />)
    const classes = container.firstElementChild?.className.split(' ') ?? []

    expect(classes).toContain('h-10')
    expect(classes).toContain('w-full')
  })
})
