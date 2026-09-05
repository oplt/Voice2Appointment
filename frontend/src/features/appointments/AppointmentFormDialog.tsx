import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import { useEffect, useState, type FormEvent } from 'react'

import { createAppointment, updateAppointment } from '../../api/appointments'
import { ApiError } from '../../api/client'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { Appointment } from '../../types'
import {
  appointmentForm,
  appointmentPayload,
  emptyAppointmentForm,
  type AppointmentFormState,
} from './form'

type Props = {
  open: boolean
  item: Appointment | null
  onClose: () => void
  onSaved: () => void
}

export function AppointmentFormDialog({ open, item, onClose, onSaved }: Props) {
  const { notify } = useSnackbar()
  const [form, setForm] = useState<AppointmentFormState>(emptyAppointmentForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setForm(item ? appointmentForm(item) : emptyAppointmentForm())
    setError(null)
  }, [item, open])

  const field = (name: keyof AppointmentFormState) => ({
    value: form[name],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [name]: event.target.value })),
  })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form.summary.trim() || !form.start_datetime || !form.end_datetime) {
      setError('Summary, start, and end are required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const payload = appointmentPayload(form)
      if (item) await updateAppointment(item.id, payload)
      else await createAppointment(payload)
      notify(item ? 'Appointment updated' : 'Appointment created', 'success')
      onSaved()
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>{item ? 'Reschedule / edit' : 'New appointment'}</DialogTitle>
      <DialogContent>
        <Stack component="form" id="appointment-form" onSubmit={submit} spacing={2} sx={{ mt: 1 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField label="Summary" {...field('summary')} required fullWidth autoFocus />
          <TextField label="Description" {...field('description')} fullWidth multiline minRows={2} />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField label="Start" type="datetime-local" {...field('start_datetime')} required fullWidth slotProps={{ inputLabel: { shrink: true } }} />
            <TextField label="End" type="datetime-local" {...field('end_datetime')} required fullWidth slotProps={{ inputLabel: { shrink: true } }} />
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField label="Timezone" {...field('timezone')} fullWidth />
            <TextField label="Status" select {...field('status')} fullWidth>
              {['pending', 'confirmed', 'cancelled', 'completed'].map((status) => <MenuItem key={status} value={status}>{status}</MenuItem>)}
            </TextField>
          </Stack>
          <TextField label="Client name" {...field('client_name')} fullWidth />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField label="Client phone" {...field('client_phone')} fullWidth />
            <TextField label="Client email" type="email" {...field('client_email')} fullWidth />
          </Stack>
          <TextField label="Notes" {...field('notes')} fullWidth multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button type="submit" form="appointment-form" variant="contained" loading={saving}>
          {item ? 'Save' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
