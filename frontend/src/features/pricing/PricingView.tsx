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
  createPrice,
  listPriceBooks,
  listPrices,
  type Price,
  type PriceBook,
} from '../../api/pricing'
import { queryKeys } from '../../api/queryKeys'
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

export function PricingView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [selectedBookId, setSelectedBookId] = useState<number | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [catalogItemId, setCatalogItemId] = useState('')
  const [amountMajor, setAmountMajor] = useState('')
  const [currency, setCurrency] = useState('EUR')

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

  const catalogItems = catalogQuery.data?.items ?? []
  const itemName = (id: number) =>
    catalogItems.find((item: CatalogItem) => item.id === id)?.name ?? `#${id}`

  const prices = pricesQuery.data ?? []

  const createMutation = useMutation({
    mutationFn: () => {
      if (activeBookId == null) throw new Error('No price book')
      const amount = Math.round(Number(amountMajor) * 100)
      return createPrice(activeBookId, {
        catalog_item_id: Number(catalogItemId),
        amount_minor: amount,
        currency: currency.trim().toUpperCase() || activeBook?.currency || 'EUR',
      })
    },
    onSuccess: () => {
      notify('Price added', 'success')
      setAddOpen(false)
      setCatalogItemId('')
      setAmountMajor('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.pricing.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add price', 'error')
    },
  })

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

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Pricing"
        subtitle="Price books and minor-unit prices by location and effective dates."
        actions={
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            disabled={activeBookId == null}
            onClick={() => {
              setCurrency(activeBook?.currency ?? 'EUR')
              setAddOpen(true)
            }}
          >
            Add price
          </Button>
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
        <Alert severity="info">No price books yet. Create one via the pricing API.</Alert>
      ) : (
        <>
          <TextField
            select
            label="Price book"
            value={activeBookId ?? ''}
            onChange={(e) => setSelectedBookId(Number(e.target.value))}
            sx={{ maxWidth: 320 }}
          >
            {books.map((book: PriceBook) => (
              <MenuItem key={book.id} value={book.id}>
                {book.name} ({book.currency})
                {!book.active ? ' — inactive' : ''}
              </MenuItem>
            ))}
          </TextField>

          {pricesQuery.isPending ? (
            <CircularProgress size={24} />
          ) : (
            <TableContainer>
              <Table size="small" aria-label="Prices">
                <TableHead>
                  <TableRow>
                    <TableCell>Price book</TableCell>
                    <TableCell>Catalog item</TableCell>
                    <TableCell>Amount</TableCell>
                    <TableCell>Channel</TableCell>
                    <TableCell>Effective</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {prices.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography color="text.secondary">No prices in this book.</Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    prices.map((row: Price) => (
                      <TableRow key={row.id}>
                        <TableCell>{activeBook?.name ?? row.price_book_id}</TableCell>
                        <TableCell>{itemName(row.catalog_item_id)}</TableCell>
                        <TableCell>{formatAmount(row.amount_minor, row.currency)}</TableCell>
                        <TableCell>{row.channel ?? '—'}</TableCell>
                        <TableCell>{formatDate(row.effective_from)}</TableCell>
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
        open={addOpen}
        onClose={() => !createMutation.isPending && setAddOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Add price</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              select
              label="Catalog item"
              value={catalogItemId}
              onChange={(e) => setCatalogItemId(e.target.value)}
              fullWidth
              required
            >
              {catalogItems.map((item) => (
                <MenuItem key={item.id} value={item.id}>
                  {item.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Amount"
              type="number"
              value={amountMajor}
              onChange={(e) => setAmountMajor(e.target.value)}
              fullWidth
              required
              helperText="Major units (e.g. 65.00)"
            />
            <TextField
              label="Currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              fullWidth
              inputProps={{ maxLength: 3 }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={createMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              !catalogItemId ||
              amountMajor === '' ||
              Number.isNaN(Number(amountMajor)) ||
              createMutation.isPending
            }
            onClick={() => createMutation.mutate()}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
