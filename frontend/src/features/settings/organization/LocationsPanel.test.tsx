import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createLocation, listLocations } from '../../../api/tenancy'
import { withQueryClient } from '../../../test/query'
import { LocationsPanel } from './LocationsPanel'

vi.mock('../../../api/tenancy', async () => {
  const actual = await vi.importActual<typeof import('../../../api/tenancy')>(
    '../../../api/tenancy',
  )
  return {
    ...actual,
    listLocations: vi.fn(),
    createLocation: vi.fn(),
    patchLocation: vi.fn(),
  }
})

vi.mock('../../../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify: vi.fn() }),
}))

function renderPanel(canWrite = true) {
  return render(
    withQueryClient(
      <ThemeProvider theme={createTheme()}>
        <LocationsPanel canWrite={canWrite} />
      </ThemeProvider>,
    ),
  )
}

describe('LocationsPanel', () => {
  beforeEach(() => {
    vi.mocked(listLocations).mockReset()
    vi.mocked(createLocation).mockReset()
  })

  it('lists locations and creates a new one when writable', async () => {
    vi.mocked(listLocations).mockResolvedValue([
      {
        id: 1,
        name: 'Main',
        timezone: 'UTC',
        address: null,
        phone: null,
        business_hours: {},
      },
    ])
    vi.mocked(createLocation).mockResolvedValue({
      id: 2,
      name: 'Branch',
      timezone: 'Europe/Berlin',
      address: null,
      phone: null,
      business_hours: {},
    })
    const user = userEvent.setup()
    renderPanel(true)
    expect(await screen.findByText('Main')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /new location|add location/i }))
    await user.type(screen.getByLabelText(/name/i), 'Branch')
    await user.click(screen.getByRole('button', { name: /^save|create$/i }))
    await waitFor(() => {
      expect(createLocation).toHaveBeenCalled()
    })
  })

  it('hides create action for read-only roles', async () => {
    vi.mocked(listLocations).mockResolvedValue([])
    renderPanel(false)
    await waitFor(() => expect(listLocations).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /new location|add location/i })).not.toBeInTheDocument()
  })
})
