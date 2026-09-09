import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { patchResource, type Resource } from '../../api/resources'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useSnackbar } from '../../components/SnackbarProvider'
import { useResourceLocationsQuery } from './useResourcesQueries'

type ResourceOverviewPanelProps = {
  resource: Resource
}

export function ResourceOverviewPanel({ resource }: ResourceOverviewPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const locationsQuery = useResourceLocationsQuery()
  const locations = locationsQuery.data ?? []

  const [editOpen, setEditOpen] = useState(false)
  const [editName, setEditName] = useState('')
  const [editType, setEditType] = useState('')
  const [editCapacity, setEditCapacity] = useState('1')
  const [editLocationId, setEditLocationId] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [forceDeactivate, setForceDeactivate] = useState(false)

  const updateMutation = useMutation({
    mutationFn: (force: boolean = false) =>
      patchResource(
        resource.id,
        {
          name: editName.trim(),
          resource_type: editType.trim(),
          capacity: Math.max(1, Number(editCapacity) || 1),
          location_id: editLocationId ? Number(editLocationId) : null,
          active: editActive,
        },
        { force },
      ),
    onSuccess: () => {
      notify('Resource updated', 'success')
      setEditOpen(false)
      setForceDeactivate(false)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.all })
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.status === 409) {
        setForceDeactivate(true)
        return
      }
      notify(err instanceof ApiError ? err.message : 'Update failed', 'error')
    },
  })

  const openEdit = () => {
    setEditName(resource.name)
    setEditType(resource.resource_type)
    setEditCapacity(String(resource.capacity))
    setEditLocationId(resource.location_id != null ? String(resource.location_id) : '')
    setEditActive(resource.active)
    setEditOpen(true)
  }

  return (
    <>
      <Stack spacing={1}>
        <Typography variant="body2">Type: {resource.resource_type}</Typography>
        <Typography variant="body2">Capacity: {resource.capacity}</Typography>
        <Typography variant="body2">
          Location:{' '}
          {resource.location_id != null
            ? (locations.find((location) => location.id === resource.location_id)?.name ??
              `#${resource.location_id}`)
            : '—'}
        </Typography>
        <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} onClick={openEdit}>
          Edit resource
        </Button>
      </Stack>

      <Dialog
        open={editOpen}
        onClose={() => !updateMutation.isPending && setEditOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Edit resource</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Type"
              value={editType}
              onChange={(e) => setEditType(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Capacity"
              type="number"
              value={editCapacity}
              onChange={(e) => setEditCapacity(e.target.value)}
              slotProps={{ htmlInput: { min: 1 } }}
              fullWidth
            />
            <TextField
              select
              label="Location"
              value={editLocationId}
              onChange={(e) => setEditLocationId(e.target.value)}
              fullWidth
            >
              <MenuItem value="">No specific location</MenuItem>
              {locations.map((location) => (
                <MenuItem key={location.id} value={location.id}>
                  {location.name}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)} disabled={updateMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!editName.trim() || !editType.trim() || updateMutation.isPending}
            onClick={() => updateMutation.mutate(false)}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={forceDeactivate}
        title="Deactivate despite future reservations?"
        description="Future held or confirmed reservations use this resource. Deactivation may require those bookings to be reassigned."
        confirmLabel="Deactivate anyway"
        confirmColor="error"
        loading={updateMutation.isPending}
        onClose={() => !updateMutation.isPending && setForceDeactivate(false)}
        onConfirm={() => updateMutation.mutate(true)}
      />
    </>
  )
}
