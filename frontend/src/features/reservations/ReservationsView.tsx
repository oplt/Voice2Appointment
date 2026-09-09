import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { listCatalogItems } from '../../api/catalog'
import { ApiError } from '../../api/client'
import { listCustomers } from '../../api/customers'
import { queryKeys } from '../../api/queryKeys'
import { listResources } from '../../api/resources'
import {
  cancelReservation,
  changeReservationResources,
  getReservation,
  listReservations,
  rescheduleReservation,
  updateReservationPartySize,
  type Reservation,
  type ReservationDetail,
  type ReservationLineItem,
} from '../../api/reservations'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'

const PAGE_SIZE = 50

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

function formatAmount(amountMinor: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amountMinor / 100)
  } catch {
    return `${(amountMinor / 100).toFixed(2)} ${currency}`
  }
}

function channelFromAllocation(allocation: Record<string, unknown>): string | null {
  const channel = allocation.channel
  if (typeof channel === 'string' && channel) return channel
  const source = allocation.source
  if (typeof source === 'string' && source) return source
  return null
}

function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString()
}

export function ReservationsView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [accumulated, setAccumulated] = useState<Reservation[]>([])
  const [detailId, setDetailId] = useState<number | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null)

  const [rescheduleTarget, setRescheduleTarget] = useState<Reservation | null>(null)
  const [rescheduleStart, setRescheduleStart] = useState('')
  const [rescheduleEnd, setRescheduleEnd] = useState('')

  const [partyTarget, setPartyTarget] = useState<Reservation | null>(null)
  const [partySize, setPartySize] = useState('1')

  const [resourcesTarget, setResourcesTarget] = useState<ReservationDetail | null>(null)
  const [selectedResourceIds, setSelectedResourceIds] = useState<number[]>([])

  const listQuery = useQuery({
    queryKey: queryKeys.reservations.list({ limit: PAGE_SIZE, offset }),
    queryFn: () => listReservations({ limit: PAGE_SIZE, offset }),
  })

  useEffect(() => {
    const page = listQuery.data
    if (!page) return
    setAccumulated((prev) => {
      if (page.offset === 0) return page.items
      const seen = new Set(prev.map((row) => row.id))
      return [...prev, ...page.items.filter((row) => !seen.has(row.id))]
    })
  }, [listQuery.data])

  const detailQuery = useQuery({
    queryKey: queryKeys.reservations.detail(detailId ?? 0),
    queryFn: () => getReservation(detailId!),
    enabled: detailId != null,
  })

  const catalogQuery = useQuery({
    queryKey: queryKeys.catalog.items({ forReservations: true }),
    queryFn: () => listCatalogItems({ limit: 100 }),
  })

  const customersQuery = useQuery({
    queryKey: queryKeys.customers.list(),
    queryFn: () => listCustomers(),
  })

  const resourcesQuery = useQuery({
    queryKey: queryKeys.resources.list,
    queryFn: () => listResources(),
    enabled: resourcesTarget != null,
  })

  const reservations = accumulated
  const total = listQuery.data?.total ?? 0
  const hasMore = reservations.length < total

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

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.reservations.all })
  }

  const cancelMutation = useMutation({
    mutationFn: (row: Reservation) => cancelReservation(row.id, {}),
    onSuccess: () => {
      notify('Reservation cancelled', 'success')
      setCancelTarget(null)
      if (detailId && cancelTarget && detailId === cancelTarget.id) setDetailId(null)
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Cancel failed', 'error')
    },
  })

  const rescheduleMutation = useMutation({
    mutationFn: () => {
      if (!rescheduleTarget) throw new Error('No reservation')
      return rescheduleReservation(rescheduleTarget.id, {
        start_datetime: fromDatetimeLocalValue(rescheduleStart),
        end_datetime: rescheduleEnd ? fromDatetimeLocalValue(rescheduleEnd) : null,
      })
    },
    onSuccess: (row) => {
      notify('Reservation rescheduled', 'success')
      setRescheduleTarget(null)
      setDetailId(row.id)
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Reschedule failed', 'error')
    },
  })

  const partyMutation = useMutation({
    mutationFn: () => {
      if (!partyTarget) throw new Error('No reservation')
      return updateReservationPartySize(partyTarget.id, {
        party_size: Math.max(1, Number(partySize) || 1),
      })
    },
    onSuccess: (row) => {
      notify('Party size updated', 'success')
      setPartyTarget(null)
      setDetailId(row.id)
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Party size update failed', 'error')
    },
  })

  const resourcesMutation = useMutation({
    mutationFn: () => {
      if (!resourcesTarget) throw new Error('No reservation')
      return changeReservationResources(resourcesTarget.id, {
        resource_ids: selectedResourceIds,
      })
    },
    onSuccess: (row) => {
      notify('Resources updated', 'success')
      setResourcesTarget(null)
      setDetailId(row.id)
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Resource change failed', 'error')
    },
  })

  const openReschedule = (row: Reservation) => {
    setRescheduleTarget(row)
    setRescheduleStart(toDatetimeLocalValue(row.start_datetime))
    setRescheduleEnd(toDatetimeLocalValue(row.end_datetime))
  }

  const openParty = (row: Reservation) => {
    setPartyTarget(row)
    setPartySize(String(row.party_size))
  }

  const openResources = (detail: ReservationDetail) => {
    setResourcesTarget(detail)
    setSelectedResourceIds(detail.resource_ids.slice())
  }

  const detail: ReservationDetail | Reservation | null =
    detailQuery.data ??
    (detailId != null ? reservations.find((r) => r.id === detailId) ?? null : null)

  const lineItems: ReservationLineItem[] =
    detailQuery.data?.line_items ??
    (detail && 'line_items' in detail ? detail.line_items : [])

  const mutable = detail != null && detail.status !== 'cancelled'

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

      {listQuery.isPending && offset === 0 ? (
        <CircularProgress size={28} />
      ) : reservations.length === 0 ? (
        <Typography color="text.secondary">No reservations yet.</Typography>
      ) : (
        <>
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
                          <Button size="small" onClick={() => setDetailId(row.id)}>
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
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Showing {reservations.length} of {total}
            </Typography>
            {hasMore ? (
              <Button
                variant="outlined"
                disabled={listQuery.isFetching}
                onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
              >
                {listQuery.isFetching ? 'Loading…' : 'Load more'}
              </Button>
            ) : null}
          </Stack>
        </>
      )}

      <Dialog
        open={detailId != null}
        onClose={() => setDetailId(null)}
        fullWidth
        maxWidth="sm"
      >
        {detail ? (
          <>
            <DialogTitle>Reservation #{detail.id}</DialogTitle>
            <DialogContent dividers>
              {detailQuery.isPending ? (
                <CircularProgress size={24} />
              ) : (
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
                  <Typography variant="body2">Mode: {detail.scheduling_mode}</Typography>
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
                  {'resource_ids' in detail && detail.resource_ids.length > 0 ? (
                    <Typography variant="body2">
                      Resources: {detail.resource_ids.map((id) => `#${id}`).join(', ')}
                    </Typography>
                  ) : null}

                  <Typography variant="subtitle2" sx={{ pt: 1 }}>
                    Line items (price snapshot)
                  </Typography>
                  {lineItems.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No line items on this reservation.
                    </Typography>
                  ) : (
                    <TableContainer>
                      <Table size="small" aria-label="Line items">
                        <TableHead>
                          <TableRow>
                            <TableCell>Item</TableCell>
                            <TableCell>Qty</TableCell>
                            <TableCell>Unit</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {lineItems.map((line) => (
                            <TableRow key={line.id}>
                              <TableCell>{line.item_name}</TableCell>
                              <TableCell>{line.quantity}</TableCell>
                              <TableCell>
                                {formatAmount(line.unit_price_minor, line.currency)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </Stack>
              )}
            </DialogContent>
            <DialogActions sx={{ flexWrap: 'wrap', gap: 1 }}>
              <Button
                disabled={!mutable}
                onClick={() => openReschedule(detail)}
              >
                Reschedule
              </Button>
              <Button disabled={!mutable} onClick={() => openParty(detail)}>
                Party size
              </Button>
              <Button
                disabled={!mutable || !detailQuery.data}
                onClick={() => detailQuery.data && openResources(detailQuery.data)}
              >
                Change resources
              </Button>
              <Button
                color="error"
                disabled={!mutable}
                onClick={() => setCancelTarget(detail)}
              >
                Cancel
              </Button>
              <Button onClick={() => setDetailId(null)}>Close</Button>
            </DialogActions>
          </>
        ) : null}
      </Dialog>

      <Dialog
        open={rescheduleTarget != null}
        onClose={() => !rescheduleMutation.isPending && setRescheduleTarget(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Reschedule reservation</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Start"
              type="datetime-local"
              value={rescheduleStart}
              onChange={(e) => setRescheduleStart(e.target.value)}
              fullWidth
              InputLabelProps={{ shrink: true }}
              required
            />
            <TextField
              label="End"
              type="datetime-local"
              value={rescheduleEnd}
              onChange={(e) => setRescheduleEnd(e.target.value)}
              fullWidth
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setRescheduleTarget(null)}
            disabled={rescheduleMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!rescheduleStart || rescheduleMutation.isPending}
            onClick={() => rescheduleMutation.mutate()}
          >
            Reschedule
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={partyTarget != null}
        onClose={() => !partyMutation.isPending && setPartyTarget(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Update party size</DialogTitle>
        <DialogContent dividers>
          <TextField
            label="Party size"
            type="number"
            value={partySize}
            onChange={(e) => setPartySize(e.target.value)}
            fullWidth
            sx={{ mt: 1 }}
            inputProps={{ min: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPartyTarget(null)} disabled={partyMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!partySize || partyMutation.isPending}
            onClick={() => partyMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={resourcesTarget != null}
        onClose={() => !resourcesMutation.isPending && setResourcesTarget(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Change resources</DialogTitle>
        <DialogContent dividers>
          {resourcesQuery.isPending ? (
            <CircularProgress size={24} />
          ) : (resourcesQuery.data ?? []).length === 0 ? (
            <Typography color="text.secondary">No active resources available.</Typography>
          ) : (
            <Stack spacing={0.5} sx={{ pt: 1 }}>
              {(resourcesQuery.data ?? []).map((resource) => (
                <FormControlLabel
                  key={resource.id}
                  control={
                    <Checkbox
                      checked={selectedResourceIds.includes(resource.id)}
                      onChange={(e) => {
                        setSelectedResourceIds((prev) =>
                          e.target.checked
                            ? [...prev, resource.id]
                            : prev.filter((id) => id !== resource.id),
                        )
                      }}
                    />
                  }
                  label={`${resource.name} (${resource.resource_type})`}
                />
              ))}
              {selectedResourceIds.length === 0 ? (
                <Alert severity="warning">Select at least one resource.</Alert>
              ) : null}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setResourcesTarget(null)}
            disabled={resourcesMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={selectedResourceIds.length === 0 || resourcesMutation.isPending}
            onClick={() => resourcesMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
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
