import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import {
  createResourceAvailabilityException,
  deleteResourceAvailabilityException,
  patchResourceAvailabilityException,
  type AvailabilityException,
  type Resource,
} from '../../api/resources'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useSnackbar } from '../../components/SnackbarProvider'
import {
  fromDatetimeLocalValue,
  toDatetimeLocalValue,
  useResourceExceptionsQuery,
} from './useResourcesQueries'

type TimeOffPanelProps = {
  resource: Resource
}

export function TimeOffPanel({ resource }: TimeOffPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const exceptionsQuery = useResourceExceptionsQuery(resource.id, true)
  const exceptions: AvailabilityException[] = exceptionsQuery.data ?? []

  const [timeOffOpen, setTimeOffOpen] = useState(false)
  const [timeOffStart, setTimeOffStart] = useState('')
  const [timeOffEnd, setTimeOffEnd] = useState('')
  const [timeOffReason, setTimeOffReason] = useState('')
  const [editTimeOff, setEditTimeOff] = useState<AvailabilityException | null>(null)
  const [deleteTimeOff, setDeleteTimeOff] = useState<AvailabilityException | null>(null)

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.resources.exceptions(resource.id),
    })
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createResourceAvailabilityException(resource.id, {
        starts_at: fromDatetimeLocalValue(timeOffStart),
        ends_at: fromDatetimeLocalValue(timeOffEnd),
        available: false,
        reason: timeOffReason.trim() || null,
      }),
    onSuccess: () => {
      notify('Time off added', 'success')
      setTimeOffOpen(false)
      setTimeOffStart('')
      setTimeOffEnd('')
      setTimeOffReason('')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add time off', 'error')
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editTimeOff) throw new Error('No time off')
      return patchResourceAvailabilityException(resource.id, editTimeOff.id, {
        starts_at: fromDatetimeLocalValue(timeOffStart),
        ends_at: fromDatetimeLocalValue(timeOffEnd),
        reason: timeOffReason.trim() || null,
      })
    },
    onSuccess: () => {
      notify('Time off updated', 'success')
      setEditTimeOff(null)
      setTimeOffOpen(false)
      invalidate()
    },
    onError: (err: unknown) =>
      notify(err instanceof ApiError ? err.message : 'Update failed', 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!deleteTimeOff) throw new Error('No time off')
      return deleteResourceAvailabilityException(resource.id, deleteTimeOff.id)
    },
    onSuccess: () => {
      notify('Time off removed', 'success')
      setDeleteTimeOff(null)
      invalidate()
    },
    onError: (err: unknown) =>
      notify(err instanceof ApiError ? err.message : 'Delete failed', 'error'),
  })

  const closeDialog = () => {
    setTimeOffOpen(false)
    setEditTimeOff(null)
  }

  return (
    <>
      <Stack spacing={1.5}>
        <Button
          variant="outlined"
          sx={{ alignSelf: 'flex-start' }}
          onClick={() => {
            setEditTimeOff(null)
            setTimeOffStart('')
            setTimeOffEnd('')
            setTimeOffReason('')
            setTimeOffOpen(true)
          }}
        >
          Add time off
        </Button>
        {exceptionsQuery.isPending ? (
          <CircularProgress size={20} />
        ) : exceptions.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No time-off exceptions yet.
          </Typography>
        ) : (
          exceptions.map((exc) => (
            <Box
              key={exc.id}
              sx={{
                border: '1px solid var(--border-subtle)',
                borderRadius: 1,
                p: 1.5,
              }}
            >
              <Typography variant="body2">
                {toDatetimeLocalValue(exc.starts_at).replace('T', ' ')} →{' '}
                {toDatetimeLocalValue(exc.ends_at).replace('T', ' ')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {exc.available ? 'Available override' : 'Unavailable'}
                {exc.reason ? ` · ${exc.reason}` : ''}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button
                  size="small"
                  onClick={() => {
                    setEditTimeOff(exc)
                    setTimeOffStart(toDatetimeLocalValue(exc.starts_at))
                    setTimeOffEnd(toDatetimeLocalValue(exc.ends_at))
                    setTimeOffReason(exc.reason ?? '')
                    setTimeOffOpen(true)
                  }}
                >
                  Edit
                </Button>
                <Button size="small" color="error" onClick={() => setDeleteTimeOff(exc)}>
                  Delete
                </Button>
              </Stack>
            </Box>
          ))
        )}
      </Stack>

      <Dialog
        open={timeOffOpen}
        onClose={() =>
          !(editTimeOff ? updateMutation.isPending : createMutation.isPending) &&
          closeDialog()
        }
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{editTimeOff ? 'Edit time off' : 'Add time off'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Starts at"
              type="datetime-local"
              value={timeOffStart}
              onChange={(e) => setTimeOffStart(e.target.value)}
              fullWidth
              slotProps={{ inputLabel: { shrink: true } }}
              required
            />
            <TextField
              label="Ends at"
              type="datetime-local"
              value={timeOffEnd}
              onChange={(e) => setTimeOffEnd(e.target.value)}
              fullWidth
              slotProps={{ inputLabel: { shrink: true } }}
              required
            />
            <TextField
              label="Reason"
              value={timeOffReason}
              onChange={(e) => setTimeOffReason(e.target.value)}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={closeDialog}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              !timeOffStart ||
              !timeOffEnd ||
              createMutation.isPending ||
              updateMutation.isPending
            }
            onClick={() =>
              editTimeOff ? updateMutation.mutate() : createMutation.mutate()
            }
          >
            {editTimeOff ? 'Save' : 'Add'}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteTimeOff != null}
        title="Delete time off?"
        description="This time-off exception will be removed."
        confirmLabel="Delete"
        confirmColor="error"
        loading={deleteMutation.isPending}
        onClose={() => !deleteMutation.isPending && setDeleteTimeOff(null)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </>
  )
}
