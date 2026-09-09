import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { listCatalogItems } from '../../api/catalog'
import { ApiError } from '../../api/client'
import { listCustomers } from '../../api/customers'
import { queryKeys } from '../../api/queryKeys'
import {
  cancelReservation,
  listReservations,
  type Reservation,
} from '../../api/reservations'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'

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

function channelFromAllocation(allocation: Record<string, unknown>): string | null {
  const channel = allocation.channel
  if (typeof channel === 'string' && channel) return channel
  const source = allocation.source
  if (typeof source === 'string' && source) return source
  return null
}

export function ReservationsView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [detail, setDetail] = useState<Reservation | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null)

  const listQuery = useQuery({
    queryKey: queryKeys.reservations.list(),
    queryFn: () => listReservations(),
  })

  const catalogQuery = useQuery({
    queryKey: queryKeys.catalog.items({ forReservations: true }),
    queryFn: () => listCatalogItems({ limit: 100 }),
  })

  const customersQuery = useQuery({
    queryKey: queryKeys.customers.list(),
    queryFn: () => listCustomers(),
  })

  const reservations = listQuery.data ?? []
  const catalogName = (id: number | null) => {
    if (id == null) return '—'
    return catalogQuery.data?.items.find((i) => i.id === id)?.name ?? `#${id}`
  }
  const customerName = (id: number | null) => {
    if (id == null) return '—'
    const row = customersQuery.data?.find((c) => c.id === id)
    if (!row) return `#${id}`
    return row.name || row.phone || row.email || `#${id}`
  }

  const cancelMutation = useMutation({
    mutationFn: (row: Reservation) => cancelReservation(row.id, {}),
    onSuccess: () => {
      notify('Reservation cancelled', 'success')
      setCancelTarget(null)
      if (detail && cancelTarget && detail.id === cancelTarget.id) setDetail(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.reservations.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Cancel failed', 'error')
    },
  })

  const listError =
    listQuery.error == null
      ? null
      : listQuery.error instanceof ApiError
        ? listQuery.error.message
        : 'Failed to load reservations'

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Reservations"
        subtitle="Bookings across services, capacity, and resources."
      />

      {listError ? <Alert severity="error">{listError}</Alert> : null}

      {listQuery.isPending ? (
        <CircularProgress size={28} />
      ) : reservations.length === 0 ? (
        <Typography color="text.secondary">No reservations yet.</Typography>
      ) : (
        <TableContainer>
          <Table size="small" aria-label="Reservations">
            <TableHead>
              <TableRow>
                <TableCell>Service</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Party</TableCell>
                <TableCell>Location</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Start</TableCell>
                <TableCell>End</TableCell>
                <TableCell>Channel</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {reservations.map((row) => {
                const channel = channelFromAllocation(row.allocation_json)
                return (
                  <TableRow key={row.id} hover>
                    <TableCell>{catalogName(row.catalog_item_id)}</TableCell>
                    <TableCell>{customerName(row.customer_id)}</TableCell>
                    <TableCell>{row.party_size}</TableCell>
                    <TableCell>
                      {row.location_id != null ? `#${row.location_id}` : '—'}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={row.status} variant="outlined" />
                    </TableCell>
                    <TableCell>{formatWhen(row.start_datetime)}</TableCell>
                    <TableCell>{formatWhen(row.end_datetime)}</TableCell>
                    <TableCell>{channel ?? '—'}</TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                        <Button size="small" onClick={() => setDetail(row)}>
                          Detail
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          disabled={row.status === 'cancelled'}
                          onClick={() => setCancelTarget(row)}
                        >
                          Cancel
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={detail != null} onClose={() => setDetail(null)} fullWidth maxWidth="sm">
        {detail ? (
          <>
            <DialogTitle>Reservation #{detail.id}</DialogTitle>
            <DialogContent dividers>
              <Stack spacing={1.5}>
                <Typography variant="body2">
                  Service: {catalogName(detail.catalog_item_id)}
                </Typography>
                <Typography variant="body2">
                  Customer: {customerName(detail.customer_id)}
                </Typography>
                <Typography variant="body2">Party size: {detail.party_size}</Typography>
                <Typography variant="body2">
                  Location: {detail.location_id != null ? `#${detail.location_id}` : '—'}
                </Typography>
                <Typography variant="body2">Status: {detail.status}</Typography>
                <Typography variant="body2">
                  Mode: {detail.scheduling_mode}
                </Typography>
                <Typography variant="body2">
                  Provider sync: {detail.provider_sync_status}
                </Typography>
                <Typography variant="body2">
                  Start: {formatWhen(detail.start_datetime)}
                </Typography>
                <Typography variant="body2">
                  End: {formatWhen(detail.end_datetime)}
                </Typography>
                {detail.hold_expires_at ? (
                  <Typography variant="body2">
                    Hold expires: {formatWhen(detail.hold_expires_at)}
                  </Typography>
                ) : null}
                <Typography variant="body2" color="text.secondary">
                  Channel:{' '}
                  {channelFromAllocation(detail.allocation_json) ?? 'not returned by API'}
                </Typography>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button
                color="error"
                disabled={detail.status === 'cancelled'}
                onClick={() => setCancelTarget(detail)}
              >
                Cancel reservation
              </Button>
              <Button onClick={() => setDetail(null)}>Close</Button>
            </DialogActions>
          </>
        ) : null}
      </Dialog>

      <ConfirmDialog
        open={Boolean(cancelTarget)}
        title="Cancel reservation?"
        description={
          cancelTarget
            ? `Reservation #${cancelTarget.id} will be marked cancelled.`
            : undefined
        }
        confirmLabel="Cancel reservation"
        confirmColor="error"
        loading={cancelMutation.isPending}
        onClose={() => {
          if (!cancelMutation.isPending) setCancelTarget(null)
        }}
        onConfirm={() => {
          if (cancelTarget) cancelMutation.mutate(cancelTarget)
        }}
      />
    </Stack>
  )
}
