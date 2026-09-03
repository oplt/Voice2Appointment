import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { HomePage } from './HomePage'

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({
    isAuthenticated: false,
    login: vi.fn(),
    register: vi.fn(),
  }),
}))

vi.mock('../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify: vi.fn() }),
}))

const theme = createTheme()

describe('HomePage auth container', () => {
  it('shows sign-in and sign-up in one card', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider theme={theme}>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </ThemeProvider>,
    )
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sign up' }))
    expect(screen.getByRole('heading', { name: 'Create an account' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /username/i })).toBeInTheDocument()
  })
})
