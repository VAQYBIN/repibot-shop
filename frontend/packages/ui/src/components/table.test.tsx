import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from './table'

function Payments() {
  return (
    <Table caption="Платежи">
      <TableHead>
        <TableRow>
          <TableHeaderCell>Дата</TableHeaderCell>
          <TableHeaderCell>Сумма</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow>
          <TableCell>12 августа</TableCell>
          <TableCell>199 ₽</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  )
}

describe('Table', () => {
  it('остаётся настоящей таблицей с подписью', () => {
    render(<Payments />)

    expect(screen.getByRole('table', { name: 'Платежи' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Дата' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '199 ₽' })).toBeInTheDocument()
  })

  it('ездит вбок внутри себя, а не таскает страницу', () => {
    /* Горизонтальная прокрутка на обёртке. Если она окажется на странице,
       сквозной обход в конце подпроекта это поймает — но лучше здесь. */
    const { container } = render(<Payments />)

    expect(container.firstElementChild?.className).toContain('overflow-x-auto')
  })

  it('строки не чередуются краской', () => {
    const { container } = render(<Payments />)

    expect(container.innerHTML).not.toContain('odd:')
  })
})
