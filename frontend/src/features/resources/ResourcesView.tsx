import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import {
  createResource,
  listResourceAvailability,
  listResourceCapabilities,
  listResources,
  type Resource,
} from '../../api/resources'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import { BookingPolicyPanel } from './BookingPolicyPanel'

const DETAIL_TABS = [
  'Overview',
  'Capabilities',
  'Working hours',
  'Service assignments',
  'Time off',
] as const

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function ResourcesView() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()

  const [section, setSection] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detailTab, setDetailTab] = useState(0)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [resourceType, setResourceType] = useState('practitioner')
  const [capacity, setCapacity] = useState('1')
  const [active, setActive] = useState(true)

  const resourcesQuery = useQuery({
    queryKey: queryKeys.resources.list,
    queryFn: () => listResources(),
  })

  const resources = resourcesQuery.data ?? []
  const q = query.trim().toLowerCase()
  const filtered = q
    ? resources.filter(
        (r) =>
          r.name.toLowerCase().includes(q) || r.resource_type.toLowerCase().includes(q),
      )
    : resources

  const effectiveSelectedId =
    selectedId != null && filtered.some((r) => r.id === selectedId)
      ? selectedId
      : (filtered[0]?.id ?? null)
  const selected: Resource | null =
    filtered.find((r) => r.id === effectiveSelectedId) ?? null

  const capsQuery = useQuery({
    queryKey: queryKeys.resources.capabilities(selected?.id ?? 0),
    queryFn: () => listResourceCapabilities(selected!.id),
    enabled: selected != null,
  })

  const availabilityQuery = useQuery({
    queryKey: queryKeys.resources.availability(selected?.id ?? 0),
    queryFn: () => listResourceAvailability(selected!.id),
    enabled: selected != null && detailTab === 2,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      createResource({
        name: name.trim(),
        resource_type: resourceType.trim(),
        capacity: Math.max(1, Number(capacity) || 1),
        active,
      }),
    onSuccess: (row) => {
      notify('Resource created', 'success')
      setCreateOpen(false)
      setName('')
      setResourceType('practitioner')
      setCapacity('1')
      setActive(true)
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

  const capabilities = capsQuery.data ?? []
  const rules = availabilityQuery.data ?? []

  const detail = selected ? (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="h3">{selected.name}</Typography>
        {!selected.active ? <Chip size="small" label="Inactive" /> : null}
      </Stack>
      <Tabs
        value={detailTab}
        onChange={(_, v: number) => setDetailTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Resource detail"
      >
        {DETAIL_TABS.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>
      {detailTab === 0 ? (
        <Stack spacing={1}>
          <Typography variant="body2">Type: {selected.resource_type}</Typography>
          <Typography variant="body2">Capacity: {selected.capacity}</Typography>
          <Typography variant="body2">
            Location: {selected.location_id != null ? `#${selected.location_id}` : '—'}
          </Typography>
        </Stack>
      ) : null}
      {detailTab === 1 ? (
        capsQuery.isPending ? (
          <CircularProgress size={20} />
        ) : (
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            {capabilities.length ? (
              capabilities.map((cap) => (
                <Chip key={cap.id} label={cap.capability} size="small" />
              ))
            ) : (
              <Typography variant="body2" color="text.secondary">
                No skill capabilities (equipment/pool).
              </Typography>
            )}
          </Stack>
        )
      ) : null}
      {detailTab === 2 ? (
        <Stack spacing={1.5}>
          {availabilityQuery.isPending ? (
            <CircularProgress size={20} />
          ) : rules.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No availability rules yet.
            </Typography>
          ) : (
            rules.map((rule) => (
              <Typography key={rule.id} variant="body2">
                {WEEKDAYS[rule.weekday] ?? `Day ${rule.weekday}`}: {rule.start_time}–
                {rule.end_time}
              </Typography>
            ))
          )}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
              gap: 0.5,
              border: '1px solid var(--border-subtle)',
              borderRadius: 1,
              p: 1,
            }}
          >
            {WEEKDAYS.map((d, i) => {
              const has = rules.some((r) => r.weekday === i)
              return (
                <Box
                  key={d}
                  sx={{
                    bgcolor: has ? 'rgba(62, 106, 225, 0.12)' : 'var(--surface-secondary)',
                    minHeight: 64,
                    borderRadius: 0.5,
                    p: 0.5,
                  }}
                >
                  <Typography variant="caption">{d.slice(0, 1)}</Typography>
                </Box>
              )
            })}
          </Box>
        </Stack>
      ) : null}
      {detailTab === 3 ? (
        <Typography variant="body2" color="text.secondary">
          Service ↔ resource requirements will list here once catalog APIs expose assignments.
        </Typography>
      ) : null}
      {detailTab === 4 ? (
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary">
            Exceptions / time off — add via form (drag optional later).
          </Typography>
          <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} disabled>
            Add time off
          </Button>
        </Stack>
      ) : null}
    </Stack>
  ) : (
    <Typography color="text.secondary">Select a resource.</Typography>
  )

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
        <Stack spacing={2}>
          <TextField
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search resources"
            fullWidth
            sx={{ maxWidth: 420 }}
          />
          {resourcesQuery.isPending ? (
            <CircularProgress size={28} />
          ) : filtered.length === 0 ? (
            <Typography color="text.secondary">No resources found.</Typography>
          ) : isMobile ? (
            <>
              <List disablePadding>
                {filtered.map((row) => (
                  <ListItemButton
                    key={row.id}
                    selected={selected?.id === row.id}
                    onClick={() => {
                      setSelectedId(row.id)
                      setMobileDetailOpen(true)
                    }}
                  >
                    <ListItemText
                      primary={row.name}
                      secondary={`${row.resource_type} · cap ${row.capacity}`}
                    />
                  </ListItemButton>
                ))}
              </List>
              <Dialog
                open={mobileDetailOpen}
                onClose={() => setMobileDetailOpen(false)}
                fullScreen
              >
                <DialogTitle>Resource</DialogTitle>
                <DialogContent dividers>{detail}</DialogContent>
                <DialogActions>
                  <Button onClick={() => setMobileDetailOpen(false)}>Close</Button>
                </DialogActions>
              </Dialog>
            </>
          ) : (
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { md: '280px 1fr' },
                gap: 2,
                alignItems: 'start',
              }}
            >
              <Box
                sx={{
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 1,
                  overflow: 'hidden',
                }}
              >
                <List disablePadding>
                  {filtered.map((row) => (
                    <ListItemButton
                      key={row.id}
                      selected={selected?.id === row.id}
                      onClick={() => setSelectedId(row.id)}
                    >
                      <ListItemText
                        primary={row.name}
                        secondary={`${row.resource_type} · cap ${row.capacity}`}
                      />
                    </ListItemButton>
                  ))}
                </List>
              </Box>
              <Box
                sx={{
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 1,
                  p: 2.5,
                  bgcolor: 'var(--surface-primary)',
                  minHeight: 320,
                }}
              >
                {detail}
              </Box>
            </Box>
          )}
        </Stack>
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
