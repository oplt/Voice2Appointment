import { useEffect, useState } from 'react'

import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { getAppointmentNotificationDeliveries } from '../../api/appointments'
import type { Appointment, NotificationDeliveryStatus } from '../../types'
import { formatAppointmentTime } from './form'

type Props = { item: Appointment | null; onClose: () => void }

const DELIVERY_CHIP_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  sent: 'success',
  scheduled: 'default',
  claimed: 'default',
  failed: 'error',
  skipped: 'warning',
  cancelled: 'default',
}

function DeliveryStatusList({ appointmentId }: { appointmentId: number }) {
  const [deliveries, setDeliveries] = useState<NotificationDeliveryStatus[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    getAppointmentNotificationDeliveries(appointmentId)
      .then((items) => {
        if (active) setDeliveries(items)
      })
      .catch(() => {
        if (active) setDeliveries([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [appointmentId])

  if (loading) return null
  if (deliveries.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No notification deliveries recorded yet.
      </Typography>
    )
  }
  return (
    <Stack spacing={0.75}>
      {deliveries.map((delivery) => (
        <Stack key={delivery.id} direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            label={delivery.status}
            color={DELIVERY_CHIP_COLOR[delivery.status] ?? 'default'}
          />
          <Typography variant="body2" color="text.secondary">
            {delivery.kind}
            {delivery.error_code ? ` — ${delivery.error_code}` : ''}
          </Typography>
        </Stack>
      ))}
    </Stack>
  )
}

export function AppointmentDetailsDialog({ item, onClose }: Props) {
  return (
    <Dialog open={Boolean(item)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Appointment details</DialogTitle>
      <DialogContent dividers>
        {item ? (
          <Stack spacing={1.5}>
            <Typography variant="body2">Summary: {item.summary}</Typography>
            <Typography variant="body2">Status: {item.status}</Typography>
            <Typography variant="body2">Start: {formatAppointmentTime(item.start_datetime)}</Typography>
            <Typography variant="body2">End: {formatAppointmentTime(item.end_datetime)}</Typography>
            <Typography variant="body2">Client: {item.client_name ?? '—'}</Typography>
            <Typography variant="body2">
              Sync: {item.provider_sync_status ?? 'unknown'}
              {item.google_calendar_link ? <Button href={item.google_calendar_link} target="_blank" rel="noopener noreferrer" size="small">Open in Google</Button> : null}
            </Typography>
            {item.notes ? <Typography variant="body2">Notes: {item.notes}</Typography> : null}
            <Box>
              <Typography variant="subtitle2" gutterBottom>Notification delivery</Typography>
              <DeliveryStatusList appointmentId={item.id} />
            </Box>
            {item.transcript ? (
              <Box>
                <Typography variant="subtitle2" gutterBottom>Voice transcript</Typography>
                <Typography component="pre" variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{item.transcript}</Typography>
              </Box>
            ) : <Typography variant="body2" color="text.secondary">No transcript on this appointment.</Typography>}
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  )
}
