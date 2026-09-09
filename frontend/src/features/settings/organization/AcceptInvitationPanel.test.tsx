import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { acceptInvitation } from '../../../api/tenancy'
import { ApiError } from '../../../api/client'
import { withQueryClient } from '../../../test/query'
import { AcceptInvitationPanel } from './AcceptInvitationPanel'

vi.mock('../../../api/tenancy', async () => {
  const actual = await vi.importActual<typeof import('../../../api/tenancy')>(
    '../../../api/tenancy',
  )
  return { ...actual, acceptInvitation: vi.fn() }
})

vi.mock('../../../auth/AuthProvider', () => ({
  useAuth: () => ({ retryBootstrap: vi.fn() }),
}))

vi.mock('../../../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify: vi.fn() }),
}))

function renderPanel(initialToken = '') {
  return render(
    withQueryClient(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <AcceptInvitationPanel initialToken={initialToken} />
        </MemoryRouter>
      </ThemeProvider>,
    ),
  )
}

describe('AcceptInvitationPanel', () => {
  beforeEach(() => {
    vi.mocked(acceptInvitation).mockReset()
  })

  it('accepts a pasted invitation token', async () => {
    vi.mocked(acceptInvitation).mockResolvedValue({
      user_id: 2,
      email: 'e2e@example.com',
      username: 'e2e',
      role: 'staff',
    })
    const user = userEvent.setup()
    renderPanel('invite-token-abc')
    expect(screen.getByDisplayValue('invite-token-abc')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /accept invitation/i }))
    await waitFor(() => {
      expect(acceptInvitation).toHaveBeenCalledWith('invite-token-abc')
    })
  })

  it('surfaces accept failures', async () => {
    vi.mocked(acceptInvitation).mockRejectedValue(new ApiError(400, 'token invalid'))
    const user = userEvent.setup()
    renderPanel('bad')
    await user.click(screen.getByRole('button', { name: /accept invitation/i }))
    expect(await screen.findByText(/token invalid/i)).toBeInTheDocument()
  })
})
