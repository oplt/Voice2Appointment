import { ThemeProvider, createTheme } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listAppointments } from '../api/appointments'
import { SnackbarProvider } from '../components/SnackbarProvider'
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
    <ThemeProvider theme={createTheme()}><MemoryRouter><SnackbarProvider><AppointmentsPage /></SnackbarProvider></MemoryRouter></ThemeProvider>,
  )
}

describe('AppointmentsPage pagination', () => {
  beforeEach(() => vi.mocked(listAppointments).mockReset())

  it('traverses beyond the first 100 rows without duplicates', async () => {
    vi.mocked(listAppointments)
      .mockResolvedValueOnce({ items: Array.from({ length: 100 }, (_, index) => appointment(index + 1)), next_cursor: 'next' })
      .mockResolvedValueOnce({ items: [appointment(100), appointment(101)], next_cursor: null })
    renderPage()
    await screen.findAllByText('Appointment 100')
    fireEvent.click(screen.getByRole('button', { name: /load more appointments/i }))
    await screen.findAllByText('Appointment 101')
    await waitFor(() => expect(listAppointments).toHaveBeenLastCalledWith({ scope: 'upcoming', limit: 100, cursor: 'next' }))
    expect(screen.getAllByText('Appointment 100')).toHaveLength(2)
  })
})
