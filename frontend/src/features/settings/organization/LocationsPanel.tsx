import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
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

import { ApiError } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import {
  createLocation,
  listLocations,
  patchLocation,
  type Location,
} from '../../../api/tenancy'
import { useSnackbar } from '../../../components/SnackbarProvider'

type Draft = {
  name: string
  timezone: string
  address: string
  phone: string
}

const emptyDraft = (): Draft => ({
  name: '',
  timezone: 'UTC',
  address: '',
  phone: '',
})

type LocationsPanelProps = {
  canWrite: boolean
}

export function LocationsPanel({ canWrite }: LocationsPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Location | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft())

  const listQuery = useQuery({
    queryKey: queryKeys.tenancy.locations,
    queryFn: listLocations,
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = {
        name: draft.name.trim(),
        timezone: draft.timezone.trim() || 'UTC',
        address: draft.address.trim() || null,
        phone: draft.phone.trim() || null,
      }
      if (editing) return patchLocation(editing.id, body)
      return createLocation(body)
    },
    onSuccess: () => {
      notify(editing ? 'Location updated' : 'Location created', 'success')
      setDialogOpen(false)
      setEditing(null)
      setDraft(emptyDraft())
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenancy.locations })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const openCreate = () => {
    setEditing(null)
    setDraft(emptyDraft())
    setDialogOpen(true)
  }

  const openEdit = (row: Location) => {
    setEditing(row)
    setDraft({
      name: row.name,
      timezone: row.timezone || 'UTC',
      address: row.address ?? '',
      phone: row.phone ?? '',
    })
    setDialogOpen(true)
  }

  const locations = listQuery.data ?? []
  const listError =
    listQuery.error instanceof ApiError
      ? listQuery.error.message
      : listQuery.error
        ? 'Failed to load locations'
        : null

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
      >
        <Typography variant="h3">Locations</Typography>
        {canWrite ? (
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
            New location
          </Button>
        ) : null}
      </Stack>

      {!canWrite ? (
        <Typography variant="body2" color="text.secondary">
          You can view locations. Ask an admin to create or edit them.
        </Typography>
      ) : null}

      {listError ? <Alert severity="error">{listError}</Alert> : null}

      {listQuery.isPending ? (
        <CircularProgress size={28} />
      ) : locations.length === 0 ? (
        <Typography color="text.secondary">No locations yet.</Typography>
      ) : (
        <TableContainer>
          <Table size="small" aria-label="Locations">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Timezone</TableCell>
                <TableCell>Phone</TableCell>
                {canWrite ? <TableCell align="right">Actions</TableCell> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {locations.map((row) => (
                <TableRow key={row.id} hover>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{row.timezone}</TableCell>
                  <TableCell>{row.phone || '—'}</TableCell>
                  {canWrite ? (
                    <TableCell align="right">
                      <Button size="small" onClick={() => openEdit(row)}>
                        Edit
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog
        open={dialogOpen}
        onClose={() => !saveMutation.isPending && setDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{editing ? 'Edit location' : 'New location'}</DialogTitle>
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
              label="Timezone"
              value={draft.timezone}
              onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
              fullWidth
              helperText="IANA timezone, e.g. Europe/Berlin"
            />
            <TextField
              label="Address"
              value={draft.address}
              onChange={(e) => setDraft({ ...draft, address: e.target.value })}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label="Phone"
              value={draft.phone}
              onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)} disabled={saveMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!draft.name.trim() || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
