import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
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
  deleteResourceAvailability,
  deleteResourceAvailabilityException,
  deleteResourceCapability,
  listResourceAvailability,
  listResourceAvailabilityExceptions,
  listResourceCapabilities,
  listResources,
  patchResource,
  patchResourceAvailability,
  patchResourceAvailabilityException,
  patchResourceCapability,
  createResourceAvailability,
  type AvailabilityRule,
  type AvailabilityException,
  type Resource,
} from '../../api/resources'
import { listLocations } from '../../api/pricing'
import { ConfirmDialog } from '../../components/ConfirmDialog'
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
  const [locationId, setLocationId] = useState('')
  const [editResource, setEditResource] = useState<Resource | null>(null)
  const [editName, setEditName] = useState('')
  const [editType, setEditType] = useState('')
  const [editCapacity, setEditCapacity] = useState('1')
  const [editLocationId, setEditLocationId] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [forceDeactivate, setForceDeactivate] = useState(false)

  const [capabilityInput, setCapabilityInput] = useState('')
  const [editCapability, setEditCapability] = useState<{ id: number; capability: string } | null>(null)
  const [timeOffOpen, setTimeOffOpen] = useState(false)
  const [timeOffStart, setTimeOffStart] = useState('')
  const [timeOffEnd, setTimeOffEnd] = useState('')
  const [timeOffReason, setTimeOffReason] = useState('')
  const [editTimeOff, setEditTimeOff] = useState<AvailabilityException | null>(null)
  const [deleteTimeOff, setDeleteTimeOff] = useState<AvailabilityException | null>(null)

  const [ruleOpen, setRuleOpen] = useState(false)
  const [editRule, setEditRule] = useState<AvailabilityRule | null>(null)
  const [deleteRule, setDeleteRule] = useState<AvailabilityRule | null>(null)
  const [ruleWeekday, setRuleWeekday] = useState('0')
  const [ruleStart, setRuleStart] = useState('09:00')
  const [ruleEnd, setRuleEnd] = useState('17:00')

  const [assignServiceId, setAssignServiceId] = useState<number | ''>('')
  const [reqDrafts, setReqDrafts] = useState<ResourceRequirementInput[]>([])

  const resourcesQuery = useQuery({
    queryKey: queryKeys.resources.list,
    queryFn: () => listResources({ include_inactive: true }),
  })

  const locationsQuery = useQuery({
    queryKey: queryKeys.pricing.locations,
    queryFn: listLocations,
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

  const updateResourceMutation = useMutation({
    mutationFn: (force: boolean = false) => {
      if (!editResource) throw new Error('No resource')
      return patchResource(
        editResource.id,
        {
          name: editName.trim(),
          resource_type: editType.trim(),
          capacity: Math.max(1, Number(editCapacity) || 1),
          location_id: editLocationId ? Number(editLocationId) : null,
          active: editActive,
        },
        { force },
      )
    },
    onSuccess: () => {
      notify('Resource updated', 'success')
      setEditResource(null)
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

  const editCapabilityMutation = useMutation({
    mutationFn: () => {
      if (!selected || !editCapability) throw new Error('No capability')
      return patchResourceCapability(selected.id, editCapability.id, editCapability.capability.trim())
    },
    onSuccess: () => {
      notify('Capability updated', 'success')
      setEditCapability(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.capabilities(selected!.id) })
    },
    onError: (err: unknown) => notify(err instanceof ApiError ? err.message : 'Update failed', 'error'),
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

  const updateTimeOffMutation = useMutation({
    mutationFn: () => {
      if (!selected || !editTimeOff) throw new Error('No time off')
      return patchResourceAvailabilityException(selected.id, editTimeOff.id, {
        starts_at: fromDatetimeLocalValue(timeOffStart),
        ends_at: fromDatetimeLocalValue(timeOffEnd),
        reason: timeOffReason.trim() || null,
      })
    },
    onSuccess: () => {
      notify('Time off updated', 'success')
      setEditTimeOff(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.exceptions(selected!.id) })
    },
    onError: (err: unknown) => notify(err instanceof ApiError ? err.message : 'Update failed', 'error'),
  })

  const deleteTimeOffMutation = useMutation({
    mutationFn: () => {
      if (!selected || !deleteTimeOff) throw new Error('No time off')
      return deleteResourceAvailabilityException(selected.id, deleteTimeOff.id)
    },
    onSuccess: () => {
      notify('Time off removed', 'success')
      setDeleteTimeOff(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.exceptions(selected!.id) })
    },
    onError: (err: unknown) => notify(err instanceof ApiError ? err.message : 'Delete failed', 'error'),
  })

  const saveRuleMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('No resource')
      const body = { weekday: Number(ruleWeekday), start_time: ruleStart, end_time: ruleEnd }
      return editRule
        ? patchResourceAvailability(selected.id, editRule.id, body)
        : createResourceAvailability(selected.id, body)
    },
    onSuccess: () => {
      notify(editRule ? 'Working hours updated' : 'Working hours added', 'success')
      setRuleOpen(false)
      setEditRule(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.availability(selected!.id) })
    },
    onError: (err: unknown) => notify(err instanceof ApiError ? err.message : 'Save failed', 'error'),
  })

  const deleteRuleMutation = useMutation({
    mutationFn: () => {
      if (!selected || !deleteRule) throw new Error('No rule')
      return deleteResourceAvailability(selected.id, deleteRule.id)
    },
    onSuccess: () => {
      notify('Working hours removed', 'success')
      setDeleteRule(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.resources.availability(selected!.id) })
    },
    onError: (err: unknown) => notify(err instanceof ApiError ? err.message : 'Delete failed', 'error'),
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
  const locations = locationsQuery.data ?? []

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
            Location: {selected.location_id != null ? locations.find((location) => location.id === selected.location_id)?.name ?? `#${selected.location_id}` : '—'}
          </Typography>
          <Button
            variant="outlined"
            sx={{ alignSelf: 'flex-start' }}
            onClick={() => {
              setEditResource(selected)
              setEditName(selected.name)
              setEditType(selected.resource_type)
              setEditCapacity(String(selected.capacity))
              setEditLocationId(selected.location_id != null ? String(selected.location_id) : '')
              setEditActive(selected.active)
            }}
          >
            Edit resource
          </Button>
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
                    onClick={() => setEditCapability({ id: cap.id, capability: cap.capability })}
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
          <Button
            variant="outlined"
            sx={{ alignSelf: 'flex-start' }}
            onClick={() => {
              setEditRule(null)
              setRuleWeekday('0')
              setRuleStart('09:00')
              setRuleEnd('17:00')
              setRuleOpen(true)
            }}
          >
            Add working hours
          </Button>
          {availabilityQuery.isPending ? (
            <CircularProgress size={20} />
          ) : rules.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No availability rules yet.
            </Typography>
          ) : (
            rules.map((rule) => (
              <Stack key={rule.id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {WEEKDAYS[rule.weekday] ?? `Day ${rule.weekday}`}: {rule.start_time}–{rule.end_time}
                </Typography>
                <Button size="small" onClick={() => {
                  setEditRule(rule)
                  setRuleWeekday(String(rule.weekday))
                  setRuleStart(rule.start_time)
                  setRuleEnd(rule.end_time)
                  setRuleOpen(true)
                }}>Edit</Button>
                <Button size="small" color="error" onClick={() => setDeleteRule(rule)}>Delete</Button>
              </Stack>
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
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button size="small" onClick={() => {
                    setEditTimeOff(exc)
                    setTimeOffStart(toDatetimeLocalValue(exc.starts_at))
                    setTimeOffEnd(toDatetimeLocalValue(exc.ends_at))
                    setTimeOffReason(exc.reason ?? '')
                    setTimeOffOpen(true)
                  }}>Edit</Button>
                  <Button size="small" color="error" onClick={() => setDeleteTimeOff(exc)}>Delete</Button>
                </Stack>
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
            <TextField
              select
              label="Location"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              fullWidth
            >
              <MenuItem value="">No specific location</MenuItem>
              {locations.map((location) => (
                <MenuItem key={location.id} value={location.id}>{location.name}</MenuItem>
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

      <Dialog
        open={editResource != null}
        onClose={() => !updateResourceMutation.isPending && setEditResource(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Edit resource</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField label="Name" value={editName} onChange={(e) => setEditName(e.target.value)} fullWidth required />
            <TextField label="Type" value={editType} onChange={(e) => setEditType(e.target.value)} fullWidth required />
            <TextField label="Capacity" type="number" value={editCapacity} onChange={(e) => setEditCapacity(e.target.value)} slotProps={{ htmlInput: { min: 1 } }} fullWidth />
            <TextField select label="Location" value={editLocationId} onChange={(e) => setEditLocationId(e.target.value)} fullWidth>
              <MenuItem value="">No specific location</MenuItem>
              {locations.map((location) => <MenuItem key={location.id} value={location.id}>{location.name}</MenuItem>)}
            </TextField>
            <FormControlLabel control={<Switch checked={editActive} onChange={(e) => setEditActive(e.target.checked)} />} label="Active" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditResource(null)} disabled={updateResourceMutation.isPending}>Cancel</Button>
          <Button variant="contained" disabled={!editName.trim() || !editType.trim() || updateResourceMutation.isPending} onClick={() => updateResourceMutation.mutate(false)}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editCapability != null} onClose={() => !editCapabilityMutation.isPending && setEditCapability(null)} fullWidth maxWidth="xs">
        <DialogTitle>Edit capability</DialogTitle>
        <DialogContent dividers>
          <TextField label="Capability" value={editCapability?.capability ?? ''} onChange={(e) => setEditCapability((value) => value ? { ...value, capability: e.target.value } : value)} fullWidth sx={{ mt: 1 }} required />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditCapability(null)} disabled={editCapabilityMutation.isPending}>Cancel</Button>
          <Button variant="contained" disabled={!editCapability?.capability.trim() || editCapabilityMutation.isPending} onClick={() => editCapabilityMutation.mutate()}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={ruleOpen} onClose={() => !saveRuleMutation.isPending && setRuleOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{editRule ? 'Edit working hours' : 'Add working hours'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField select label="Day" value={ruleWeekday} onChange={(e) => setRuleWeekday(e.target.value)} fullWidth>
              {WEEKDAYS.map((day, index) => <MenuItem key={day} value={index}>{day}</MenuItem>)}
            </TextField>
            <TextField label="Starts" type="time" value={ruleStart} onChange={(e) => setRuleStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth required />
            <TextField label="Ends" type="time" value={ruleEnd} onChange={(e) => setRuleEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} fullWidth required />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRuleOpen(false)} disabled={saveRuleMutation.isPending}>Cancel</Button>
          <Button variant="contained" disabled={!ruleStart || !ruleEnd || saveRuleMutation.isPending} onClick={() => saveRuleMutation.mutate()}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={timeOffOpen}
        onClose={() => !(editTimeOff ? updateTimeOffMutation.isPending : timeOffMutation.isPending) && setTimeOffOpen(false)}
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
          <Button onClick={() => { setTimeOffOpen(false); setEditTimeOff(null) }} disabled={timeOffMutation.isPending || updateTimeOffMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!timeOffStart || !timeOffEnd || timeOffMutation.isPending || updateTimeOffMutation.isPending}
            onClick={() => editTimeOff ? updateTimeOffMutation.mutate() : timeOffMutation.mutate()}
          >
            {editTimeOff ? 'Save' : 'Add'}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={forceDeactivate}
        title="Deactivate despite future reservations?"
        description="Future held or confirmed reservations use this resource. Deactivation may require those bookings to be reassigned."
        confirmLabel="Deactivate anyway"
        confirmColor="error"
        loading={updateResourceMutation.isPending}
        onClose={() => !updateResourceMutation.isPending && setForceDeactivate(false)}
        onConfirm={() => updateResourceMutation.mutate(true)}
      />
      <ConfirmDialog
        open={deleteRule != null}
        title="Delete working hours?"
        description="This availability rule will be removed."
        confirmLabel="Delete"
        confirmColor="error"
        loading={deleteRuleMutation.isPending}
        onClose={() => !deleteRuleMutation.isPending && setDeleteRule(null)}
        onConfirm={() => deleteRuleMutation.mutate()}
      />
      <ConfirmDialog
        open={deleteTimeOff != null}
        title="Delete time off?"
        description="This time-off exception will be removed."
        confirmLabel="Delete"
        confirmColor="error"
        loading={deleteTimeOffMutation.isPending}
        onClose={() => !deleteTimeOffMutation.isPending && setDeleteTimeOff(null)}
        onConfirm={() => deleteTimeOffMutation.mutate()}
      />
    </Stack>
  )
}
