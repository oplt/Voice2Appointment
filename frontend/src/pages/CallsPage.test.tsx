import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { listCalls } from '../api/calls'
import { CallsPage } from '../pages/CallsPage'

vi.mock('../api/calls', () => ({
  listCalls: vi.fn(),
  getCall: vi.fn(),
}))

const theme = createTheme()

function renderPage() {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <CallsPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('CallsPage states', () => {
  beforeEach(() => {
    vi.mocked(listCalls).mockReset()
  })

  it('renders empty state', async () => {
    vi.mocked(listCalls).mockResolvedValue({ items: [], next_cursor: null, limit: 25 })
    renderPage()
    expect(screen.getByRole('heading', { name: /calls/i })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText(/no call sessions yet/i)).toBeInTheDocument()
    })
  })

  it('renders success rows without transcript field', async () => {
    vi.mocked(listCalls).mockResolvedValue({
      items: [
        {
          id: 1,
          call_sid: 'CA1',
          status: 'completed',
          has_transcript: true,
          started_at: '2026-09-03T12:00:00Z',
        },
      ],
      next_cursor: null,
      limit: 25,
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getAllByText('CA1').length).toBeGreaterThan(0)
    })
    expect(screen.queryByText(/full transcript/i)).not.toBeInTheDocument()
  })

  it('renders error with recovery', async () => {
    vi.mocked(listCalls).mockRejectedValue(new ApiError(500, 'boom'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})
