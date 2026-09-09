import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  putResourceRequirements,
  type ResourceRequirementInput,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import type { Resource } from '../../api/resources'
import { useSnackbar } from '../../components/SnackbarProvider'
import {
  useAssignableServicesQuery,
  useServiceRequirementsQuery,
} from './useResourcesQueries'

type ServiceAssignmentsPanelProps = {
  resource: Resource
}

export function ServiceAssignmentsPanel({ resource }: ServiceAssignmentsPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [assignServiceId, setAssignServiceId] = useState<number | ''>('')
  const [reqDrafts, setReqDrafts] = useState<ResourceRequirementInput[]>([])

  const servicesQuery = useAssignableServicesQuery(true)
  const requirementsQuery = useServiceRequirementsQuery(assignServiceId, true)
  const services = servicesQuery.data?.items ?? []
  const linkedServices = services.filter((svc) => svc.bookable || svc.kind === 'service')

  const saveMutation = useMutation({
    mutationFn: () => {
      if (assignServiceId === '') throw new Error('No service')
      const payload = reqDrafts.length
        ? reqDrafts
        : [
            {
              resource_type: resource.resource_type,
              capability: null,
              quantity: 1,
              required: true,
            },
          ]
      return putResourceRequirements(assignServiceId, payload)
    },
    onSuccess: () => {
      notify('Service requirements saved', 'success')
      void queryClient.invalidateQueries({
        queryKey: queryKeys.catalog.requirements(assignServiceId as number),
      })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to save requirements', 'error')
    },
  })

  const loadRequirementsIntoDraft = () => {
    const rows = requirementsQuery.data ?? []
    if (rows.length) {
      setReqDrafts(
        rows.map((r) => ({
          resource_type: r.resource_type,
          capability: r.capability,
          quantity: r.quantity,
          required: r.required,
        })),
      )
    } else {
      setReqDrafts([
        {
          resource_type: resource.resource_type,
          capability: null,
          quantity: 1,
          required: true,
        },
      ])
    }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Link this resource type to a catalog service via resource requirements.
      </Typography>
      <TextField
        select
        label="Service"
        value={assignServiceId}
        onChange={(e) => {
          const next = e.target.value === '' ? '' : Number(e.target.value)
          setAssignServiceId(next)
          setReqDrafts([])
        }}
        fullWidth
      >
        <MenuItem value="">Select a service</MenuItem>
        {linkedServices.map((svc) => (
          <MenuItem key={svc.id} value={svc.id}>
            {svc.name}
          </MenuItem>
        ))}
      </TextField>
      {assignServiceId !== '' ? (
        <>
          {requirementsQuery.isPending ? (
            <CircularProgress size={20} />
          ) : (
            <Button
              variant="outlined"
              sx={{ alignSelf: 'flex-start' }}
              onClick={loadRequirementsIntoDraft}
            >
              Load current requirements
            </Button>
          )}
          {reqDrafts.map((draft, idx) => (
            <Stack
              key={idx}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              sx={{ alignItems: { sm: 'center' } }}
            >
              <TextField
                label="Resource type"
                value={draft.resource_type ?? ''}
                onChange={(e) => {
                  const next = [...reqDrafts]
                  next[idx] = { ...draft, resource_type: e.target.value || null }
                  setReqDrafts(next)
                }}
                fullWidth
              />
              <TextField
                label="Capability"
                value={draft.capability ?? ''}
                onChange={(e) => {
                  const next = [...reqDrafts]
                  next[idx] = { ...draft, capability: e.target.value || null }
                  setReqDrafts(next)
                }}
                fullWidth
              />
              <TextField
                label="Qty"
                type="number"
                value={draft.quantity ?? 1}
                onChange={(e) => {
                  const next = [...reqDrafts]
                  next[idx] = {
                    ...draft,
                    quantity: Math.max(1, Number(e.target.value) || 1),
                  }
                  setReqDrafts(next)
                }}
                sx={{ width: 100 }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={draft.required !== false}
                    onChange={(e) => {
                      const next = [...reqDrafts]
                      next[idx] = { ...draft, required: e.target.checked }
                      setReqDrafts(next)
                    }}
                  />
                }
                label="Required"
              />
              <IconButton
                aria-label="Remove requirement"
                onClick={() => setReqDrafts(reqDrafts.filter((_, i) => i !== idx))}
              >
                <DeleteOutlineIcon />
              </IconButton>
            </Stack>
          ))}
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              onClick={() =>
                setReqDrafts([
                  ...reqDrafts,
                  {
                    resource_type: resource.resource_type,
                    capability: null,
                    quantity: 1,
                    required: true,
                  },
                ])
              }
            >
              Add requirement row
            </Button>
            <Button
              variant="contained"
              disabled={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              Save requirements
            </Button>
          </Stack>
        </>
      ) : null}
    </Stack>
  )
}
