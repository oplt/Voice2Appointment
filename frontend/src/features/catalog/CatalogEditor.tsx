import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
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
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  archiveCatalogItem,
  patchCatalogItem,
  type CatalogCategory,
  type CatalogItem,
  type CatalogKind,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useSnackbar } from '../../components/SnackbarProvider'
import { OptionsPanel } from './OptionsPanel'

const EDITOR_TABS = [
  'Overview',
  'Pricing',
  'Scheduling',
  'Options',
  'Availability',
  'Locations',
] as const

export type CatalogDraft = {
  name: string
  kind: CatalogKind
  category_id: number | ''
  description: string
  active: boolean
  bookable: boolean
  duration_minutes: string
}

function draftFromItem(item: CatalogItem): CatalogDraft {
  return {
    name: item.name,
    kind: item.kind,
    category_id: item.category_id ?? '',
    description: item.description ?? '',
    active: item.active,
    bookable: item.bookable,
    duration_minutes: item.duration_minutes != null ? String(item.duration_minutes) : '',
  }
}

function voicePreview(item: CatalogItem): string {
  const duration =
    item.duration_minutes != null ? `${item.duration_minutes}-minute ` : ''
  const bookable = item.bookable ? 'and is bookable by phone.' : 'and is not bookable by phone.'
  return `I can describe ${duration}${item.name} ${bookable}`
}

type CatalogEditorProps = {
  item: CatalogItem | null
  categories: CatalogCategory[]
  narrow: boolean
  onClose: () => void
  onSaved: (updated: CatalogItem) => void
  onArchived: () => void
}

export function CatalogEditor({
  item,
  categories,
  narrow,
  onClose,
  onSaved,
  onArchived,
}: CatalogEditorProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [editorTab, setEditorTab] = useState(0)
  const [editDraft, setEditDraft] = useState<CatalogDraft | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<CatalogItem | null>(null)

  useEffect(() => {
    if (!item) {
      setEditDraft(null)
      setEditorTab(0)
      return
    }
    setEditDraft(draftFromItem(item))
    setEditorTab(0)
  }, [item])

  const patchMutation = useMutation({
    mutationFn: (target: CatalogItem) => {
      if (!editDraft) throw new Error('No draft')
      return patchCatalogItem(target.id, {
        expected_version: target.version,
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
      setEditDraft(draftFromItem(updated))
      onSaved(updated)
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (target: CatalogItem) => archiveCatalogItem(target.id, target.version),
    onSuccess: () => {
      notify('Item archived', 'success')
      setArchiveTarget(null)
      onArchived()
      void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  return (
    <>
      <Dialog
        open={item != null}
        onClose={onClose}
        fullWidth
        maxWidth="md"
        fullScreen={narrow}
      >
        {item && editDraft ? (
          <>
            <DialogTitle>{editDraft.name || item.name}</DialogTitle>
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
                    onChange={(e) =>
                      setEditDraft({ ...editDraft, description: e.target.value })
                    }
                    fullWidth
                    multiline
                    minRows={2}
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={editDraft.active}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, active: e.target.checked })
                        }
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
                    <Typography variant="body1">{voicePreview(item)}</Typography>
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
              {editorTab === 3 ? <OptionsPanel itemId={item.id} /> : null}
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
                onClick={() => setArchiveTarget(item)}
                disabled={archiveMutation.isPending}
              >
                Archive
              </Button>
              <Box sx={{ flex: 1 }} />
              <Button onClick={onClose}>Close</Button>
              <Button
                variant="contained"
                disabled={!editDraft.name.trim() || patchMutation.isPending}
                onClick={() => patchMutation.mutate(item)}
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
    </>
  )
}
