import CancelOutlinedIcon from '@mui/icons-material/CancelOutlined'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'

import type { AppointmentListItem } from '../../types'
import { formatAppointmentTime } from './form'
import type { AppointmentScope } from './useAppointmentsList'

type Props = {
  items: AppointmentListItem[]
  scope: AppointmentScope
  loading: boolean
  loadingMore: boolean
  error: string | null
  hasMore: boolean
  onScope: (scope: AppointmentScope) => void
  onRetry: () => void
  onLoadMore: () => void
  onView: (item: AppointmentListItem) => void
  onEdit: (item: AppointmentListItem) => void
  onCancel: (item: AppointmentListItem) => void
}

function Actions({ item, onView, onEdit, onCancel }: Pick<Props, 'onView' | 'onEdit' | 'onCancel'> & { item: AppointmentListItem }) {
  const disabled = item.status === 'cancelled'
  return (
    <>
      <IconButton aria-label={`View appointment ${item.summary}`} size="small" onClick={() => onView(item)}><VisibilityOutlinedIcon fontSize="small" /></IconButton>
      <IconButton aria-label={`Reschedule appointment ${item.summary}`} size="small" onClick={() => onEdit(item)} disabled={disabled}><EditOutlinedIcon fontSize="small" /></IconButton>
      <IconButton aria-label={`Cancel appointment ${item.summary}`} size="small" onClick={() => onCancel(item)} disabled={disabled}><CancelOutlinedIcon fontSize="small" /></IconButton>
    </>
  )
}

export function AppointmentList(props: Props) {
  const { items, scope, loading, loadingMore, error, hasMore } = props
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }} aria-label="Appointment time range">
        {(['upcoming', 'history', 'all'] as const).map((value) => (
          <Button key={value} variant={scope === value ? 'contained' : 'outlined'} aria-pressed={scope === value} onClick={() => props.onScope(value)}>
            {value[0].toUpperCase() + value.slice(1)}
          </Button>
        ))}
      </Stack>
      {error ? <Alert severity="error" action={<Button color="inherit" size="small" onClick={props.onRetry}>Retry</Button>}>{error}</Alert> : null}
      {loading ? (
        <Stack spacing={1}>{[1, 2, 3].map((key) => <Skeleton key={key} variant="rounded" height={40} />)}</Stack>
      ) : items.length === 0 && !error ? (
        <Alert severity="info">No {scope === 'all' ? '' : `${scope} `}appointments.</Alert>
      ) : (
        <>
          <Stack spacing={1.5} sx={{ display: { xs: 'flex', md: 'none' } }}>
            {items.map((item) => (
              <Box key={item.id} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
                <Stack spacing={1}>
                  <Typography variant="subtitle1">{item.summary}</Typography>
                  <Typography variant="body2" color="text.secondary">{formatAppointmentTime(item.start_datetime)}</Typography>
                  <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}><Chip size="small" label={item.status} variant="outlined" /><Chip size="small" label={item.provider_sync_status} variant="outlined" /></Stack>
                  <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap' }}><Actions item={item} onView={props.onView} onEdit={props.onEdit} onCancel={props.onCancel} /></Stack>
                </Stack>
              </Box>
            ))}
          </Stack>
          <TableContainer sx={{ display: { xs: 'none', md: 'block' }, overflowX: 'auto' }}>
            <Table size="small" aria-label="Appointments">
              <TableHead><TableRow><TableCell>Summary</TableCell><TableCell>Start</TableCell><TableCell>Client</TableCell><TableCell>Status</TableCell><TableCell>Sync</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead>
              <TableBody>{items.map((item) => (
                <TableRow key={item.id} hover>
                  <TableCell>{item.summary}</TableCell><TableCell>{formatAppointmentTime(item.start_datetime)}</TableCell><TableCell>—</TableCell><TableCell><Chip size="small" label={item.status} variant="outlined" /></TableCell><TableCell><Chip size="small" label={item.provider_sync_status} variant="outlined" /></TableCell>
                  <TableCell align="right"><Actions item={item} onView={props.onView} onEdit={props.onEdit} onCancel={props.onCancel} /></TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
          </TableContainer>
          {hasMore ? <Button onClick={props.onLoadMore} loading={loadingMore} sx={{ alignSelf: 'center' }}>Load more appointments</Button> : null}
        </>
      )}
    </Stack>
  )
}
