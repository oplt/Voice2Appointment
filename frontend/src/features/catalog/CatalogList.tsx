import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import InputAdornment from '@mui/material/InputAdornment'
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
import type { CatalogItem, CatalogKind } from '../../api/catalog'
import { CatalogItemActionsMenu } from './CatalogItemActionsMenu'

const LIST_CONTAINER_MIN = 720

type CatalogListProps = {
  query: string
  onQueryChange: (value: string) => void
  kindFilter: 'all' | CatalogKind
  onKindFilterChange: (value: 'all' | CatalogKind) => void
  kindFilterDisabled: boolean
  items: CatalogItem[]
  total: number
  loading: boolean
  fetchingMore: boolean
  hasMore: boolean
  onLoadMore: () => void
  selected: number[]
  onToggleSelected: (id: number) => void
  onSelectAllVisible: (checked: boolean) => void
  categoryNameOf: (id: number | null) => string
  bulkPending: boolean
  onBulkEnable: () => void
  onBulkDisable: () => void
  onEdit: (item: CatalogItem) => void
  onDuplicate: (item: CatalogItem) => void
  onArchive: (item: CatalogItem) => void
}

export function CatalogList({
  query,
  onQueryChange,
  kindFilter,
  onKindFilterChange,
  kindFilterDisabled,
  items,
  total,
  loading,
  fetchingMore,
  hasMore,
  onLoadMore,
  selected,
  onToggleSelected,
  onSelectAllVisible,
  categoryNameOf,
  bulkPending,
  onBulkEnable,
  onBulkDisable,
  onEdit,
  onDuplicate,
  onArchive,
}: CatalogListProps) {
  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        sx={{ alignItems: { sm: 'center' } }}
      >
        <TextField
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
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
          onChange={(e) => onKindFilterChange(e.target.value as 'all' | CatalogKind)}
          sx={{ minWidth: 160 }}
          disabled={kindFilterDisabled}
        >
          <MenuItem value="all">All kinds</MenuItem>
          <MenuItem value="service">Service</MenuItem>
          <MenuItem value="product">Product</MenuItem>
          <MenuItem value="addon">Add-on</MenuItem>
          <MenuItem value="package">Package</MenuItem>
        </TextField>
        <Button
          variant="outlined"
          disabled={!selected.length || bulkPending}
          onClick={onBulkEnable}
        >
          Enable
        </Button>
        <Button
          variant="outlined"
          disabled={!selected.length || bulkPending}
          onClick={onBulkDisable}
        >
          Disable
        </Button>
      </Stack>

      {loading ? (
        <CircularProgress size={28} />
      ) : items.length === 0 ? (
        <Typography color="text.secondary">No catalog items found.</Typography>
      ) : (
        <Box
          sx={{
            containerType: 'inline-size',
            containerName: 'catalog-list',
          }}
        >
          <Stack
            spacing={1.5}
            sx={{
              display: 'flex',
              [`@container catalog-list (min-width: ${LIST_CONTAINER_MIN}px)`]: {
                display: 'none',
              },
            }}
          >
            {items.map((row) => (
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
                    onChange={() => onToggleSelected(row.id)}
                    slotProps={{ input: { 'aria-label': `Select ${row.name}` } }}
                  />
                  <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle1">{row.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {row.kind} · {categoryNameOf(row.category_id)}
                    </Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                      {row.active ? null : <Chip size="small" label="Disabled" />}
                      {row.bookable ? (
                        <Chip size="small" label="Bookable" variant="outlined" />
                      ) : null}
                    </Stack>
                  </Stack>
                  <CatalogItemActionsMenu
                    item={row}
                    onEdit={onEdit}
                    onDuplicate={onDuplicate}
                    onArchive={onArchive}
                  />
                </Stack>
              </Box>
            ))}
          </Stack>

          <TableContainer
            sx={{
              display: 'none',
              [`@container catalog-list (min-width: ${LIST_CONTAINER_MIN}px)`]: {
                display: 'block',
              },
            }}
          >
            <Table size="small" aria-label="Catalog items">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      indeterminate={
                        selected.length > 0 && selected.length < items.length
                      }
                      checked={items.length > 0 && selected.length === items.length}
                      onChange={(e) => onSelectAllVisible(e.target.checked)}
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
                {items.map((row) => (
                  <TableRow key={row.id} hover selected={selected.includes(row.id)}>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selected.includes(row.id)}
                        onChange={() => onToggleSelected(row.id)}
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
                      <CatalogItemActionsMenu
                        item={row}
                        onEdit={onEdit}
                        onDuplicate={onDuplicate}
                        onArchive={onArchive}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          Showing {items.length} of {total}
        </Typography>
        {hasMore ? (
          <Button variant="outlined" disabled={fetchingMore} onClick={onLoadMore}>
            {fetchingMore ? 'Loading…' : 'Load more'}
          </Button>
        ) : null}
      </Stack>
    </Stack>
  )
}
