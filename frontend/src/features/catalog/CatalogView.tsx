import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
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
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  archiveCatalogItem,
  bulkActivateCatalogItems,
  bulkDeactivateCatalogItems,
  createCatalogItem,
  createCatalogOption,
  createCategory,
  deleteCatalogOption,
  listCatalogItems,
  listCatalogOptions,
  listCategories,
  patchCatalogItem,
  patchCatalogOption,
  patchCategory,
  type CatalogCategory,
  type CatalogItem,
  type CatalogKind,
  type CatalogOption,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'

const EDITOR_TABS = [
  'Overview',
  'Pricing',
  'Scheduling',
  'Options',
  'Availability',
  'Locations',
] as const

const PAGE_SIZE = 50

type DraftItem = {
  name: string
  kind: CatalogKind
  category_id: number | ''
  description: string
  active: boolean
  bookable: boolean
  duration_minutes: string
}

const emptyDraft = (): DraftItem => ({
  name: '',
  kind: 'service',
  category_id: '',
  description: '',
  active: true,
  bookable: false,
  duration_minutes: '',
})

function voicePreview(item: CatalogItem): string {
  const duration =
    item.duration_minutes != null ? `${item.duration_minutes}-minute ` : ''
  const bookable = item.bookable ? 'and is bookable by phone.' : 'and is not bookable by phone.'
  return `I can describe ${duration}${item.name} ${bookable}`
}

export function CatalogView() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()

  const [listTab, setListTab] = useState(0)
  const [query, setQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<'all' | CatalogKind>('all')
  const [selected, setSelected] = useState<number[]>([])
  const [editorId, setEditorId] = useState<number | null>(null)
  const [editorTab, setEditorTab] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [draft, setDraft] = useState<DraftItem>(emptyDraft)
  const [editDraft, setEditDraft] = useState<DraftItem | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<CatalogItem | null>(null)
  const [offset, setOffset] = useState(0)
  const [accumulated, setAccumulated] = useState<CatalogItem[]>([])

  const [categoryDialog, setCategoryDialog] = useState<'create' | CatalogCategory | null>(null)
  const [categoryName, setCategoryName] = useState('')
  const [categoryActive, setCategoryActive] = useState(true)

  const [optionName, setOptionName] = useState('')

  const kindParam: CatalogKind | undefined =
    listTab === 2
      ? 'product'
      : listTab === 1 || kindFilter === 'all'
        ? undefined
        : kindFilter

  useEffect(() => {
    setOffset(0)
    setAccumulated([])
    setSelected([])
  }, [query, kindFilter, listTab])

  const itemsQuery = useQuery({
    queryKey: queryKeys.catalog.items({
      query: query.trim() || undefined,
      kind: kindParam,
      listTab,
      limit: PAGE_SIZE,
      offset,
    }),
    queryFn: () =>
      listCatalogItems({
        query: query.trim() || undefined,
        kind: kindParam,
        limit: PAGE_SIZE,
        offset,
      }),
  })

  useEffect(() => {
    const page = itemsQuery.data
    if (!page) return
    setAccumulated((prev) => {
      if (page.offset === 0) return page.items
      const seen = new Set(prev.map((row) => row.id))
      return [...prev, ...page.items.filter((row) => !seen.has(row.id))]
    })
  }, [itemsQuery.data])

  const categoriesQuery = useQuery({
    queryKey: queryKeys.catalog.categories,
    queryFn: listCategories,
  })

  const optionsQuery = useQuery({
    queryKey: queryKeys.catalog.options(editorId ?? 0),
    queryFn: () => listCatalogOptions(editorId!),
    enabled: editorId != null && editorTab === 3,
  })

  const items = accumulated
  const total = itemsQuery.data?.total ?? 0
  const hasMore = items.length < total
  const categories = categoriesQuery.data ?? []
  const categoryNameOf = (id: number | null) =>
    id == null ? '—' : (categories.find((c) => c.id === id)?.name ?? `#${id}`)

  const filtered =
    listTab === 1
      ? items.filter((row) => row.kind === 'service' || row.kind === 'package')
      : items

  const editor = items.find((r) => r.id === editorId) ?? null

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.all })
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createCatalogItem({
        name: draft.name.trim(),
        kind: draft.kind,
        category_id: draft.category_id === '' ? null : draft.category_id,
        description: draft.description.trim() || null,
        active: draft.active,
        bookable: draft.bookable,
        duration_minutes: draft.duration_minutes
          ? Number(draft.duration_minutes)
          : null,
      }),
    onSuccess: () => {
      notify('Catalog item created', 'success')
      setCreateOpen(false)
      setDraft(emptyDraft())
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Create failed', 'error')
    },
  })

  const patchMutation = useMutation({
    mutationFn: (item: CatalogItem) => {
      if (!editDraft) throw new Error('No draft')
      return patchCatalogItem(item.id, {
        expected_version: item.version,
        name: editDraft.name.trim(),
        kind: editDraft.kind,
        category_id: editDraft.category_id === '' ? null : editDraft.category_id,
        description: editDraft.description.trim() || null,
        active: editDraft.active,
        bookable: editDraft.bookable,
        duration_minutes: editDraft.duration_minutes
          ? Number(editDraft.duration_minutes)
          : null,
      })
    },
    onSuccess: (updated) => {
      notify('Catalog item saved', 'success')
      setEditorId(updated.id)
      setEditDraft({
        name: updated.name,
        kind: updated.kind,
        category_id: updated.category_id ?? '',
        description: updated.description ?? '',
        active: updated.active,
        bookable: updated.bookable,
        duration_minutes: updated.duration_minutes != null ? String(updated.duration_minutes) : '',
      })
      setAccumulated((prev) => prev.map((row) => (row.id === updated.id ? updated : row)))
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const bulkMutation = useMutation({
    mutationFn: async (active: boolean) => {
      if (active) return bulkActivateCatalogItems(selected)
      return bulkDeactivateCatalogItems(selected)
    },
    onSuccess: (_data, active) => {
      notify(active ? 'Items enabled' : 'Items disabled', 'success')
      setSelected([])
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Bulk update failed', 'error')
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (item: CatalogItem) => archiveCatalogItem(item.id, item.version),
    onSuccess: () => {
      notify('Item archived', 'success')
      setArchiveTarget(null)
      setEditorId(null)
      setOffset(0)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  const categorySaveMutation = useMutation({
    mutationFn: async () => {
      const name = categoryName.trim()
      if (!name) throw new Error('Name required')
      if (categoryDialog === 'create') {
        return createCategory({ name, active: categoryActive })
      }
      if (categoryDialog && typeof categoryDialog === 'object') {
        return patchCategory(categoryDialog.id, { name, active: categoryActive })
      }
      throw new Error('No category dialog')
    },
    onSuccess: () => {
      notify(categoryDialog === 'create' ? 'Category created' : 'Category saved', 'success')
      setCategoryDialog(null)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Category save failed', 'error')
    },
  })

  const archiveCategoryMutation = useMutation({
    mutationFn: (cat: CatalogCategory) => patchCategory(cat.id, { active: false }),
    onSuccess: () => {
      notify('Category archived', 'success')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  const createOptionMutation = useMutation({
    mutationFn: () => {
      if (editorId == null) throw new Error('No item')
      return createCatalogOption(editorId, { name: optionName.trim(), active: true })
    },
    onSuccess: () => {
      notify('Option added', 'success')
      setOptionName('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.options(editorId!) })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add option', 'error')
    },
  })

  const toggleOptionMutation = useMutation({
    mutationFn: (opt: CatalogOption) => {
      if (editorId == null) throw new Error('No item')
      return patchCatalogOption(editorId, opt.id, { active: !opt.active })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.options(editorId!) })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to update option', 'error')
    },
  })

  const deleteOptionMutation = useMutation({
    mutationFn: (opt: CatalogOption) => {
      if (editorId == null) throw new Error('No item')
      return deleteCatalogOption(editorId, opt.id)
    },
    onSuccess: () => {
      notify('Option removed', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.options(editorId!) })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to remove option', 'error')
    },
  })

  const openEditor = (item: CatalogItem) => {
    setEditorId(item.id)
    setEditorTab(0)
    setEditDraft({
      name: item.name,
      kind: item.kind,
      category_id: item.category_id ?? '',
      description: item.description ?? '',
      active: item.active,
      bookable: item.bookable,
      duration_minutes: item.duration_minutes != null ? String(item.duration_minutes) : '',
    })
  }

  const openCategoryCreate = () => {
    setCategoryName('')
    setCategoryActive(true)
    setCategoryDialog('create')
  }

  const openCategoryEdit = (cat: CatalogCategory) => {
    setCategoryName(cat.name)
    setCategoryActive(cat.active)
    setCategoryDialog(cat)
  }

  const toggleSelected = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const listError =
    itemsQuery.error == null
      ? null
      : itemsQuery.error instanceof ApiError
        ? itemsQuery.error.message
        : 'Failed to load catalog'

  const options = optionsQuery.data ?? []

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Services & Products"
        subtitle="Catalog items the assistant can describe, sell, and book."
        actions={
          listTab === 3 ? (
            <Button variant="contained" startIcon={<AddIcon />} onClick={openCategoryCreate}>
              New category
            </Button>
          ) : (
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => {
                setDraft(emptyDraft())
                setCreateOpen(true)
              }}
            >
              New item
            </Button>
          )
        }
      />

      {listError ? <Alert severity="error">{listError}</Alert> : null}

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
      ) : listTab === 3 ? (
        <Stack spacing={2}>
          {categoriesQuery.isPending ? (
            <CircularProgress size={24} />
          ) : categories.length === 0 ? (
            <Typography color="text.secondary">No categories yet.</Typography>
          ) : (
            <TableContainer>
              <Table size="small" aria-label="Catalog categories">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {categories.map((cat) => (
                    <TableRow key={cat.id}>
                      <TableCell>{cat.name}</TableCell>
                      <TableCell>{cat.active ? 'Active' : 'Archived'}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                          <Button size="small" onClick={() => openCategoryEdit(cat)}>
                            Edit
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            disabled={!cat.active || archiveCategoryMutation.isPending}
                            onClick={() => archiveCategoryMutation.mutate(cat)}
                          >
                            Archive
                          </Button>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
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
              disabled={listTab === 1 || listTab === 2}
            >
              <MenuItem value="all">All kinds</MenuItem>
              <MenuItem value="service">Service</MenuItem>
              <MenuItem value="product">Product</MenuItem>
              <MenuItem value="addon">Add-on</MenuItem>
              <MenuItem value="package">Package</MenuItem>
            </TextField>
            <Button
              variant="outlined"
              disabled={!selected.length || bulkMutation.isPending}
              onClick={() => bulkMutation.mutate(true)}
            >
              Enable
            </Button>
            <Button
              variant="outlined"
              disabled={!selected.length || bulkMutation.isPending}
              onClick={() => bulkMutation.mutate(false)}
            >
              Disable
            </Button>
          </Stack>

          {itemsQuery.isPending && offset === 0 ? (
            <CircularProgress size={28} />
          ) : filtered.length === 0 ? (
            <Typography color="text.secondary">No catalog items found.</Typography>
          ) : isMobile ? (
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
                        {row.kind} · {categoryNameOf(row.category_id)}
                      </Typography>
                      <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                        {row.active ? null : <Chip size="small" label="Disabled" />}
                        {row.bookable ? <Chip size="small" label="Bookable" variant="outlined" /> : null}
                      </Stack>
                      <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={() => openEditor(row)}>
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
                    <TableCell>Duration</TableCell>
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
                      <TableCell>{categoryNameOf(row.category_id)}</TableCell>
                      <TableCell>
                        {row.duration_minutes != null ? `${row.duration_minutes} min` : '—'}
                      </TableCell>
                      <TableCell>{row.active ? 'Active' : 'Disabled'}</TableCell>
                      <TableCell align="right">
                        <Button size="small" onClick={() => openEditor(row)}>
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {listTab !== 3 && listTab !== 4 ? (
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                Showing {filtered.length} of {total}
              </Typography>
              {hasMore ? (
                <Button
                  variant="outlined"
                  disabled={itemsQuery.isFetching}
                  onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
                >
                  {itemsQuery.isFetching ? 'Loading…' : 'Load more'}
                </Button>
              ) : null}
            </Stack>
          ) : null}
        </>
      )}

      <Dialog
        open={createOpen}
        onClose={() => !createMutation.isPending && setCreateOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>New catalog item</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              fullWidth
              required
            />
            <TextField
              select
              label="Kind"
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value as CatalogKind })}
              fullWidth
            >
              <MenuItem value="service">Service</MenuItem>
              <MenuItem value="product">Product</MenuItem>
              <MenuItem value="addon">Add-on</MenuItem>
              <MenuItem value="package">Package</MenuItem>
            </TextField>
            <TextField
              select
              label="Category"
              value={draft.category_id}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  category_id: e.target.value === '' ? '' : Number(e.target.value),
                })
              }
              fullWidth
            >
              <MenuItem value="">None</MenuItem>
              {categories.map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Description"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label="Duration (minutes)"
              type="number"
              value={draft.duration_minutes}
              onChange={(e) => setDraft({ ...draft, duration_minutes: e.target.value })}
              fullWidth
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft.active}
                  onChange={(e) => setDraft({ ...draft, active: e.target.checked })}
                />
              }
              label="Active"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={draft.bookable}
                  onChange={(e) => setDraft({ ...draft, bookable: e.target.checked })}
                />
              }
              label="Bookable"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!draft.name.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={categoryDialog != null}
        onClose={() => !categorySaveMutation.isPending && setCategoryDialog(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {categoryDialog === 'create' ? 'New category' : 'Edit category'}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={categoryName}
              onChange={(e) => setCategoryName(e.target.value)}
              fullWidth
              required
            />
            <FormControlLabel
              control={
                <Switch
                  checked={categoryActive}
                  onChange={(e) => setCategoryActive(e.target.checked)}
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCategoryDialog(null)}
            disabled={categorySaveMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!categoryName.trim() || categorySaveMutation.isPending}
            onClick={() => categorySaveMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={editor != null}
        onClose={() => setEditorId(null)}
        fullWidth
        maxWidth="md"
        fullScreen={isMobile}
      >
        {editor && editDraft ? (
          <>
            <DialogTitle>{editDraft.name || editor.name}</DialogTitle>
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
                  <TextField
                    label="Name"
                    value={editDraft.name}
                    onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
                    fullWidth
                  />
                  <TextField
                    select
                    label="Kind"
                    value={editDraft.kind}
                    onChange={(e) =>
                      setEditDraft({ ...editDraft, kind: e.target.value as CatalogKind })
                    }
                    fullWidth
                  >
                    <MenuItem value="service">Service</MenuItem>
                    <MenuItem value="product">Product</MenuItem>
                    <MenuItem value="addon">Add-on</MenuItem>
                    <MenuItem value="package">Package</MenuItem>
                  </TextField>
                  <TextField
                    select
                    label="Category"
                    value={editDraft.category_id}
                    onChange={(e) =>
                      setEditDraft({
                        ...editDraft,
                        category_id: e.target.value === '' ? '' : Number(e.target.value),
                      })
                    }
                    fullWidth
                  >
                    <MenuItem value="">None</MenuItem>
                    {categories.map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.name}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Description"
                    value={editDraft.description}
                    onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={editDraft.active}
                        onChange={(e) => setEditDraft({ ...editDraft, active: e.target.checked })}
                      />
                    }
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
                    <Typography variant="body1">{voicePreview(editor)}</Typography>
                  </Box>
                </Stack>
              ) : null}
              {editorTab === 1 ? (
                <Typography variant="body1" color="text.secondary">
                  Manage amounts in{' '}
                  <Button component={RouterLink} to="/pricing" size="small">
                    Pricing
                  </Button>
                  .
                </Typography>
              ) : null}
              {editorTab === 2 ? (
                <Stack spacing={2}>
                  <TextField
                    label="Duration (minutes)"
                    type="number"
                    value={editDraft.duration_minutes}
                    onChange={(e) =>
                      setEditDraft({ ...editDraft, duration_minutes: e.target.value })
                    }
                    fullWidth
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={editDraft.bookable}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, bookable: e.target.checked })
                        }
                      />
                    }
                    label="Bookable"
                  />
                </Stack>
              ) : null}
              {editorTab === 3 ? (
                <Stack spacing={2}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <TextField
                      label="Option name"
                      value={optionName}
                      onChange={(e) => setOptionName(e.target.value)}
                      fullWidth
                    />
                    <Button
                      variant="contained"
                      disabled={!optionName.trim() || createOptionMutation.isPending}
                      onClick={() => createOptionMutation.mutate()}
                      sx={{ whiteSpace: 'nowrap' }}
                    >
                      Add option
                    </Button>
                  </Stack>
                  {optionsQuery.isPending ? (
                    <CircularProgress size={20} />
                  ) : options.length === 0 ? (
                    <Typography color="text.secondary">No options yet.</Typography>
                  ) : (
                    <Stack spacing={1}>
                      {options.map((opt) => (
                        <Stack
                          key={opt.id}
                          direction="row"
                          spacing={1}
                          sx={{ alignItems: 'center' }}
                        >
                          <Typography sx={{ flex: 1 }}>{opt.name}</Typography>
                          <Chip
                            size="small"
                            label={opt.active ? 'Active' : 'Inactive'}
                            variant="outlined"
                          />
                          <Button
                            size="small"
                            onClick={() => toggleOptionMutation.mutate(opt)}
                            disabled={toggleOptionMutation.isPending}
                          >
                            {opt.active ? 'Disable' : 'Enable'}
                          </Button>
                          <IconButton
                            aria-label={`Delete ${opt.name}`}
                            size="small"
                            onClick={() => deleteOptionMutation.mutate(opt)}
                            disabled={deleteOptionMutation.isPending}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Stack>
                      ))}
                    </Stack>
                  )}
                </Stack>
              ) : null}
              {editorTab === 4 ? (
                <Alert severity="info">
                  Per-item availability schedules are not exposed by the catalog API yet.
                  Configure resource working hours under Resources.
                </Alert>
              ) : null}
              {editorTab === 5 ? (
                <Alert severity="info">
                  Location assignment for catalog items is not available in the API yet.
                  Manage locations under organization settings.
                </Alert>
              ) : null}
            </DialogContent>
            <DialogActions>
              <Button
                color="error"
                onClick={() => setArchiveTarget(editor)}
                disabled={archiveMutation.isPending}
              >
                Archive
              </Button>
              <Box sx={{ flex: 1 }} />
              <Button onClick={() => setEditorId(null)}>Close</Button>
              <Button
                variant="contained"
                disabled={!editDraft.name.trim() || patchMutation.isPending}
                onClick={() => patchMutation.mutate(editor)}
              >
                Save
              </Button>
            </DialogActions>
          </>
        ) : null}
      </Dialog>

      <ConfirmDialog
        open={Boolean(archiveTarget)}
        title="Archive catalog item?"
        description={
          archiveTarget
            ? `“${archiveTarget.name}” will be archived and deactivated.`
            : undefined
        }
        confirmLabel="Archive"
        confirmColor="error"
        loading={archiveMutation.isPending}
        onClose={() => {
          if (!archiveMutation.isPending) setArchiveTarget(null)
        }}
        onConfirm={() => {
          if (archiveTarget) archiveMutation.mutate(archiveTarget)
        }}
      />
    </Stack>
  )
}
