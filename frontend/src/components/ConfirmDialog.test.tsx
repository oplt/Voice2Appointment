import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from './ConfirmDialog'

const theme = createTheme()

function Harness() {
  const [open, setOpen] = useState(false)
  return (
    <ThemeProvider theme={theme}>
      <button type="button" onClick={() => setOpen(true)}>
        Open confirm
      </button>
      <ConfirmDialog
        open={open}
        title="Disconnect?"
        description="Clears stored credentials."
        onClose={() => setOpen(false)}
        onConfirm={() => setOpen(false)}
      />
    </ThemeProvider>
  )
}

describe('ConfirmDialog focus', () => {
  it('restores focus to the opener after close', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open confirm' })
    await user.click(opener)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    await waitFor(() => {
      expect(opener).toHaveFocus()
    })
  })

  it('exposes labelled dialog semantics', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <ThemeProvider theme={theme}>
        <ConfirmDialog
          open
          title="Delete item"
          description="This cannot be undone."
          onClose={vi.fn()}
          onConfirm={onConfirm}
        />
      </ThemeProvider>,
    )
    const dialog = screen.getByRole('dialog', { name: 'Delete item' })
    expect(dialog).toHaveAttribute('aria-describedby', 'confirm-dialog-description')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(onConfirm).toHaveBeenCalled()
  })
})
