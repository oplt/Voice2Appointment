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

import { ApiError } from '../../api/client'
import {
  createCustomer,
  listCustomers,
  patchCustomer,
  type Customer,
} from '../../api/customers'
import { queryKeys } from '../../api/queryKeys'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'

type Draft = {
  name: string
  phone: string
  email: string
}

const emptyDraft = (): Draft => ({ name: '', phone: '', email: '' })

export function CustomersView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Customer | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)

  const listQuery = useQuery({
    queryKey: queryKeys.customers.list(search.trim()),
    queryFn: () => listCustomers(search.trim() || undefined),
  })

  const customers = listQuery.data ?? []

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = {
        name: draft.name.trim() || null,
        phone: draft.phone.trim() || null,
        email: draft.email.trim() || null,
      }
      if (editing) return patchCustomer(editing.id, body)
      return createCustomer(body)
    },
    onSuccess: () => {
      notify(editing ? 'Customer updated' : 'Customer created', 'success')
      setDialogOpen(false)
      setEditing(null)
      setDraft(emptyDraft())
      void queryClient.invalidateQueries({ queryKey: queryKeys.customers.all })
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

  const openEdit = (customer: Customer) => {
    setEditing(customer)
    setDraft({
      name: customer.name ?? '',
      phone: customer.phone ?? '',
      email: customer.email ?? '',
    })
    setDialogOpen(true)
  }

  const listError =
    listQuery.error == null
      ? null
      : listQuery.error instanceof ApiError
        ? listQuery.error.message
        : 'Failed to load customers'

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Customers"
        subtitle="Organization-scoped customers separate from application users."
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
            New customer
          </Button>
        }
      />

      {listError ? <Alert severity="error">{listError}</Alert> : null}

      <TextField
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name, phone, or email"
        fullWidth
        sx={{ maxWidth: 420 }}
      />

      {listQuery.isPending ? (
        <CircularProgress size={28} />
      ) : customers.length === 0 ? (
        <Typography color="text.secondary">No customers found.</Typography>
      ) : (
        <TableContainer>
          <Table size="small" aria-label="Customers">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Phone</TableCell>
                <TableCell>Email</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {customers.map((row) => (
                <TableRow key={row.id} hover>
                  <TableCell>{row.name || '—'}</TableCell>
                  <TableCell>{row.phone || '—'}</TableCell>
                  <TableCell>{row.email || '—'}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(row)}>
                      Edit
                    </Button>
                  </TableCell>
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
        <DialogTitle>{editing ? 'Edit customer' : 'New customer'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              fullWidth
            />
            <TextField
              label="Phone"
              value={draft.phone}
              onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
              fullWidth
            />
            <TextField
              label="Email"
              type="email"
              value={draft.email}
              onChange={(e) => setDraft({ ...draft, email: e.target.value })}
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
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
