import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import MenuItem from '@mui/material/MenuItem'
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

import {
  listCatalogItems,
  listResourceRequirements,
  putResourceRequirements,
  type ResourceRequirementInput,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import {
  createResource,
  createResourceAvailabilityException,
  createResourceCapability,
  deleteResourceCapability,
  listResourceAvailability,
  listResourceAvailabilityExceptions,
  listResourceCapabilities,
  listResources,
  type AvailabilityException,
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

function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString()
}

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

  const [capabilityInput, setCapabilityInput] = useState('')
  const [timeOffOpen, setTimeOffOpen] = useState(false)
  const [timeOffStart, setTimeOffStart] = useState('')
  const [timeOffEnd, setTimeOffEnd] = useState('')
  const [timeOffReason, setTimeOffReason] = useState('')

  const [assignServiceId, setAssignServiceId] = useState<number | ''>('')
  const [reqDrafts, setReqDrafts] = useState<ResourceRequirementInput[]>([])

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

  const exceptionsQuery = useQuery({
    queryKey: queryKeys.resources.exceptions(selected?.id ?? 0),
    queryFn: () => listResourceAvailabilityExceptions(selected!.id),
    enabled: selected != null && detailTab === 4,
  })

  const servicesQuery = useQuery({
    queryKey: queryKeys.catalog.items({ forResourceAssign: true, kind: 'service' }),
    queryFn: () => listCatalogItems({ kind: 'service', limit: 100, active: true }),
    enabled: detailTab === 3,
  })

  const requirementsQuery = useQuery({
    queryKey: queryKeys.catalog.requirements(assignServiceId === '' ? 0 : assignServiceId),
    queryFn: () => listResourceRequirements(assignServiceId as number),
    enabled: detailTab === 3 && assignServiceId !== '',
  })

  const services = servicesQuery.data?.items ?? []
  const linkedServices = services.filter((svc) => svc.bookable || svc.kind === 'service')

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

  const addCapabilityMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('No resource')
      return createResourceCapability(selected.id, capabilityInput.trim())
    },
    onSuccess: () => {
      notify('Capability added', 'success')
      setCapabilityInput('')
      void queryClient.invalidateQueries({
        queryKey: queryKeys.resources.capabilities(selected!.id),
      })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add capability', 'error')
    },
  })

  const deleteCapabilityMutation = useMutation({
    mutationFn: (capabilityId: number) => {
      if (!selected) throw new Error('No resource')
      return deleteResourceCapability(selected.id, capabilityId)
    },
    onSuccess: () => {
      notify('Capability removed', 'success')
      void queryClient.invalidateQueries({
        queryKey: queryKeys.resources.capabilities(selected!.id),
      })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to remove capability', 'error')
    },
  })

  const timeOffMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('No resource')
      return createResourceAvailabilityException(selected.id, {
        starts_at: fromDatetimeLocalValue(timeOffStart),
        ends_at: fromDatetimeLocalValue(timeOffEnd),
        available: false,
        reason: timeOffReason.trim() || null,
      })
    },
    onSuccess: () => {
      notify('Time off added', 'success')
      setTimeOffOpen(false)
      setTimeOffStart('')
      setTimeOffEnd('')
      setTimeOffReason('')
      void queryClient.invalidateQueries({
        queryKey: queryKeys.resources.exceptions(selected!.id),
      })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add time off', 'error')
    },
  })

  const saveRequirementsMutation = useMutation({
    mutationFn: () => {
      if (assignServiceId === '') throw new Error('No service')
      const payload = reqDrafts.length
        ? reqDrafts
        : [
            {
              resource_type: selected?.resource_type ?? null,
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

  const listError =
    resourcesQuery.error == null
      ? null
      : resourcesQuery.error instanceof ApiError
        ? resourcesQuery.error.message
        : 'Failed to load resources'

  const capabilities = capsQuery.data ?? []
  const rules = availabilityQuery.data ?? []
  const exceptions: AvailabilityException[] = exceptionsQuery.data ?? []

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
    } else if (selected) {
      setReqDrafts([
        {
          resource_type: selected.resource_type,
          capability: null,
          quantity: 1,
          required: true,
        },
      ])
    }
  }

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
              disabled={!capabilityInput.trim() || addCapabilityMutation.isPending}
              onClick={() => addCapabilityMutation.mutate()}
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
                    onDelete={() => deleteCapabilityMutation.mutate(cap.id)}
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
                      next[idx] = { ...draft, quantity: Math.max(1, Number(e.target.value) || 1) }
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
                        resource_type: selected.resource_type,
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
                  disabled={saveRequirementsMutation.isPending}
                  onClick={() => saveRequirementsMutation.mutate()}
                >
                  Save requirements
                </Button>
              </Stack>
            </>
          ) : null}
        </Stack>
      ) : null}
      {detailTab === 4 ? (
        <Stack spacing={1.5}>
          <Button
            variant="outlined"
            sx={{ alignSelf: 'flex-start' }}
            onClick={() => setTimeOffOpen(true)}
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
              </Box>
            ))
          )}
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

      <Dialog
        open={timeOffOpen}
        onClose={() => !timeOffMutation.isPending && setTimeOffOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Add time off</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Starts at"
              type="datetime-local"
              value={timeOffStart}
              onChange={(e) => setTimeOffStart(e.target.value)}
              fullWidth
              InputLabelProps={{ shrink: true }}
              required
            />
            <TextField
              label="Ends at"
              type="datetime-local"
              value={timeOffEnd}
              onChange={(e) => setTimeOffEnd(e.target.value)}
              fullWidth
              InputLabelProps={{ shrink: true }}
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
          <Button onClick={() => setTimeOffOpen(false)} disabled={timeOffMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!timeOffStart || !timeOffEnd || timeOffMutation.isPending}
            onClick={() => timeOffMutation.mutate()}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
