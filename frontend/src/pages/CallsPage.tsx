import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { getDashboardSummary } from '../api/dashboard'
import { PageHeader } from '../components/PageHeader'
import type { RecentCall } from '../types'

function formatWhen(iso?: string | null) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

export function CallsPage() {
  const [calls, setCalls] = useState<RecentCall[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    setUnavailable(false)
    getDashboardSummary()
      .then((summary) => {
        setCalls(summary.recent_calls ?? [])
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 404 || err.status === 501)) {
          setUnavailable(true)
          setCalls([])
          return
        }
        setError(err instanceof ApiError ? err.message : 'Failed to load calls')
        setCalls([])
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Calls"
        subtitle="Recent Twilio call sessions from the dashboard summary."
        actions={
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip icon={<PhoneInTalkOutlinedIcon />} label="Sessions" variant="outlined" />
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={load}
              disabled={loading}
              aria-label="Refresh calls"
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {unavailable ? (
        <Alert severity="info">
          Call session API is not available yet. This page will list sessions when the backend
          exposes them.
        </Alert>
      ) : null}

      {loading ? (
        <Stack spacing={1}>
          <Skeleton variant="rounded" height={40} />
          <Skeleton variant="rounded" height={40} />
        </Stack>
      ) : !unavailable && !error && calls.length === 0 ? (
        <Alert severity="info">No recent calls to show.</Alert>
      ) : calls.length > 0 ? (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Call SID</TableCell>
              <TableCell>From</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Started</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {calls.map((call) => (
              <TableRow key={call.call_sid} hover>
                <TableCell>{call.call_sid}</TableCell>
                <TableCell>{call.from_number ?? '—'}</TableCell>
                <TableCell>{call.status ?? '—'}</TableCell>
                <TableCell>{formatWhen(call.started_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </Stack>
  )
}
