import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader'

const DEMO = [
  { id: 1, book: 'Default', item: 'General consultation', amount: '€65.00', effective: '2026-01-01' },
  { id: 2, book: 'Default', item: 'Haircut', amount: '€40.00', effective: '2026-01-01' },
  { id: 3, book: 'Weekend', item: 'Haircut', amount: '€48.00', effective: '2026-03-01' },
]

export function PricingView() {
  return (
    <Stack spacing={3}>
      <PageHeader
        title="Pricing"
        subtitle="Price books and minor-unit prices by location and effective dates."
      />
      <Alert severity="info">
        Preview table — connect to price-book APIs when exposed. Manage sellable items in{' '}
        <Button component={RouterLink} to="/catalog" size="small">
          Services & Products
        </Button>
        .
      </Alert>
      <Typography variant="body2" color="text.secondary">
        Amounts shown for layout only.
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Price book preview">
          <TableHead>
            <TableRow>
              <TableCell>Price book</TableCell>
              <TableCell>Catalog item</TableCell>
              <TableCell>Amount</TableCell>
              <TableCell>Effective</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {DEMO.map((row) => (
              <TableRow key={row.id}>
                <TableCell>{row.book}</TableCell>
                <TableCell>{row.item}</TableCell>
                <TableCell>{row.amount}</TableCell>
                <TableCell>{row.effective}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  )
}
