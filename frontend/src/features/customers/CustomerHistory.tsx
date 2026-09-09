import Alert from '@mui/material/Alert'
import CircularProgress from '@mui/material/CircularProgress'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'

import { ApiError } from '../../api/client'
import { listCustomerReservations } from '../../api/customers'
import { queryKeys } from '../../api/queryKeys'

function formatWhen(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

type CustomerHistoryProps = {
  customerId: number
}

export function CustomerHistory({ customerId }: CustomerHistoryProps) {
  const historyQuery = useQuery({
    queryKey: queryKeys.customers.reservations(customerId),
    queryFn: () => listCustomerReservations(customerId),
  })

  if (historyQuery.isPending) {
    return <CircularProgress size={24} />
  }

  if (historyQuery.error) {
    return (
      <Alert severity="error">
        {historyQuery.error instanceof ApiError
          ? historyQuery.error.message
          : 'Failed to load reservation history'}
      </Alert>
    )
  }

  const rows = historyQuery.data ?? []
  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No reservation history.
      </Typography>
    )
  }

  return (
    <Stack spacing={1}>
      <Typography variant="h3">Reservation history</Typography>
      <List dense disablePadding>
        {rows.map((row) => (
          <ListItem key={row.id} divider disableGutters>
            <ListItemText
              primary={`${formatWhen(row.start_datetime)} · ${row.status}`}
              secondary={`Party ${row.party_size}${
                row.catalog_item_id != null ? ` · item #${row.catalog_item_id}` : ''
              }`}
            />
          </ListItem>
        ))}
      </List>
    </Stack>
  )
}
