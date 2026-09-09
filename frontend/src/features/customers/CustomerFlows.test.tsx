import { ThemeProvider, createTheme } from '@mui/material/styles'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { withQueryClient } from '../../test/query'
import { CustomerDetailDrawer } from './CustomerDetailDrawer'
import { MergeCustomerDialog } from './MergeCustomerDialog'

vi.mock('../../api/customers', async () => {
  const actual = await vi.importActual<typeof import('../../api/customers')>(
    '../../api/customers',
  )
  return {
    ...actual,
    listCustomerReservations: vi.fn().mockResolvedValue([]),
    mergeCustomers: vi.fn().mockResolvedValue({
      id: 2,
      name: 'Target',
      phone: null,
      email: 't@example.com',
      language: null,
      consent_preferences: {},
      metadata_json: {},
    }),
  }
})

vi.mock('../../components/SnackbarProvider', () => ({
  useSnackbar: () => ({ notify: vi.fn() }),
}))

const source = {
  id: 1,
  name: 'Source',
  phone: '+15550001',
  email: 's@example.com',
  language: 'en',
  consent_preferences: {},
  metadata_json: {},
}

const target = {
  id: 2,
  name: 'Target',
  phone: null,
  email: 't@example.com',
  language: null,
  consent_preferences: {},
  metadata_json: {},
}

describe('Customer detail and merge', () => {
  it('renders detail drawer with history and merge action', async () => {
    const onMerge = vi.fn()
    render(
      withQueryClient(
        <ThemeProvider theme={createTheme()}>
          <CustomerDetailDrawer
            customer={source}
            canMerge
            onClose={vi.fn()}
            onEdit={vi.fn()}
            onMerge={onMerge}
          />
        </ThemeProvider>,
      ),
    )
    expect(screen.getByText('Source')).toBeInTheDocument()
    expect(screen.getByText(/\+15550001/)).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /merge/i }))
    expect(onMerge).toHaveBeenCalledWith(source)
  })

  it('requires MERGE confirmation before merging', async () => {
    const onMerged = vi.fn()
    const user = userEvent.setup()
    render(
      withQueryClient(
        <ThemeProvider theme={createTheme()}>
          <MergeCustomerDialog
            open
            source={source}
            candidates={[source, target]}
            onClose={vi.fn()}
            onMerged={onMerged}
          />
        </ThemeProvider>,
      ),
    )
    const mergeBtn = screen.getByRole('button', { name: /merge permanently/i })
    expect(mergeBtn).toBeDisabled()
    await user.click(screen.getByLabelText(/target customer/i))
    await user.click(await screen.findByRole('option', { name: 'Target (#2)' }))
    await user.type(screen.getByLabelText(/type MERGE to confirm/i), 'MERGE')
    expect(mergeBtn).not.toBeDisabled()
  })
})
