import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { capturePaymentByToken, getPaymentByToken } from '../api/payments'
import { ApiError } from '../api/client'
import { SecurePaymentPage } from './SecurePaymentPage'

vi.mock('../api/payments', async () => {
  const actual = await vi.importActual<typeof import('../api/payments')>('../api/payments')
  return {
    ...actual,
    getPaymentByToken: vi.fn(),
    capturePaymentByToken: vi.fn(),
  }
})

function renderPage(path: string) {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/secure/:purpose" element={<SecurePaymentPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

const pendingPayment = {
  id: 7,
  organization_id: 1,
  reservation_id: 3,
  amount_minor: 2500,
  currency: 'EUR',
  purpose: 'deposit',
  provider: 'manual',
  status: 'pending',
  checkout_url: null,
  link_expired: false,
  expires_at: null,
}

describe('SecurePaymentPage', () => {
  beforeEach(() => {
    vi.mocked(getPaymentByToken).mockReset()
    vi.mocked(capturePaymentByToken).mockReset()
  })

  it('shows invalid state when token is missing', async () => {
    renderPage('/secure/deposit')
    expect(
      await screen.findByText(/payment link is invalid or incomplete/i),
    ).toBeInTheDocument()
    expect(getPaymentByToken).not.toHaveBeenCalled()
  })

  it('shows invalid state for unknown token', async () => {
    vi.mocked(getPaymentByToken).mockRejectedValueOnce(new ApiError(404, 'not found'))
    renderPage('/secure/deposit?t=bad-token')
    expect(
      await screen.findByText(/payment link is invalid or incomplete/i),
    ).toBeInTheDocument()
  })

  it('does not treat status=success as paid without provider confirmation', async () => {
    vi.mocked(getPaymentByToken).mockResolvedValue({ ...pendingPayment })
    renderPage('/secure/deposit?t=tok&status=success')
    expect(await screen.findByText(/amount due/i)).toBeInTheDocument()
    expect(screen.queryByText(/payment received/i)).not.toBeInTheDocument()
    expect(screen.getByText(/checking payment status/i)).toBeInTheDocument()
  })

  it('captures a manual payment with the secure token', async () => {
    vi.mocked(getPaymentByToken).mockResolvedValue({ ...pendingPayment })
    vi.mocked(capturePaymentByToken).mockResolvedValue({
      ...pendingPayment,
      status: 'captured',
    })
    const user = userEvent.setup()
    renderPage('/secure/deposit?t=good-token')
    expect(await screen.findByRole('button', { name: /confirm payment/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /confirm payment/i }))
    await waitFor(() =>
      expect(capturePaymentByToken).toHaveBeenCalledWith(7, 'good-token'),
    )
    expect(await screen.findByText(/payment received/i)).toBeInTheDocument()
  })

  it('shows expired state when the payment link is expired', async () => {
    vi.mocked(getPaymentByToken).mockResolvedValue({
      ...pendingPayment,
      link_expired: true,
      status: 'pending',
    })
    renderPage('/secure/deposit?t=expired-token')
    expect(await screen.findByText(/expired/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /confirm payment/i })).not.toBeInTheDocument()
  })

  it('shows paid state when payment is already captured', async () => {
    vi.mocked(getPaymentByToken).mockResolvedValue({
      ...pendingPayment,
      status: 'captured',
    })
    renderPage('/secure/deposit?t=paid-token')
    expect(await screen.findByText(/payment received/i)).toBeInTheDocument()
  })
})
