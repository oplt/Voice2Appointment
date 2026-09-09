import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { createResource } from '../../api/resources'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import { BookingPolicyPanel } from './BookingPolicyPanel'
import { ResourceListPane } from './ResourceListPane'
import {
  useResourceLocationsQuery,
  useResourcesListQuery,
} from './useResourcesQueries'

export function ResourcesView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()

  const [section, setSection] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [resourceType, setResourceType] = useState('practitioner')
  const [capacity, setCapacity] = useState('1')
  const [active, setActive] = useState(true)
  const [locationId, setLocationId] = useState('')

  const resourcesQuery = useResourcesListQuery()
  const locationsQuery = useResourceLocationsQuery()
  const resources = resourcesQuery.data ?? []
  const locations = locationsQuery.data ?? []

  const createMutation = useMutation({
    mutationFn: () =>
      createResource({
        name: name.trim(),
        resource_type: resourceType.trim(),
        capacity: Math.max(1, Number(capacity) || 1),
        active,
        location_id: locationId ? Number(locationId) : null,
      }),
    onSuccess: (row) => {
      notify('Resource created', 'success')
      setCreateOpen(false)
      setName('')
      setResourceType('practitioner')
      setCapacity('1')
      setActive(true)
      setLocationId('')
      setSelectedId(row.id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Create failed', 'error')
    },
  })

  const listError =
    resourcesQuery.error == null
      ? null
      : resourcesQuery.error instanceof ApiError
        ? resourcesQuery.error.message
        : 'Failed to load resources'

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Resources"
        subtitle="Staff, rooms, equipment, and capacity pools."
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setCreateOpen(true)}
          >
            New resource
          </Button>
        }
      />

      {listError ? <Alert severity="error">{listError}</Alert> : null}

      <Tabs
        value={section}
        onChange={(_, v: number) => setSection(v)}
        aria-label="Resources sections"
      >
        <Tab label="Directory" />
        <Tab label="Business hours" />
      </Tabs>

      {section === 1 ? <BookingPolicyPanel /> : null}

      {section === 0 ? (
        <ResourceListPane
          resources={resources}
          loading={resourcesQuery.isPending}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      ) : null}

      <Dialog
        open={createOpen}
        onClose={() => !createMutation.isPending && setCreateOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>New resource</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Type"
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value)}
              fullWidth
              required
              helperText="e.g. practitioner, chair, capacity_pool"
            />
            <TextField
              label="Capacity"
              type="number"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              fullWidth
            />
            <TextField
              select
              label="Location"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
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
                <Switch checked={active} onChange={(e) => setActive(e.target.checked)} />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!name.trim() || !resourceType.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
