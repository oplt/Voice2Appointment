import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import { SnackbarProvider, useSnackbar } from './SnackbarProvider'

const theme = createTheme()

function Trigger({ severity }: { severity: 'info' | 'error' }) {
  const { notify } = useSnackbar()
  return (
    <button type="button" onClick={() => notify('Saved prefs', severity)}>
      Notify
    </button>
  )
}

describe('SnackbarProvider live regions', () => {
  it('announces info with status / polite', async () => {
    render(
      <ThemeProvider theme={theme}>
        <SnackbarProvider>
          <Trigger severity="info" />
        </SnackbarProvider>
      </ThemeProvider>,
    )
    await act(async () => {
      screen.getByRole('button', { name: 'Notify' }).click()
    })
    const status = await screen.findByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('Saved prefs')
  })

  it('announces errors with alert / assertive', async () => {
    render(
      <ThemeProvider theme={theme}>
        <SnackbarProvider>
          <Trigger severity="error" />
        </SnackbarProvider>
      </ThemeProvider>,
    )
    await act(async () => {
      screen.getByRole('button', { name: 'Notify' }).click()
    })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('aria-live', 'assertive')
  })
})
