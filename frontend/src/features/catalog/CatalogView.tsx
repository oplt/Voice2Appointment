import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import InputAdornment from '@mui/material/InputAdornment'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader'

type CatalogKind = 'service' | 'product' | 'addon' | 'package'

type CatalogRow = {
  id: number
  name: string
  kind: CatalogKind
  category: string
  active: boolean
  bookable: boolean
  durationMinutes: number | null
  priceLabel: string
  voicePreview: string
}

const SEED: CatalogRow[] = [
  {
    id: 1,
    name: 'General consultation',
    kind: 'service',
    category: 'Visits',
    active: true,
    bookable: true,
    durationMinutes: 30,
    priceLabel: '€65',
    voicePreview: 'I can book a 30-minute general consultation for sixty-five euros.',
  },
  {
    id: 2,
    name: 'Haircut',
    kind: 'service',
    category: 'Salon',
    active: true,
    bookable: true,
    durationMinutes: 45,
    priceLabel: '€40',
    voicePreview: 'A haircut takes about forty-five minutes and costs forty euros.',
  },
  {
    id: 3,
    name: 'Shampoo add-on',
    kind: 'addon',
    category: 'Salon',
    active: true,
    bookable: false,
    durationMinutes: 10,
    priceLabel: '€8',
    voicePreview: 'You can add a shampoo treatment for eight euros.',
  },
  {
    id: 4,
    name: 'Gift card',
    kind: 'product',
    category: 'Retail',
    active: false,
    bookable: false,
    durationMinutes: null,
    priceLabel: 'from €25',
    voicePreview: 'Gift cards start at twenty-five euros and are not bookable by phone.',
  },
]

const EDITOR_TABS = [
  'Overview',
  'Pricing',
  'Scheduling',
  'Options',
  'Availability',
  'Locations',
] as const

export function CatalogView() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [listTab, setListTab] = useState(0)
  const [query, setQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<'all' | CatalogKind>('all')
  const [rows, setRows] = useState(SEED)
  const [selected, setSelected] = useState<number[]>([])
  const [editorId, setEditorId] = useState<number | null>(null)
  const [editorTab, setEditorTab] = useState(0)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (kindFilter !== 'all' && row.kind !== kindFilter) return false
      if (listTab === 1 && row.kind !== 'service' && row.kind !== 'package') return false
      if (listTab === 2 && row.kind !== 'product') return false
      if (listTab === 3 && !row.category) return false
      if (!q) return true
      return (
        row.name.toLowerCase().includes(q) ||
        row.category.toLowerCase().includes(q) ||
        row.kind.includes(q)
      )
    })
  }, [rows, query, kindFilter, listTab])

  const editor = rows.find((r) => r.id === editorId) ?? null

  const toggleSelected = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const setActiveBulk = (active: boolean) => {
    setRows((prev) =>
      prev.map((row) => (selected.includes(row.id) ? { ...row, active } : row)),
    )
    setSelected([])
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Services & Products"
        subtitle="Catalog items the assistant can describe, sell, and book."
        actions={
          <Button variant="contained" startIcon={<AddIcon />} disabled>
            New item
          </Button>
        }
      />

      <Alert severity="info">
        Local preview shell — wire to org catalog APIs when HTTP routes ship. Price books also live
        under{' '}
        <Button component={RouterLink} to="/pricing" size="small">
          Pricing
        </Button>
        .
      </Alert>

      <Tabs
        value={listTab}
        onChange={(_, v: number) => setListTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Catalog views"
      >
        <Tab label="All" />
        <Tab label="Services" />
        <Tab label="Products" />
        <Tab label="Categories" />
        <Tab label="Prices" />
      </Tabs>

      {listTab === 4 ? (
        <Stack spacing={2}>
          <Typography variant="body1" color="text.secondary">
            Price books and effective dates.
          </Typography>
          <Button component={RouterLink} to="/pricing" variant="outlined" sx={{ alignSelf: 'flex-start' }}>
            Open pricing
          </Button>
        </Stack>
      ) : (
        <>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            sx={{ alignItems: { sm: 'center' } }}
          >
            <TextField
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search catalog"
              fullWidth
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                },
              }}
            />
            <TextField
              select
              label="Kind"
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value as 'all' | CatalogKind)}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="all">All kinds</MenuItem>
              <MenuItem value="service">Service</MenuItem>
              <MenuItem value="product">Product</MenuItem>
              <MenuItem value="addon">Add-on</MenuItem>
              <MenuItem value="package">Package</MenuItem>
            </TextField>
            <Button
              variant="outlined"
              disabled={!selected.length}
              onClick={() => setActiveBulk(true)}
            >
              Enable
            </Button>
            <Button
              variant="outlined"
              disabled={!selected.length}
              onClick={() => setActiveBulk(false)}
            >
              Disable
            </Button>
          </Stack>

          {isMobile ? (
            <Stack spacing={1.5}>
              {filtered.map((row) => (
                <Box
                  key={row.id}
                  sx={{
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 1,
                    p: 1.5,
                    bgcolor: 'var(--surface-primary)',
                  }}
                >
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                    <Checkbox
                      checked={selected.includes(row.id)}
                      onChange={() => toggleSelected(row.id)}
                      slotProps={{ input: { 'aria-label': `Select ${row.name}` } }}
                    />
                    <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="subtitle1">{row.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {row.kind} · {row.category} · {row.priceLabel}
                      </Typography>
                      <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                        {row.active ? null : <Chip size="small" label="Disabled" />}
                        {row.bookable ? <Chip size="small" label="Bookable" variant="outlined" /> : null}
                      </Stack>
                      <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={() => setEditorId(row.id)}>
                        Edit
                      </Button>
                    </Stack>
                  </Stack>
                </Box>
              ))}
            </Stack>
          ) : (
            <TableContainer>
              <Table size="small" aria-label="Catalog items">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox">
                      <Checkbox
                        indeterminate={
                          selected.length > 0 && selected.length < filtered.length
                        }
                        checked={filtered.length > 0 && selected.length === filtered.length}
                        onChange={(e) =>
                          setSelected(e.target.checked ? filtered.map((r) => r.id) : [])
                        }
                        slotProps={{ input: { 'aria-label': 'Select all visible' } }}
                      />
                    </TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Kind</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>Price</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {filtered.map((row) => (
                    <TableRow key={row.id} hover selected={selected.includes(row.id)}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={selected.includes(row.id)}
                          onChange={() => toggleSelected(row.id)}
                          slotProps={{ input: { 'aria-label': `Select ${row.name}` } }}
                        />
                      </TableCell>
                      <TableCell>{row.name}</TableCell>
                      <TableCell>{row.kind}</TableCell>
                      <TableCell>{row.category}</TableCell>
                      <TableCell>{row.priceLabel}</TableCell>
                      <TableCell>{row.active ? 'Active' : 'Disabled'}</TableCell>
                      <TableCell align="right">
                        <Button size="small" onClick={() => { setEditorId(row.id); setEditorTab(0) }}>
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      <Dialog
        open={editor != null}
        onClose={() => setEditorId(null)}
        fullWidth
        maxWidth="md"
        fullScreen={isMobile}
      >
        {editor ? (
          <>
            <DialogTitle>{editor.name}</DialogTitle>
            <DialogContent dividers>
              <Tabs
                value={editorTab}
                onChange={(_, v: number) => setEditorTab(v)}
                variant="scrollable"
                scrollButtons="auto"
                aria-label="Catalog item editor"
                sx={{ mb: 2 }}
              >
                {EDITOR_TABS.map((label) => (
                  <Tab key={label} label={label} />
                ))}
              </Tabs>
              {editorTab === 0 ? (
                <Stack spacing={2}>
                  <TextField label="Name" value={editor.name} fullWidth disabled />
                  <TextField label="Kind" value={editor.kind} fullWidth disabled />
                  <TextField label="Category" value={editor.category} fullWidth disabled />
                  <FormControlLabel
                    control={<Switch checked={editor.active} disabled />}
                    label="Active"
                  />
                  <Box
                    sx={{
                      p: 2,
                      bgcolor: 'var(--surface-secondary)',
                      borderRadius: 1,
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                      Voice preview
                    </Typography>
                    <Typography variant="body1">{editor.voicePreview}</Typography>
                  </Box>
                </Stack>
              ) : null}
              {editorTab === 1 ? (
                <Typography variant="body1">List price: {editor.priceLabel}</Typography>
              ) : null}
              {editorTab === 2 ? (
                <Typography variant="body1">
                  Duration: {editor.durationMinutes != null ? `${editor.durationMinutes} min` : 'n/a'}
                  {editor.bookable ? ' · bookable' : ' · not bookable'}
                </Typography>
              ) : null}
              {editorTab >= 3 ? (
                <Alert severity="info">
                  {EDITOR_TABS[editorTab]} editing awaits catalog option / availability APIs.
                </Alert>
              ) : null}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setEditorId(null)}>Close</Button>
            </DialogActions>
          </>
        ) : null}
      </Dialog>
    </Stack>
  )
}
