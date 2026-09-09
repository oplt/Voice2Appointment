import { ThemeProvider, createTheme } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listAppointments } from '../api/appointments'
import { SnackbarProvider } from '../components/SnackbarProvider'
import { withQueryClient } from '../test/query'
import { AppointmentsPage } from './AppointmentsPage'

vi.mock('../api/appointments', () => ({
  listAppointments: vi.fn(),
  getAppointment: vi.fn(),
  createAppointment: vi.fn(),
  updateAppointment: vi.fn(),
  deleteAppointment: vi.fn(),
}))

const appointment = (id: number) => ({
  id,
  summary: `Appointment ${id}`,
  start_datetime: `2026-09-05T${String(id % 24).padStart(2, '0')}:00:00Z`,
  end_datetime: `2026-09-05T${String(id % 24).padStart(2, '0')}:30:00Z`,
  timezone: 'UTC',
  status: 'confirmed',
  provider_sync_status: 'synced',
})

function renderPage() {
  return render(
    withQueryClient(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <SnackbarProvider>
            <AppointmentsPage />
          </SnackbarProvider>
        </MemoryRouter>
      </ThemeProvider>,
    ),
  )
}

describe('AppointmentsPage pagination', () => {
  beforeEach(() => vi.mocked(listAppointments).mockReset())

  it('traverses cursor pages without duplicates', async () => {
    vi.mocked(listAppointments).mockImplementation(async (params = {}) => {
      if (params.cursor === 'next') {
        return { items: [appointment(3), appointment(4)], next_cursor: null }
      }
      return {
        items: [appointment(1), appointment(2), appointment(3)],
        next_cursor: 'next',
      }
    })
    renderPage()
    await screen.findAllByText('Appointment 3')
    fireEvent.click(screen.getByRole('button', { name: /load more appointments/i }))
    await screen.findAllByText('Appointment 4')
    await waitFor(() =>
      expect(listAppointments).toHaveBeenCalledWith({
        scope: 'upcoming',
        limit: 100,
        cursor: 'next',
      }),
    )
    // Mobile + desktop both render; Map-dedup keeps a single logical row (2 DOM nodes).
    expect(screen.getAllByText('Appointment 3')).toHaveLength(2)
    expect(screen.getAllByText('Appointment 4')).toHaveLength(2)
  })
})
