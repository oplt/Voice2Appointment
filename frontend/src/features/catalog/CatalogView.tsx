import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  archiveCatalogItem,
  bulkActivateCatalogItems,
  bulkDeactivateCatalogItems,
  createCatalogItem,
  duplicateCatalogItem,
  listCatalogItems,
  listCategories,
  type CatalogItem,
  type CatalogKind,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { queryStaleTime } from '../../app/queryClient'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { CatalogCreateDialog } from './CatalogCreateDialog'
import { CatalogEditor, type CatalogDraft } from './CatalogEditor'
import { CatalogList } from './CatalogList'
import { CategoryManager } from './CategoryManager'

const PAGE_SIZE = 50
const SEARCH_DEBOUNCE_MS = 300

const emptyDraft = (): CatalogDraft => ({
  name: '',
  kind: 'service',
  category_id: '',
  description: '',
  active: true,
  bookable: false,
  duration_minutes: '',
})

export function CatalogView() {
  const theme = useTheme()
  const narrowEditor = useMediaQuery(theme.breakpoints.down('md'))
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()

  const [listTab, setListTab] = useState(0)
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS)
  const [kindFilter, setKindFilter] = useState<'all' | CatalogKind>('all')
  const [selected, setSelected] = useState<number[]>([])
  const [editorId, setEditorId] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [draft, setDraft] = useState<CatalogDraft>(emptyDraft)
  const [archiveTarget, setArchiveTarget] = useState<CatalogItem | null>(null)
  const [offset, setOffset] = useState(0)
  const [accumulated, setAccumulated] = useState<CatalogItem[]>([])
  const [categoryCreateOpen, setCategoryCreateOpen] = useState(false)

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
  }, [debouncedQuery, kindFilter, listTab])

  const itemsQuery = useQuery({
    queryKey: queryKeys.catalog.items({
      query: debouncedQuery || undefined,
      kind: kindParam,
      listTab,
      limit: PAGE_SIZE,
      offset,
    }),
    queryFn: ({ signal }) =>
      listCatalogItems(
        {
          query: debouncedQuery || undefined,
          kind: kindParam,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    staleTime: queryStaleTime.catalog,
  })

  const categoriesQuery = useQuery({
    queryKey: queryKeys.catalog.categories,
    queryFn: ({ signal }) => listCategories(signal),
    staleTime: queryStaleTime.catalog,
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

  const duplicateMutation = useMutation({
    mutationFn: (item: CatalogItem) =>
      duplicateCatalogItem(item.id, `${item.name} (copy)`),
    onSuccess: (row) => {
      notify('Item duplicated', 'success')
      setAccumulated((prev) => [row, ...prev.filter((item) => item.id !== row.id)])
      setEditorId(row.id)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Duplicate failed', 'error')
    },
  })

  const openEditor = (item: CatalogItem) => {
    setEditorId(item.id)
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

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Services & Products"
        subtitle="Catalog items the assistant can describe, sell, and book."
        actions={
          listTab === 3 ? (
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCategoryCreateOpen(true)}
            >
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
          <Button
            component={RouterLink}
            to="/pricing"
            variant="outlined"
            sx={{ alignSelf: 'flex-start' }}
          >
            Open pricing
          </Button>
        </Stack>
      ) : listTab === 3 ? (
        <CategoryManager
          createOpen={categoryCreateOpen}
          onCreateOpenChange={setCategoryCreateOpen}
        />
      ) : (
        <CatalogList
          query={query}
          onQueryChange={setQuery}
          kindFilter={kindFilter}
          onKindFilterChange={setKindFilter}
          kindFilterDisabled={listTab === 1 || listTab === 2}
          items={filtered}
          total={total}
          loading={itemsQuery.isPending && offset === 0}
          fetchingMore={itemsQuery.isFetching}
          hasMore={hasMore}
          onLoadMore={() => setOffset((prev) => prev + PAGE_SIZE)}
          selected={selected}
          onToggleSelected={toggleSelected}
          onSelectAllVisible={(checked) =>
            setSelected(checked ? filtered.map((r) => r.id) : [])
          }
          categoryNameOf={categoryNameOf}
          bulkPending={bulkMutation.isPending}
          onBulkEnable={() => bulkMutation.mutate(true)}
          onBulkDisable={() => bulkMutation.mutate(false)}
          onEdit={openEditor}
          onDuplicate={(item) => duplicateMutation.mutate(item)}
          onArchive={setArchiveTarget}
        />
      )}

      <CatalogCreateDialog
        open={createOpen}
        draft={draft}
        onDraftChange={setDraft}
        categories={categories}
        saving={createMutation.isPending}
        onClose={() => setCreateOpen(false)}
        onCreate={() => createMutation.mutate()}
      />

      <CatalogEditor
        item={editor}
        categories={categories}
        narrow={narrowEditor}
        onClose={() => setEditorId(null)}
        onSaved={(updated) => {
          setEditorId(updated.id)
          setAccumulated((prev) =>
            prev.map((row) => (row.id === updated.id ? updated : row)),
          )
        }}
        onArchived={() => {
          setEditorId(null)
          setOffset(0)
        }}
      />

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
