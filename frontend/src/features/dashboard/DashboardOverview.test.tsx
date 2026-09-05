import { ThemeProvider, createTheme } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../api/client'
import { getDashboardSummary } from '../../api/dashboard'
import { DashboardOverview } from './DashboardOverview'

vi.mock('../../api/dashboard', () => ({
  getDashboardSummary: vi.fn(),
}))
vi.mock('../../hooks/useApiHealth', () => ({
  useApiHealth: () => ({ status: 'ok' as const, message: 'ok', refresh: vi.fn() }),
}))

const theme = createTheme()

function renderPage() {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <DashboardOverview />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('DashboardOverview states', () => {
  beforeEach(() => {
    vi.mocked(getDashboardSummary).mockReset()
  })

  it('renders KPI fields from contract', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue({
      appointments_today: 2,
      appointments_week: 5,
      upcoming: [],
      calendar_connected: true,
      recent_calls: 3,
      call_statistics: { calls_today: 1, recent_calls: 3 },
      provider_status: { twilio: true, deepgram: true, calendar: true },
      operational: {
        calls_today: {
          value: 1,
          definition: 'Calls started in the local day.',
          window: 'local_day',
          timezone: 'UTC',
          drill_down: '/calls',
          exclusions: 'None',
          numerator: 1,
          denominator: 2,
        },
      },
      timezone: 'UTC',
      generated_at: '2026-09-03T12:00:00Z',
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('Details'))
    expect(screen.getByText('Calls started in the local day.')).toBeInTheDocument()
    expect(screen.getByText('Window: local_day (UTC)')).toBeInTheDocument()
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
    expect(screen.getByText('Exclusions: None')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View details' })).toHaveAttribute('href', '/calls')
    expect(screen.getByText('Twilio configured')).toBeInTheDocument()
  })

  it('renders error recovery', async () => {
    vi.mocked(getDashboardSummary).mockRejectedValue(new ApiError(500, 'summary failed'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('summary failed')).toBeInTheDocument()
    })
  })
})
