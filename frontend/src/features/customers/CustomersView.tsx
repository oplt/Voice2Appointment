import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
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
import { canWriteCustomers, listOrganizations } from '../../api/tenancy'
import { queryStaleTime } from '../../app/queryClient'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { CustomerDetailDrawer } from './CustomerDetailDrawer'
import { MergeCustomerDialog } from './MergeCustomerDialog'

type Draft = {
  name: string
  phone: string
  email: string
  language: string
}

const emptyDraft = (): Draft => ({ name: '', phone: '', email: '', language: '' })
const SEARCH_DEBOUNCE_MS = 300
const MASTER_DETAIL_MIN = 720

export function CustomersView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Customer | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [selected, setSelected] = useState<Customer | null>(null)
  const [mergeSource, setMergeSource] = useState<Customer | null>(null)

  const orgsQuery = useQuery({
    queryKey: queryKeys.tenancy.organizations,
    queryFn: ({ signal }) => listOrganizations(signal),
    staleTime: queryStaleTime.tenancy,
  })
  const activeRole = orgsQuery.data?.find((org) => org.active)?.role
  const canMerge = canWriteCustomers(activeRole)

  const listQuery = useQuery({
    queryKey: queryKeys.customers.list(debouncedSearch),
    queryFn: ({ signal }) =>
      listCustomers(
        { query: debouncedSearch || undefined, limit: 100, offset: 0 },
        signal,
      ),
    staleTime: queryStaleTime.customers,
  })

  const page = listQuery.data
  const customers = page?.items ?? []

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = {
        name: draft.name.trim() || null,
        phone: draft.phone.trim() || null,
        email: draft.email.trim() || null,
        language: draft.language.trim() || null,
      }
      if (editing) return patchCustomer(editing.id, body)
      return createCustomer(body)
    },
    onSuccess: (row) => {
      notify(editing ? 'Customer updated' : 'Customer created', 'success')
      setDialogOpen(false)
      setEditing(null)
      setDraft(emptyDraft())
      setSelected(row)
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
      language: customer.language ?? '',
    })
    setDialogOpen(true)
  }

  const listError =
    listQuery.error == null
      ? null
      : listQuery.error instanceof ApiError
        ? listQuery.error.message
        : 'Failed to load customers'

  const mergeCandidates = customers

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
      {page ? (
        <Typography variant="body2" color="text.secondary">
          Showing {customers.length} of {page.total}
        </Typography>
      ) : null}

      {listQuery.isPending ? (
        <CircularProgress size={28} />
      ) : customers.length === 0 ? (
        <Typography color="text.secondary">No customers found.</Typography>
      ) : (
        <Box
          sx={{
            containerType: 'inline-size',
            containerName: 'customers-md',
          }}
        >
          {/* Narrow: compact list → drawer */}
          <List
            disablePadding
            aria-label="Customers"
            sx={{
              display: 'block',
              borderTop: '1px solid var(--border-subtle)',
              [`@container customers-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
                display: 'none',
              },
            }}
          >
            {customers.map((row) => (
              <ListItemButton key={row.id} onClick={() => setSelected(row)}>
                <ListItemText
                  primary={row.name || '—'}
                  secondary={[row.phone, row.email].filter(Boolean).join(' · ') || 'No contact'}
                />
              </ListItemButton>
            ))}
          </List>

          {/* Wide: table (detail stays in drawer) */}
          <TableContainer
            sx={{
              display: 'none',
              [`@container customers-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
                display: 'block',
              },
            }}
          >
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
                  <TableRow
                    key={row.id}
                    hover
                    selected={selected?.id === row.id}
                    sx={{ cursor: 'pointer' }}
                    onClick={() => setSelected(row)}
                  >
                    <TableCell>{row.name || '—'}</TableCell>
                    <TableCell>{row.phone || '—'}</TableCell>
                    <TableCell>{row.email || '—'}</TableCell>
                    <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                      <Button size="small" onClick={() => setSelected(row)}>
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      <CustomerDetailDrawer
        customer={selected}
        canMerge={canMerge}
        onClose={() => setSelected(null)}
        onEdit={(customer) => openEdit(customer)}
        onMerge={(customer) => setMergeSource(customer)}
      />

      <MergeCustomerDialog
        open={Boolean(mergeSource)}
        source={mergeSource}
        candidates={mergeCandidates}
        onClose={() => setMergeSource(null)}
        onMerged={(target) => {
          setMergeSource(null)
          setSelected(target)
        }}
      />

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
            <TextField
              label="Language"
              value={draft.language}
              onChange={(e) => setDraft({ ...draft, language: e.target.value })}
              fullWidth
              helperText="Optional BCP-47 tag, e.g. en or de"
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
