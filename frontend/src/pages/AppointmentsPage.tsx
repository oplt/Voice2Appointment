import AddIcon from '@mui/icons-material/Add'
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import MenuItem from '@mui/material/MenuItem'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import {
  createAppointment,
  deleteAppointment,
  listAppointments,
  updateAppointment,
} from '../api/appointments'
import { ApiError } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'
import { useSnackbar } from '../components/SnackbarProvider'
import type { Appointment, AppointmentCreate } from '../types'

type FormState = {
  summary: string
  description: string
  start_datetime: string
  end_datetime: string
  timezone: string
  status: string
  client_name: string
  client_phone: string
  client_email: string
  notes: string
}

const emptyForm = (): FormState => ({
  summary: '',
  description: '',
  start_datetime: '',
  end_datetime: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  status: 'pending',
  client_name: '',
  client_phone: '',
  client_email: '',
  notes: '',
})

function toLocalInputValue(iso: string) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromLocalInputValue(value: string) {
  if (!value) return ''
  return new Date(value).toISOString()
}

function formFromAppointment(a: Appointment): FormState {
  return {
    summary: a.summary,
    description: a.description ?? '',
    start_datetime: toLocalInputValue(a.start_datetime),
    end_datetime: toLocalInputValue(a.end_datetime),
    timezone: a.timezone || 'UTC',
    status: a.status || 'pending',
    client_name: a.client_name ?? '',
    client_phone: a.client_phone ?? '',
    client_email: a.client_email ?? '',
    notes: a.notes ?? '',
  }
}

function toPayload(form: FormState): AppointmentCreate {
  return {
    summary: form.summary.trim(),
    description: form.description.trim() || null,
    start_datetime: fromLocalInputValue(form.start_datetime),
    end_datetime: fromLocalInputValue(form.end_datetime),
    timezone: form.timezone.trim() || 'UTC',
    status: form.status,
    client_name: form.client_name.trim() || null,
    client_phone: form.client_phone.trim() || null,
    client_email: form.client_email.trim() || null,
    notes: form.notes.trim() || null,
  }
}

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

export function AppointmentsPage() {
  const { notify } = useSnackbar()
  const [items, setItems] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Appointment | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<Appointment | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    listAppointments()
      .then(setItems)
      .catch((err: unknown) => {
        setItems([])
        setError(err instanceof ApiError ? err.message : 'Failed to load appointments')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm())
    setFormError(null)
    setDialogOpen(true)
  }

  const openEdit = (item: Appointment) => {
    setEditing(item)
    setForm(formFromAppointment(item))
    setFormError(null)
    setDialogOpen(true)
  }

  const closeDialog = () => {
    if (saving) return
    setDialogOpen(false)
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    if (!form.summary.trim() || !form.start_datetime || !form.end_datetime) {
      setFormError('Summary, start, and end are required')
      return
    }
    const payload = toPayload(form)
    setSaving(true)
    try {
      if (editing) {
        await updateAppointment(editing.id, payload)
        notify('Appointment updated', 'success')
      } else {
        await createAppointment(payload)
        notify('Appointment created', 'success')
      }
      setDialogOpen(false)
      load()
    } catch (err: unknown) {
      setFormError(err instanceof ApiError ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteAppointment(deleteTarget.id)
      notify('Appointment deleted', 'success')
      setDeleteTarget(null)
      load()
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Delete failed', 'error')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Appointments"
        subtitle="Create, reschedule, and cancel booked slots."
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
            New appointment
          </Button>
        }
      />

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <Stack spacing={1}>
          <Skeleton variant="rounded" height={40} />
          <Skeleton variant="rounded" height={40} />
          <Skeleton variant="rounded" height={40} />
        </Stack>
      ) : items.length === 0 && !error ? (
        <Alert severity="info">
          No appointments yet. Create one to sync with your calendar.
        </Alert>
      ) : items.length > 0 ? (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Summary</TableCell>
              <TableCell>Start</TableCell>
              <TableCell>Client</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} hover>
                <TableCell>
                  <Typography variant="body2">{item.summary}</Typography>
                </TableCell>
                <TableCell>{formatWhen(item.start_datetime)}</TableCell>
                <TableCell>{item.client_name ?? '—'}</TableCell>
                <TableCell>{item.status}</TableCell>
                <TableCell align="right">
                  <Tooltip title="Edit">
                    <IconButton
                      aria-label={`Edit appointment ${item.summary}`}
                      size="small"
                      onClick={() => openEdit(item)}
                    >
                      <EditOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton
                      aria-label={`Delete appointment ${item.summary}`}
                      size="small"
                      onClick={() => setDeleteTarget(item)}
                    >
                      <DeleteOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}

      <Dialog open={dialogOpen} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? 'Edit appointment' : 'New appointment'}</DialogTitle>
        <DialogContent>
          <Stack component="form" id="appointment-form" onSubmit={onSubmit} spacing={2} sx={{ mt: 1 }}>
            {formError ? <Alert severity="error">{formError}</Alert> : null}
            <TextField
              label="Summary"
              value={form.summary}
              onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
              required
              fullWidth
              autoFocus
            />
            <TextField
              label="Description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Start"
                type="datetime-local"
                value={form.start_datetime}
                onChange={(e) => setForm((f) => ({ ...f, start_datetime: e.target.value }))}
                required
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="End"
                type="datetime-local"
                value={form.end_datetime}
                onChange={(e) => setForm((f) => ({ ...f, end_datetime: e.target.value }))}
                required
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Timezone"
                value={form.timezone}
                onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Status"
                select
                value={form.status}
                onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
                fullWidth
              >
                {['pending', 'confirmed', 'cancelled', 'completed'].map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Client name"
              value={form.client_name}
              onChange={(e) => setForm((f) => ({ ...f, client_name: e.target.value }))}
              fullWidth
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Client phone"
                value={form.client_phone}
                onChange={(e) => setForm((f) => ({ ...f, client_phone: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Client email"
                type="email"
                value={form.client_email}
                onChange={(e) => setForm((f) => ({ ...f, client_email: e.target.value }))}
                fullWidth
              />
            </Stack>
            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeDialog} disabled={saving} variant="text">
            Cancel
          </Button>
          <Button type="submit" form="appointment-form" variant="contained" loading={saving}>
            {editing ? 'Save' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete appointment?"
        description={
          deleteTarget
            ? `“${deleteTarget.summary}” will be permanently removed.`
            : undefined
        }
        confirmLabel="Delete"
        confirmColor="error"
        loading={deleting}
        onClose={() => {
          if (!deleting) setDeleteTarget(null)
        }}
        onConfirm={confirmDelete}
      />
    </Stack>
  )
}
