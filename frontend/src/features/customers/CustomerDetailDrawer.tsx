import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import type { Customer } from '../../api/customers'
import { CustomerHistory } from './CustomerHistory'

function consentSummary(prefs: Record<string, unknown>): string {
  const keys = Object.keys(prefs || {})
  if (keys.length === 0) return 'No consent preferences recorded'
  return keys
    .map((key) => `${key}: ${String(prefs[key])}`)
    .slice(0, 8)
    .join(' · ')
}

type CustomerDetailDrawerProps = {
  customer: Customer | null
  canMerge: boolean
  onClose: () => void
  onEdit: (customer: Customer) => void
  onMerge: (customer: Customer) => void
}

export function CustomerDetailDrawer({
  customer,
  canMerge,
  onClose,
  onEdit,
  onMerge,
}: CustomerDetailDrawerProps) {
  const open = customer != null

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: { sx: { width: { xs: '100%', sm: 420 }, p: 2.5 } },
      }}
    >
      {customer ? (
        <Stack spacing={2.5} sx={{ height: '100%' }}>
          <Stack spacing={0.5}>
            <Typography variant="h3">{customer.name || 'Unnamed customer'}</Typography>
            <Typography variant="body2" color="text.secondary">
              #{customer.id}
            </Typography>
          </Stack>

          <Stack spacing={1}>
            <Typography variant="body2">
              Phone: {customer.phone || '—'}
            </Typography>
            <Typography variant="body2">
              Email: {customer.email || '—'}
            </Typography>
            <Typography variant="body2">
              Language: {customer.language || '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Consent: {consentSummary(customer.consent_preferences)}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            <Button variant="outlined" onClick={() => onEdit(customer)}>
              Edit
            </Button>
            {canMerge ? (
              <Button color="warning" variant="outlined" onClick={() => onMerge(customer)}>
                Merge…
              </Button>
            ) : null}
            <Button onClick={onClose}>Close</Button>
          </Stack>

          <Divider />
          <CustomerHistory customerId={customer.id} />
        </Stack>
      ) : null}
    </Drawer>
  )
}
