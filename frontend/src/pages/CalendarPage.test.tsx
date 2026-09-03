import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { getCalendarStatus, listCalendarEvents } from '../api/calendars'
import { SnackbarProvider } from '../components/SnackbarProvider'
import { CalendarPage } from '../pages/CalendarPage'

vi.mock('../api/calendars', () => ({
  getCalendarStatus: vi.fn(),
  listCalendarEvents: vi.fn(),
  checkCalendarAvailability: vi.fn(),
  startGoogleCalendarConnect: vi.fn(),
  updateCalendarPreferences: vi.fn(),
}))

const theme = createTheme()

function renderPage() {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <SnackbarProvider>
          <CalendarPage />
        </SnackbarProvider>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('CalendarPage states', () => {
  beforeEach(() => {
    vi.mocked(getCalendarStatus).mockReset()
    vi.mocked(listCalendarEvents).mockReset()
  })

  it('shows disconnected empty guidance', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: false,
      provider: 'google',
      calendar_id: null,
      time_zone: 'UTC',
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/not connected/i)).toBeInTheDocument()
    })
  })

  it('renders events with title contract', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: true,
      provider: 'google',
      calendar_id: 'primary',
      time_zone: 'UTC',
    })
    vi.mocked(listCalendarEvents).mockResolvedValue([
      {
        id: '1',
        title: 'Consult',
        start: '2026-09-03T10:00:00Z',
        end: '2026-09-03T10:30:00Z',
        allDay: false,
        url: 'https://calendar.example/1',
      },
    ])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Consult')).toBeInTheDocument()
    })
  })

  it('renders status error recovery', async () => {
    vi.mocked(getCalendarStatus).mockRejectedValue(new ApiError(503, 'calendar down'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('calendar down')).toBeInTheDocument()
    })
  })
})
