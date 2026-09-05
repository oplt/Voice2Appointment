import { ThemeProvider, createTheme } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTwilioAnalytics, getAnalyticsMeta, getAnalyticsSummary } from '../api/analytics'
import { AnalyticsPage } from './AnalyticsPage'
import type { AnalyticsSummary } from '../types'

vi.mock('../api/analytics', () => ({
  getAnalyticsMeta: vi.fn(),
  getAnalyticsSummary: vi.fn(),
  fetchTwilioAnalytics: vi.fn(),
}))

vi.mock('../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify: vi.fn() }),
}))

const theme = createTheme()

const meta = {
  timezone: 'America/Los_Angeles',
  today: '2026-03-10',
  default_range_days: 30,
  max_range_days: 90,
  default_range: { start: '2026-02-09', end: '2026-03-10' },
}

const emptySummary: AnalyticsSummary = {
  total_calls: 0,
  total_duration: 0,
  avg_duration: 0,
  total_cost: 0,
  calls_over_time: { labels: [], values: [] },
  duration_distribution: { labels: [], values: [] },
  cost_over_time: { labels: [], values: [] },
  top_numbers: { labels: [], values: [] },
  peak_hours_days: {
    weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    hours: Array.from({ length: 24 }, (_, i) => i),
    matrix: Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0)),
  },
  top_countries: [],
  geo_country_counts: [],
  timezone: 'America/Los_Angeles',
  comparison: null,
}

function renderPage(initial = '/analytics') {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter initialEntries={[initial]}>
        <AnalyticsPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('AnalyticsPage filters', () => {
  beforeEach(() => {
    vi.mocked(getAnalyticsMeta).mockReset()
    vi.mocked(getAnalyticsSummary).mockReset()
    vi.mocked(fetchTwilioAnalytics).mockReset()
    vi.mocked(getAnalyticsMeta).mockResolvedValue(meta)
    vi.mocked(getAnalyticsSummary).mockResolvedValue(emptySummary)
  })

  it('loads meta then issues exactly one summary request for defaults', async () => {
    renderPage()
    await waitFor(() => expect(getAnalyticsMeta).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1))
    expect(getAnalyticsSummary).toHaveBeenCalledWith({
      start: '2026-02-09',
      end: '2026-03-10',
      compare: false,
    })
    expect(await screen.findByText(/America\/Los_Angeles/)).toBeInTheDocument()
    expect(screen.getByText(/max 90d/)).toBeInTheDocument()
  })

  it('does not request while editing draft; Apply triggers one more request', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2026-03-01' },
    })
    expect(getAnalyticsSummary).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(2))
    expect(getAnalyticsSummary).toHaveBeenLastCalledWith({
      start: '2026-03-01',
      end: '2026-03-10',
      compare: false,
    })
  })

  it('rejects oversized apply using server max without fetching', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2025-01-01' },
    })
    fireEvent.change(screen.getByLabelText('End date'), {
      target: { value: '2026-03-10' },
    })
    await user.click(screen.getByRole('button', { name: 'Apply' }))
    expect(await screen.findByText(/cannot exceed 90 days/i)).toBeInTheDocument()
    expect(getAnalyticsSummary).toHaveBeenCalledTimes(1)
  })

  it('does not fetch malformed URL filters before correction', async () => {
    renderPage('/analytics?start=2026-02-31&end=2026-03-10')
    await waitFor(() => expect(getAnalyticsMeta).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(screen.getByText(/valid start date/i)).toBeInTheDocument(),
    )
    expect(getAnalyticsSummary).not.toHaveBeenCalled()
  })

  it('applies tenant presets into draft only until Apply', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(getAnalyticsSummary).toHaveBeenCalledTimes(1))
    await user.click(screen.getByRole('button', { name: 'Last 7 days' }))
    expect(getAnalyticsSummary).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('Start date')).toHaveValue('2026-03-04')
    expect(screen.getByLabelText('End date')).toHaveValue('2026-03-10')
  })

  it('honors back/forward URL changes with one request per distinct range', async () => {
    renderPage('/analytics?start=2026-03-01&end=2026-03-07')
    await waitFor(() =>
      expect(getAnalyticsSummary).toHaveBeenCalledWith({
        start: '2026-03-01',
        end: '2026-03-07',
        compare: false,
      }),
    )
    expect(getAnalyticsSummary).toHaveBeenCalledTimes(1)
  })
})
