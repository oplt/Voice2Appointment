import AddIcon from '@mui/icons-material/Add'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useMemo, useState } from 'react'

import { PageHeader } from '../../components/PageHeader'
import { BookingPolicyPanel } from './BookingPolicyPanel'

type ResourceRow = {
  id: number
  name: string
  resourceType: string
  active: boolean
  capacity: number
  capabilities: string[]
  hours: string
}

const SEED: ResourceRow[] = [
  {
    id: 1,
    name: 'Dr. Rivera',
    resourceType: 'practitioner',
    active: true,
    capacity: 1,
    capabilities: ['general', 'follow_up'],
    hours: 'Mon–Fri 09:00–17:00',
  },
  {
    id: 2,
    name: 'Chair 1',
    resourceType: 'chair',
    active: true,
    capacity: 1,
    capabilities: [],
    hours: 'Tue–Sat 10:00–19:00',
  },
  {
    id: 3,
    name: 'Dining room',
    resourceType: 'capacity_pool',
    active: true,
    capacity: 40,
    capabilities: ['indoor'],
    hours: 'Daily 11:00–22:00',
  },
]

const DETAIL_TABS = [
  'Overview',
  'Capabilities',
  'Working hours',
  'Service assignments',
  'Time off',
] as const

export function ResourcesView() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [section, setSection] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(SEED[0]?.id ?? null)
  const [detailTab, setDetailTab] = useState(0)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return SEED
    return SEED.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.resourceType.toLowerCase().includes(q) ||
        r.capabilities.some((c) => c.includes(q)),
    )
  }, [query])

  const selected = filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null

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
          <Typography variant="body2">Type: {selected.resourceType}</Typography>
          <Typography variant="body2">Capacity: {selected.capacity}</Typography>
          <Typography variant="body2">Hours: {selected.hours}</Typography>
        </Stack>
      ) : null}
      {detailTab === 1 ? (
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
          {selected.capabilities.length ? (
            selected.capabilities.map((cap) => <Chip key={cap} label={cap} size="small" />)
          ) : (
            <Typography variant="body2" color="text.secondary">
              No skill capabilities (equipment/pool).
            </Typography>
          )}
        </Stack>
      ) : null}
      {detailTab === 2 ? (
        <Stack spacing={1.5}>
          <Typography variant="body1">{selected.hours}</Typography>
          <Typography variant="body2" color="text.secondary">
            Calendar-style week grid will render here. Button/form editors stay available for every
            change — drag is never the only path.
          </Typography>
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
            {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
              <Box
                key={`${d}-${i}`}
                sx={{
                  bgcolor: i < 5 ? 'rgba(62, 106, 225, 0.12)' : 'var(--surface-secondary)',
                  minHeight: 64,
                  borderRadius: 0.5,
                  p: 0.5,
                }}
              >
                <Typography variant="caption">{d}</Typography>
              </Box>
            ))}
          </Box>
          <Button variant="outlined" sx={{ alignSelf: 'flex-start' }}>
            Edit hours (form)
          </Button>
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
          <Button variant="outlined" sx={{ alignSelf: 'flex-start' }}>
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
          <Button variant="contained" startIcon={<AddIcon />} disabled>
            New resource
          </Button>
        }
      />

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
          {isMobile ? (
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
                      secondary={`${row.resourceType} · cap ${row.capacity}`}
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
                        secondary={`${row.resourceType} · cap ${row.capacity}`}
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
    </Stack>
  )
}
