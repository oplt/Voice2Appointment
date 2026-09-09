import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
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
  createResourceCapability,
  deleteResourceCapability,
  patchResourceCapability,
  type Resource,
} from '../../api/resources'
import { useSnackbar } from '../../components/SnackbarProvider'
import { useResourceCapabilitiesQuery } from './useResourcesQueries'

type CapabilitiesPanelProps = {
  resource: Resource
}

export function CapabilitiesPanel({ resource }: CapabilitiesPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [capabilityInput, setCapabilityInput] = useState('')
  const [editCapability, setEditCapability] = useState<{
    id: number
    capability: string
  } | null>(null)

  const capsQuery = useResourceCapabilitiesQuery(resource.id)
  const capabilities = capsQuery.data ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.resources.capabilities(resource.id),
    })
  }

  const addMutation = useMutation({
    mutationFn: () => createResourceCapability(resource.id, capabilityInput.trim()),
    onSuccess: () => {
      notify('Capability added', 'success')
      setCapabilityInput('')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add capability', 'error')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (capabilityId: number) =>
      deleteResourceCapability(resource.id, capabilityId),
    onSuccess: () => {
      notify('Capability removed', 'success')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to remove capability', 'error')
    },
  })

  const editMutation = useMutation({
    mutationFn: () => {
      if (!editCapability) throw new Error('No capability')
      return patchResourceCapability(
        resource.id,
        editCapability.id,
        editCapability.capability.trim(),
      )
    },
    onSuccess: () => {
      notify('Capability updated', 'success')
      setEditCapability(null)
      invalidate()
    },
    onError: (err: unknown) =>
      notify(err instanceof ApiError ? err.message : 'Update failed', 'error'),
  })

  return (
    <>
      <Stack spacing={2}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField
            label="Capability"
            value={capabilityInput}
            onChange={(e) => setCapabilityInput(e.target.value)}
            fullWidth
            placeholder="e.g. colorist, wheelchair"
          />
          <Button
            variant="contained"
            disabled={!capabilityInput.trim() || addMutation.isPending}
            onClick={() => addMutation.mutate()}
            sx={{ whiteSpace: 'nowrap' }}
          >
            Add
          </Button>
        </Stack>
        {capsQuery.isPending ? (
          <CircularProgress size={20} />
        ) : (
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            {capabilities.length ? (
              capabilities.map((cap) => (
                <Chip
                  key={cap.id}
                  label={cap.capability}
                  size="small"
                  onClick={() =>
                    setEditCapability({ id: cap.id, capability: cap.capability })
                  }
                  onDelete={() => deleteMutation.mutate(cap.id)}
                  deleteIcon={<DeleteOutlineIcon />}
                />
              ))
            ) : (
              <Typography variant="body2" color="text.secondary">
                No skill capabilities yet.
              </Typography>
            )}
          </Stack>
        )}
      </Stack>

      <Dialog
        open={editCapability != null}
        onClose={() => !editMutation.isPending && setEditCapability(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Edit capability</DialogTitle>
        <DialogContent dividers>
          <TextField
            label="Capability"
            value={editCapability?.capability ?? ''}
            onChange={(e) =>
              setEditCapability((value) =>
                value ? { ...value, capability: e.target.value } : value,
              )
            }
            fullWidth
            sx={{ mt: 1 }}
            required
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditCapability(null)} disabled={editMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!editCapability?.capability.trim() || editMutation.isPending}
            onClick={() => editMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
