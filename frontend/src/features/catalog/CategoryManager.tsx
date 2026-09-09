import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  createCategory,
  listCategories,
  patchCategory,
  type CatalogCategory,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

type DialogState =
  | { mode: 'create'; name: string; active: boolean }
  | { mode: 'edit'; category: CatalogCategory; name: string; active: boolean }

type CategoryManagerProps = {
  createOpen: boolean
  onCreateOpenChange: (open: boolean) => void
}

export function CategoryManager({
  createOpen,
  onCreateOpenChange,
}: CategoryManagerProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [seenCreateOpen, setSeenCreateOpen] = useState(createOpen)

  if (createOpen !== seenCreateOpen) {
    setSeenCreateOpen(createOpen)
    if (createOpen) {
      setDialog({ mode: 'create', name: '', active: true })
    }
  }

  const categoriesQuery = useQuery({
    queryKey: queryKeys.catalog.categories,
    queryFn: ({ signal }) => listCategories(signal),
  })
  const categories = categoriesQuery.data ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.all })
  }

  const closeDialog = () => {
    onCreateOpenChange(false)
    setDialog(null)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!dialog) throw new Error('No category dialog')
      const name = dialog.name.trim()
      if (!name) throw new Error('Name required')
      if (dialog.mode === 'create') {
        return createCategory({ name, active: dialog.active })
      }
      return patchCategory(dialog.category.id, { name, active: dialog.active })
    },
    onSuccess: () => {
      notify(dialog?.mode === 'create' ? 'Category created' : 'Category saved', 'success')
      closeDialog()
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Category save failed', 'error')
    },
  })

  const archiveMutation = useMutation({
    mutationFn: (cat: CatalogCategory) => patchCategory(cat.id, { active: false }),
    onSuccess: () => {
      notify('Category archived', 'success')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  const openEdit = (cat: CatalogCategory) => {
    onCreateOpenChange(false)
    setDialog({
      mode: 'edit',
      category: cat,
      name: cat.name,
      active: cat.active,
    })
  }

  return (
    <>
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
                        <Button size="small" onClick={() => openEdit(cat)}>
                          Edit
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          disabled={!cat.active || archiveMutation.isPending}
                          onClick={() => archiveMutation.mutate(cat)}
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

      <Dialog
        open={dialog != null}
        onClose={() => !saveMutation.isPending && closeDialog()}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {dialog?.mode === 'create' ? 'New category' : 'Edit category'}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={dialog?.name ?? ''}
              onChange={(e) =>
                setDialog((prev) => (prev ? { ...prev, name: e.target.value } : prev))
              }
              fullWidth
              required
            />
            <FormControlLabel
              control={
                <Switch
                  checked={dialog?.active ?? true}
                  onChange={(e) =>
                    setDialog((prev) =>
                      prev ? { ...prev, active: e.target.checked } : prev,
                    )
                  }
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saveMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!dialog?.name.trim() || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
