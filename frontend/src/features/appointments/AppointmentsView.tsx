import AddIcon from '@mui/icons-material/Add'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import { useRef, useState } from 'react'

import { deleteAppointment, getAppointment } from '../../api/appointments'
import { ApiError } from '../../api/client'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { Appointment, AppointmentListItem } from '../../types'
import { AppointmentDetailsDialog } from './AppointmentDetailsDialog'
import { AppointmentFormDialog } from './AppointmentFormDialog'
import { AppointmentList } from './AppointmentList'
import { useAppointmentsList } from './useAppointmentsList'

export function AppointmentsView() {
  const list = useAppointmentsList()
  const { notify } = useSnackbar()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Appointment | null>(null)
  const [detail, setDetail] = useState<Appointment | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AppointmentListItem | null>(null)
  const [deleting, setDeleting] = useState(false)
  const detailRequest = useRef(0)

  const openForm = (item: Appointment | null) => {
    setEditing(item)
    setFormOpen(true)
  }
  const saved = () => {
    setFormOpen(false)
    void list.refresh()
  }
  const loadAppointment = async (
    item: AppointmentListItem,
    onLoaded: (appointment: Appointment) => void,
  ) => {
    const request = ++detailRequest.current
    try {
      const appointment = await getAppointment(item.id)
      if (request === detailRequest.current) onLoaded(appointment)
    } catch (caught: unknown) {
      if (request === detailRequest.current) {
        notify(caught instanceof ApiError ? caught.message : 'Could not load appointment details', 'error')
      }
    }
  }
  const closeDetail = () => {
    detailRequest.current += 1
    setDetail(null)
  }
  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteAppointment(deleteTarget.id)
      notify('Appointment cancelled', 'success')
      setDeleteTarget(null)
      await list.refresh()
    } catch (caught: unknown) {
      notify(caught instanceof ApiError ? caught.message : 'Cancel failed', 'error')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Appointments"
        subtitle="Create, reschedule, and cancel booked slots."
        actions={<Button variant="contained" startIcon={<AddIcon />} onClick={() => openForm(null)}>New appointment</Button>}
      />
      <AppointmentList
        {...list}
        hasMore={Boolean(list.nextCursor)}
        onScope={list.setScope}
        onRetry={() => void list.refresh()}
        onLoadMore={() => void list.loadMore()}
        onView={(item) => void loadAppointment(item, setDetail)}
        onEdit={(item) => void loadAppointment(item, openForm)}
        onCancel={setDeleteTarget}
      />
      <AppointmentFormDialog open={formOpen} item={editing} onClose={() => setFormOpen(false)} onSaved={saved} />
      <AppointmentDetailsDialog item={detail} onClose={closeDetail} />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Cancel appointment?"
        description={deleteTarget ? `“${deleteTarget.summary}” will be marked cancelled.` : undefined}
        confirmLabel="Cancel appointment"
        confirmColor="error"
        loading={deleting}
        onClose={() => { if (!deleting) setDeleteTarget(null) }}
        onConfirm={() => void confirmDelete()}
      />
    </Stack>
  )
}
