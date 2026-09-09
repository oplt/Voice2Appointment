import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
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
import { Link as RouterLink } from 'react-router-dom'

import { listCatalogItems, type CatalogItem } from '../../api/catalog'
import { ApiError } from '../../api/client'
import {
  archivePrice,
  archivePriceBook,
  createPrice,
  createPriceBook,
  listLocations,
  listPriceBooks,
  listPrices,
  patchPriceBook,
  patchPrice,
  type Price,
  type PriceBook,
} from '../../api/pricing'
import { queryKeys } from '../../api/queryKeys'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'

function formatAmount(amountMinor: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amountMinor / 100)
  } catch {
    return `${(amountMinor / 100).toFixed(2)} ${currency}`
  }
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(iso))
  } catch {
    return iso
  }
}

function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromDatetimeLocalValue(value: string): string | null {
  if (!value.trim()) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

type PriceForm = {
  catalogItemId: string
  amountMajor: string
  currency: string
  channel: string
  locationId: string
  effectiveFrom: string
  effectiveUntil: string
}

const emptyPriceForm = (currency = 'EUR'): PriceForm => ({
  catalogItemId: '',
  amountMajor: '',
  currency,
  channel: '',
  locationId: '',
  effectiveFrom: '',
  effectiveUntil: '',
})

export function PricingView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [selectedBookId, setSelectedBookId] = useState<number | null>(null)
  const [bookOpen, setBookOpen] = useState(false)
  const [bookName, setBookName] = useState('')
  const [bookCurrency, setBookCurrency] = useState('EUR')
  const [editBook, setEditBook] = useState<PriceBook | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [editPrice, setEditPrice] = useState<Price | null>(null)
  const [priceForm, setPriceForm] = useState<PriceForm>(emptyPriceForm())
  const [archiveBookTarget, setArchiveBookTarget] = useState<PriceBook | null>(null)
  const [archivePriceTarget, setArchivePriceTarget] = useState<Price | null>(null)

  const booksQuery = useQuery({
    queryKey: queryKeys.pricing.books,
    queryFn: listPriceBooks,
  })

  const books = booksQuery.data ?? []
  const activeBookId = selectedBookId ?? books[0]?.id ?? null
  const activeBook = books.find((b) => b.id === activeBookId) ?? null

  const pricesQuery = useQuery({
    queryKey: queryKeys.pricing.prices(activeBookId ?? 0),
    queryFn: () => listPrices(activeBookId!),
    enabled: activeBookId != null,
  })

  const catalogQuery = useQuery({
    queryKey: queryKeys.catalog.items({ forPricing: true }),
    queryFn: () => listCatalogItems({ limit: 100 }),
  })

  const locationsQuery = useQuery({
    queryKey: queryKeys.pricing.locations,
    queryFn: ({ signal }) => listLocations(signal),
  })

  const catalogItems = catalogQuery.data?.items ?? []
  const locations = locationsQuery.data ?? []
  const itemName = (id: number) =>
    catalogItems.find((item: CatalogItem) => item.id === id)?.name ?? `#${id}`
  const locationName = (id: number | null) => {
    if (id == null) return '—'
    return locations.find((loc) => loc.id === id)?.name ?? `#${id}`
  }

  const prices = pricesQuery.data ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.pricing.all })
  }

  const createBookMutation = useMutation({
    mutationFn: () =>
      createPriceBook({
        name: bookName.trim(),
        currency: bookCurrency.trim().toUpperCase() || 'EUR',
        active: true,
      }),
    onSuccess: (book) => {
      notify('Price book created', 'success')
      setBookOpen(false)
      setBookName('')
      setBookCurrency('EUR')
      setSelectedBookId(book.id)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to create price book', 'error')
    },
  })

  const archiveBookMutation = useMutation({
    mutationFn: (book: PriceBook) => archivePriceBook(book.id),
    onSuccess: () => {
      notify('Price book archived', 'success')
      setArchiveBookTarget(null)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  const editBookMutation = useMutation({
    mutationFn: () => {
      if (!editBook) throw new Error('No price book')
      return patchPriceBook(editBook.id, {
        name: bookName.trim(),
        currency: bookCurrency.trim().toUpperCase() || editBook.currency,
        active: editBook.active,
      })
    },
    onSuccess: () => {
      notify('Price book updated', 'success')
      setEditBook(null)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to update price book', 'error')
    },
  })

  const createMutation = useMutation({
    mutationFn: () => {
      if (activeBookId == null) throw new Error('No price book')
      const amount = Math.round(Number(priceForm.amountMajor) * 100)
      return createPrice(activeBookId, {
        catalog_item_id: Number(priceForm.catalogItemId),
        amount_minor: amount,
        currency: priceForm.currency.trim().toUpperCase() || activeBook?.currency || 'EUR',
        channel: priceForm.channel.trim() || null,
        location_id: priceForm.locationId ? Number(priceForm.locationId) : null,
        effective_from: fromDatetimeLocalValue(priceForm.effectiveFrom),
        effective_until: fromDatetimeLocalValue(priceForm.effectiveUntil),
      })
    },
    onSuccess: () => {
      notify('Price added', 'success')
      setAddOpen(false)
      setPriceForm(emptyPriceForm(activeBook?.currency ?? 'EUR'))
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add price', 'error')
    },
  })

  const editMutation = useMutation({
    mutationFn: () => {
      if (!editPrice || activeBookId == null) throw new Error('No price')
      const amount = Math.round(Number(priceForm.amountMajor) * 100)
      return patchPrice(activeBookId, editPrice.id, {
        amount_minor: amount,
        currency: priceForm.currency.trim().toUpperCase() || editPrice.currency,
        channel: priceForm.channel.trim() || null,
        location_id: priceForm.locationId ? Number(priceForm.locationId) : null,
        effective_from: fromDatetimeLocalValue(priceForm.effectiveFrom),
        effective_until: fromDatetimeLocalValue(priceForm.effectiveUntil),
      })
    },
    onSuccess: () => {
      notify('Price updated', 'success')
      setEditPrice(null)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to update price', 'error')
    },
  })

  const archivePriceMutation = useMutation({
    mutationFn: (price: Price) => {
      if (activeBookId == null) throw new Error('No price book')
      return archivePrice(activeBookId, price.id)
    },
    onSuccess: () => {
      notify('Price archived', 'success')
      setArchivePriceTarget(null)
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Archive failed', 'error')
    },
  })

  const openAdd = () => {
    setPriceForm(emptyPriceForm(activeBook?.currency ?? 'EUR'))
    setAddOpen(true)
  }

  const openEditBook = (book: PriceBook) => {
    setEditBook(book)
    setBookName(book.name)
    setBookCurrency(book.currency)
  }

  const openEdit = (row: Price) => {
    setEditPrice(row)
    setPriceForm({
      catalogItemId: String(row.catalog_item_id),
      amountMajor: (row.amount_minor / 100).toFixed(2),
      currency: row.currency,
      channel: row.channel ?? '',
      locationId: row.location_id != null ? String(row.location_id) : '',
      effectiveFrom: toDatetimeLocalValue(row.effective_from),
      effectiveUntil: toDatetimeLocalValue(row.effective_until),
    })
  }

  const booksError =
    booksQuery.error == null
      ? null
      : booksQuery.error instanceof ApiError
        ? booksQuery.error.message
        : 'Failed to load price books'
  const pricesError =
    pricesQuery.error == null
      ? null
      : pricesQuery.error instanceof ApiError
        ? pricesQuery.error.message
        : 'Failed to load prices'

  const priceFormFields = (
    <Stack spacing={2} sx={{ pt: 1 }}>
      {!editPrice ? (
        <TextField
          select
          label="Catalog item"
          value={priceForm.catalogItemId}
          onChange={(e) => setPriceForm({ ...priceForm, catalogItemId: e.target.value })}
          fullWidth
          required
        >
          {catalogItems.map((item) => (
            <MenuItem key={item.id} value={item.id}>
              {item.name}
            </MenuItem>
          ))}
        </TextField>
      ) : (
        <Typography variant="body2">Item: {itemName(editPrice.catalog_item_id)}</Typography>
      )}
      <TextField
        label="Amount"
        type="number"
        value={priceForm.amountMajor}
        onChange={(e) => setPriceForm({ ...priceForm, amountMajor: e.target.value })}
        fullWidth
        required
        helperText="Major units (e.g. 65.00)"
      />
      <TextField
        label="Currency"
        value={priceForm.currency}
        onChange={(e) => setPriceForm({ ...priceForm, currency: e.target.value })}
        fullWidth
        slotProps={{ htmlInput: { maxLength: 3 } }}
      />
      <TextField
        label="Channel"
        value={priceForm.channel}
        onChange={(e) => setPriceForm({ ...priceForm, channel: e.target.value })}
        fullWidth
        helperText="Optional (e.g. phone, web)"
      />
      <TextField
        select
        label="Location"
        value={priceForm.locationId}
        onChange={(e) => setPriceForm({ ...priceForm, locationId: e.target.value })}
        fullWidth
      >
        <MenuItem value="">All locations</MenuItem>
        {locations.map((loc) => (
          <MenuItem key={loc.id} value={loc.id}>
            {loc.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Effective from"
        type="datetime-local"
        value={priceForm.effectiveFrom}
        onChange={(e) => setPriceForm({ ...priceForm, effectiveFrom: e.target.value })}
        fullWidth
        slotProps={{ inputLabel: { shrink: true } }}
      />
      <TextField
        label="Effective until"
        type="datetime-local"
        value={priceForm.effectiveUntil}
        onChange={(e) => setPriceForm({ ...priceForm, effectiveUntil: e.target.value })}
        fullWidth
        slotProps={{ inputLabel: { shrink: true } }}
      />
    </Stack>
  )

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Pricing"
        subtitle="Price books and minor-unit prices by location and effective dates."
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setBookOpen(true)}>
              New price book
            </Button>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              disabled={activeBookId == null}
              onClick={openAdd}
            >
              Add price
            </Button>
          </Stack>
        }
      />

      <Typography variant="body2" color="text.secondary">
        Manage sellable items in{' '}
        <Button component={RouterLink} to="/catalog" size="small">
          Services & Products
        </Button>
        .
      </Typography>

      {booksError ? <Alert severity="error">{booksError}</Alert> : null}
      {pricesError ? <Alert severity="error">{pricesError}</Alert> : null}

      {booksQuery.isPending ? (
        <CircularProgress size={28} />
      ) : books.length === 0 ? (
        <Alert severity="info">No price books yet. Create one to start adding prices.</Alert>
      ) : (
        <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
            <TextField
              select
              label="Price book"
              value={activeBookId ?? ''}
              onChange={(e) => setSelectedBookId(Number(e.target.value))}
              sx={{ maxWidth: 320, minWidth: 240 }}
            >
              {books.map((book: PriceBook) => (
                <MenuItem key={book.id} value={book.id}>
                  {book.name} ({book.currency})
                  {!book.active ? ' — inactive' : ''}
                </MenuItem>
              ))}
            </TextField>
            {activeBook?.active ? (
              <>
                <Button variant="outlined" onClick={() => openEditBook(activeBook)}>
                  Edit book
                </Button>
                <Button
                  color="error"
                  variant="outlined"
                  onClick={() => setArchiveBookTarget(activeBook)}
                >
                  Archive book
                </Button>
              </>
            ) : (
              <Button variant="outlined" onClick={() => activeBook && openEditBook(activeBook)}>
                Edit book
              </Button>
            )}
          </Stack>

          {pricesQuery.isPending ? (
            <CircularProgress size={24} />
          ) : (
            <TableContainer>
              <Table size="small" aria-label="Prices">
                <TableHead>
                  <TableRow>
                    <TableCell>Catalog item</TableCell>
                    <TableCell>Amount</TableCell>
                    <TableCell>Channel</TableCell>
                    <TableCell>Location</TableCell>
                    <TableCell>Effective</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {prices.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <Typography color="text.secondary">No prices in this book.</Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    prices.map((row: Price) => (
                      <TableRow key={row.id}>
                        <TableCell>{itemName(row.catalog_item_id)}</TableCell>
                        <TableCell>{formatAmount(row.amount_minor, row.currency)}</TableCell>
                        <TableCell>{row.channel ?? '—'}</TableCell>
                        <TableCell>{locationName(row.location_id)}</TableCell>
                        <TableCell>
                          {formatDate(row.effective_from)}
                          {row.effective_until ? ` → ${formatDate(row.effective_until)}` : ''}
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                            <Button size="small" onClick={() => openEdit(row)}>
                              Edit
                            </Button>
                            <Button
                              size="small"
                              color="error"
                              onClick={() => setArchivePriceTarget(row)}
                            >
                              Archive
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      <Dialog
        open={bookOpen}
        onClose={() => !createBookMutation.isPending && setBookOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>New price book</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={bookName}
              onChange={(e) => setBookName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Currency"
              value={bookCurrency}
              onChange={(e) => setBookCurrency(e.target.value)}
              fullWidth
              required
              slotProps={{ htmlInput: { maxLength: 3 } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBookOpen(false)} disabled={createBookMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!bookName.trim() || createBookMutation.isPending}
            onClick={() => createBookMutation.mutate()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={editBook != null}
        onClose={() => !editBookMutation.isPending && setEditBook(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Edit price book</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Name"
              value={bookName}
              onChange={(e) => setBookName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Currency"
              value={bookCurrency}
              onChange={(e) => setBookCurrency(e.target.value)}
              fullWidth
              required
              slotProps={{ htmlInput: { maxLength: 3 } }}
              helperText="Currency cannot change once this book has prices."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditBook(null)} disabled={editBookMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!bookName.trim() || editBookMutation.isPending}
            onClick={() => editBookMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={addOpen}
        onClose={() => !createMutation.isPending && setAddOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Add price</DialogTitle>
        <DialogContent dividers>{priceFormFields}</DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={createMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              !priceForm.catalogItemId ||
              priceForm.amountMajor === '' ||
              Number.isNaN(Number(priceForm.amountMajor)) ||
              createMutation.isPending
            }
            onClick={() => createMutation.mutate()}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={editPrice != null}
        onClose={() => !editMutation.isPending && setEditPrice(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Edit price</DialogTitle>
        <DialogContent dividers>{priceFormFields}</DialogContent>
        <DialogActions>
          <Button onClick={() => setEditPrice(null)} disabled={editMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              priceForm.amountMajor === '' ||
              Number.isNaN(Number(priceForm.amountMajor)) ||
              editMutation.isPending
            }
            onClick={() => editMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={Boolean(archiveBookTarget)}
        title="Archive price book?"
        description={
          archiveBookTarget
            ? `“${archiveBookTarget.name}” will be marked inactive.`
            : undefined
        }
        confirmLabel="Archive"
        confirmColor="error"
        loading={archiveBookMutation.isPending}
        onClose={() => {
          if (!archiveBookMutation.isPending) setArchiveBookTarget(null)
        }}
        onConfirm={() => {
          if (archiveBookTarget) archiveBookMutation.mutate(archiveBookTarget)
        }}
      />

      <ConfirmDialog
        open={Boolean(archivePriceTarget)}
        title="Archive price?"
        description="This closes the effective window so the price is no longer active."
        confirmLabel="Archive"
        confirmColor="error"
        loading={archivePriceMutation.isPending}
        onClose={() => {
          if (!archivePriceMutation.isPending) setArchivePriceTarget(null)
        }}
        onConfirm={() => {
          if (archivePriceTarget) archivePriceMutation.mutate(archivePriceTarget)
        }}
      />
    </Stack>
  )
}
