import { ThemeProvider, createTheme } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { requestPasswordReset } from '../api/auth'
import { ApiError } from '../api/client'
import { ForgotPasswordPage } from './ForgotPasswordPage'

vi.mock('../api/auth', () => ({
  requestPasswordReset: vi.fn(),
}))

const notify = vi.fn()
vi.mock('../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify }),
}))

function renderPage() {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter>
        <ForgotPasswordPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.mocked(requestPasswordReset).mockReset()
    notify.mockReset()
  })

  it('rejects submission with no email without calling the API', async () => {
    // The <TextField required> attribute normally blocks real browser
    // submission before React's handler runs; dispatch the submit event
    // directly to exercise the defense-in-depth check inside the handler.
    const { container } = renderPage()
    const form = container.querySelector('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form as HTMLFormElement)
    expect(await screen.findByText('Email is required')).toBeInTheDocument()
    expect(requestPasswordReset).not.toHaveBeenCalled()
  })

  it('shows the same confirmation message for a submitted email', async () => {
    vi.mocked(requestPasswordReset).mockResolvedValueOnce({ message: 'queued' })
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/email/i), 'owner@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() => expect(requestPasswordReset).toHaveBeenCalledWith('owner@example.com'))
    expect(
      await screen.findByText(/if an account exists for this email/i),
    ).toBeInTheDocument()
  })

  it('surfaces a recoverable error without leaking whether the email exists', async () => {
    vi.mocked(requestPasswordReset).mockRejectedValueOnce(
      new ApiError(503, 'Request failed'),
    )
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/email/i), 'owner@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(await screen.findByText('Request failed')).toBeInTheDocument()
    expect(
      screen.queryByText(/if an account exists for this email/i),
    ).not.toBeInTheDocument()
  })
})
