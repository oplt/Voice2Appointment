import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'

import type { CatalogCategory, CatalogKind } from '../../api/catalog'
import type { CatalogDraft } from './CatalogEditor'

type CatalogCreateDialogProps = {
  open: boolean
  draft: CatalogDraft
  onDraftChange: (draft: CatalogDraft) => void
  categories: CatalogCategory[]
  saving: boolean
  onClose: () => void
  onCreate: () => void
}

export function CatalogCreateDialog({
  open,
  draft,
  onDraftChange,
  categories,
  saving,
  onClose,
  onCreate,
}: CatalogCreateDialogProps) {
  return (
    <Dialog open={open} onClose={() => !saving && onClose()} fullWidth maxWidth="sm">
      <DialogTitle>New catalog item</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Name"
            value={draft.name}
            onChange={(e) => onDraftChange({ ...draft, name: e.target.value })}
            fullWidth
            required
          />
          <TextField
            select
            label="Kind"
            value={draft.kind}
            onChange={(e) =>
              onDraftChange({ ...draft, kind: e.target.value as CatalogKind })
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
            value={draft.category_id}
            onChange={(e) =>
              onDraftChange({
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
            onChange={(e) => onDraftChange({ ...draft, description: e.target.value })}
            fullWidth
            multiline
            minRows={2}
          />
          <TextField
            label="Duration (minutes)"
            type="number"
            value={draft.duration_minutes}
            onChange={(e) => onDraftChange({ ...draft, duration_minutes: e.target.value })}
            fullWidth
          />
          <FormControlLabel
            control={
              <Switch
                checked={draft.active}
                onChange={(e) => onDraftChange({ ...draft, active: e.target.checked })}
              />
            }
            label="Active"
          />
          <FormControlLabel
            control={
              <Switch
                checked={draft.bookable}
                onChange={(e) => onDraftChange({ ...draft, bookable: e.target.checked })}
              />
            }
            label="Bookable"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={!draft.name.trim() || saving}
          onClick={onCreate}
        >
          Create
        </Button>
      </DialogActions>
    </Dialog>
  )
}
