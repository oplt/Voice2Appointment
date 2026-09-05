import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { ChartWithTable, HeatmapWithTable } from './ChartWithTable'

const theme = createTheme()

describe('ChartWithTable', () => {
  it('exposes accessible toggle and table parity including zeros', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider theme={theme}>
        <ChartWithTable
          title="Calls by day"
          summary="2 points"
          labels={['Mon', 'Tue']}
          values={[3, 0]}
          valueLabel="Calls"
        >
          <div>chart</div>
        </ChartWithTable>
      </ThemeProvider>,
    )
    expect(screen.getByRole('heading', { name: 'Calls by day' })).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Show table' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(screen.getByRole('button', { name: 'Hide table' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByRole('table', { name: /Calls by day data table/i })).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})

describe('HeatmapWithTable', () => {
  it('includes zero cells in the semantic table', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider theme={theme}>
        <HeatmapWithTable
          title="Peak hours by weekday"
          summary="matrix"
          weekdays={['Mon']}
          hours={[0, 1]}
          matrix={[[0, 4]]}
        >
          <div>heatmap</div>
        </HeatmapWithTable>
      </ThemeProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'Show table' }))
    const cells = screen.getAllByRole('cell')
    expect(cells.some((c) => c.textContent === '0')).toBe(true)
    expect(cells.some((c) => c.textContent === '4')).toBe(true)
  })
})
