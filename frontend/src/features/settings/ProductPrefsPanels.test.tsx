import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../api/client'
import { getProductPrefs, patchProductPrefs } from '../../api/users'
import { SnackbarProvider } from '../../components/SnackbarProvider'
import { ProductPrefsPanels } from './ProductPrefsPanels'

vi.mock('../../api/users', () => ({
  getProductPrefs: vi.fn(),
  patchProductPrefs: vi.fn(),
}))

const prefs = {
  notifications: {
    channel: 'email' as const,
    confirmations_enabled: false,
    reminders_enabled: false,
    consent_at: null,
    quiet_hours_start: null,
    quiet_hours_end: null,
    reminder_hours_before: 24,
  },
  retention: { transcript_days: 30, recording_days: 14, legal_hold: false },
  transcripts: { storage_enabled: false, consent_at: null, redact_phone_numbers: true },
  transfer: { enabled: false, destination_e164: null, business_hours_only: false },
  languages: { primary: 'en', enabled: ['en'] },
}

function renderPanel() {
  return render(
    <ThemeProvider theme={createTheme()}>
      <SnackbarProvider>
        <ProductPrefsPanels />
      </SnackbarProvider>
    </ThemeProvider>,
  )
}

describe('ProductPrefsPanels', () => {
  beforeEach(() => {
    vi.mocked(getProductPrefs).mockReset()
    vi.mocked(patchProductPrefs).mockReset()
  })

  it('does not offer a save path after loading preferences fails', async () => {
    vi.mocked(getProductPrefs).mockRejectedValue(new ApiError(500, 'settings unavailable'))

    renderPanel()

    expect(await screen.findByText('settings unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save product settings' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry loading settings' })).toBeEnabled()
  })

  it('requires explicit transcript consent before saving storage changes', async () => {
    const user = userEvent.setup()
    vi.mocked(getProductPrefs).mockResolvedValue(prefs)
    vi.mocked(patchProductPrefs).mockResolvedValue({
      ...prefs,
      transcripts: { ...prefs.transcripts, storage_enabled: true, consent_at: '2030-01-01T00:00:00Z' },
    })

    renderPanel()
    await screen.findByRole('button', { name: 'Save product settings' })
    await user.click(screen.getByRole('switch', { name: 'Store voice transcripts' }))

    const save = screen.getByRole('button', { name: 'Save product settings' })
    expect(save).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /I confirm that transcript storage consent/i }))
    expect(save).toBeEnabled()
    await user.click(save)

    await waitFor(() => {
      expect(patchProductPrefs).toHaveBeenCalledWith(
        expect.objectContaining({ transcript_storage_consent: true }),
      )
    })
  })
})
