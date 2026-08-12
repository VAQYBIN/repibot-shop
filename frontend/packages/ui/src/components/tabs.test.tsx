import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs'

function Periods() {
  return (
    <Tabs defaultValue="today">
      <TabsList aria-label="Период">
        <TabsTrigger value="today">Сегодня</TabsTrigger>
        <TabsTrigger value="week">Неделя</TabsTrigger>
      </TabsList>
      <TabsContent value="today">1 240 ₽</TabsContent>
      <TabsContent value="week">8 700 ₽</TabsContent>
    </Tabs>
  )
}

describe('Tabs', () => {
  it('показывает содержимое выбранной вкладки', () => {
    render(<Periods />)

    expect(screen.getByRole('tab', { name: 'Сегодня', selected: true })).toBeInTheDocument()
    expect(screen.getByText('1 240 ₽')).toBeInTheDocument()
  })

  it('переключается нажатием', async () => {
    render(<Periods />)

    await userEvent.click(screen.getByRole('tab', { name: 'Неделя' }))

    expect(screen.getByText('8 700 ₽')).toBeInTheDocument()
  })

  it('переключается стрелками', async () => {
    /* Ради этого и взят Radix: блуждающий фокус по списку вкладок руками
       пишется долго и почти всегда с ошибкой в краевом случае. */
    render(<Periods />)
    await userEvent.click(screen.getByRole('tab', { name: 'Сегодня' }))

    await userEvent.keyboard('{ArrowRight}')

    expect(screen.getByRole('tab', { name: 'Неделя', selected: true })).toBeInTheDocument()
  })
})
