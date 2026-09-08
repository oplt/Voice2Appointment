import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../api/client'
import { getDashboardSummary } from '../../api/dashboard'
import { withQueryClient } from '../../test/query'
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
    withQueryClient(
      <ThemeProvider theme={theme}>
        <MemoryRouter>
          <DashboardOverview />
        </MemoryRouter>
      </ThemeProvider>,
    ),
  )
}

describe('DashboardOverview states', () => {
  beforeEach(() => {
    vi.mocked(getDashboardSummary).mockReset()
  })

  it('renders compact operational metrics without KPI methodology', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue({
      appointments_today: 2,
      appointments_week: 5,
      upcoming: [
        {
          id: 1,
          summary: 'Alex · checkup',
          start_datetime: '2026-09-03T14:00:00Z',
          end_datetime: '2026-09-03T14:30:00Z',
          timezone: 'UTC',
          status: 'confirmed',
        },
      ],
      calendar_connected: true,
      recent_calls: 3,
      call_statistics: { calls_today: 1, recent_calls: 3, attention_today: 0 },
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
        attention_needed: {
          value: 0,
          definition: 'Calls needing follow-up.',
          window: 'local_day',
          timezone: 'UTC',
          drill_down: '/calls',
          exclusions: 'None',
        },
      },
      timezone: 'UTC',
      generated_at: '2026-09-03T12:00:00Z',
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Today' })).toBeInTheDocument()
    expect(screen.getByText('Calls')).toBeInTheDocument()
    expect(screen.getByText('Bookings')).toBeInTheDocument()
    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByText('Upcoming')).toBeInTheDocument()
    expect(screen.getByText('Alex · checkup')).toBeInTheDocument()
    expect(screen.getByText('System health')).toBeInTheDocument()
    expect(screen.queryByText('Details')).not.toBeInTheDocument()
    expect(screen.queryByText('Calls started in the local day.')).not.toBeInTheDocument()
    expect(screen.queryByText('Exclusions: None')).not.toBeInTheDocument()
  })

  it('renders error recovery', async () => {
    vi.mocked(getDashboardSummary).mockRejectedValue(new ApiError(500, 'summary failed'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('summary failed')).toBeInTheDocument()
    })
  })
})
