import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { getCall, listCalls } from '../api/calls'
import { PageHeader } from '../components/PageHeader'
import type { CallSession } from '../types'

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

function formatDuration(seconds?: number | null) {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

export function CallsPage() {
  const [calls, setCalls] = useState<CallSession[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<CallSession | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback((cursor?: string | null) => {
    const more = Boolean(cursor)
    if (more) setLoadingMore(true)
    else {
      setLoading(true)
      setError(null)
    }
    listCalls({ limit: 25, cursor: cursor || undefined })
      .then((page) => {
        setCalls((prev) => (more ? [...prev, ...page.items] : page.items))
        setNextCursor(page.next_cursor ?? null)
      })
      .catch((err: unknown) => {
        if (!more) {
          setCalls([])
          setError(err instanceof ApiError ? err.message : 'Failed to load calls')
        }
      })
      .finally(() => {
        setLoading(false)
        setLoadingMore(false)
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openDetail = async (call: CallSession) => {
    setDetailLoading(true)
    try {
      const full = await getCall(call.id, call.has_transcript === true)
      setDetail(full)
    } catch (err: unknown) {
      setDetail({
        ...call,
        transcript:
          err instanceof ApiError ? `Unable to load details: ${err.message}` : null,
      })
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Calls"
        subtitle="Tenant call sessions with status, duration, and outcome."
        actions={
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip icon={<PhoneInTalkOutlinedIcon />} label="Sessions" variant="outlined" />
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => load()}
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
            <Button color="inherit" size="small" onClick={() => load()}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <Stack spacing={1}>
          <Skeleton variant="rounded" height={40} />
          <Skeleton variant="rounded" height={40} />
        </Stack>
      ) : !error && calls.length === 0 ? (
        <Alert severity="info">No call sessions yet.</Alert>
      ) : calls.length > 0 ? (
        <Stack spacing={2}>
          {/* Mobile cards */}
          <Stack spacing={1.5} sx={{ display: { xs: 'flex', md: 'none' } }}>
            {calls.map((call) => (
              <Box
                key={call.id}
                component="button"
                type="button"
                onClick={() => void openDetail(call)}
                sx={{
                  textAlign: 'left',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  p: 1.5,
                  bgcolor: 'background.paper',
                  cursor: 'pointer',
                  minHeight: 44,
                }}
              >
                <Typography variant="subtitle2">{call.call_sid}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {call.from_number ?? '—'} · {call.status}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatWhen(call.started_at)} · {formatDuration(call.duration_seconds)}
                </Typography>
              </Box>
            ))}
          </Stack>

          <TableContainer sx={{ display: { xs: 'none', md: 'block' }, overflowX: 'auto' }}>
            <Table size="small" aria-label="Call sessions">
              <TableHead>
                <TableRow>
                  <TableCell>Call SID</TableCell>
                  <TableCell>From</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Outcome</TableCell>
                  <TableCell>Started</TableCell>
                  <TableCell>Duration</TableCell>
                  <TableCell align="right">Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {calls.map((call) => (
                  <TableRow key={call.id} hover>
                    <TableCell>{call.call_sid}</TableCell>
                    <TableCell>{call.from_number ?? '—'}</TableCell>
                    <TableCell>
                      <Chip size="small" label={call.status} variant="outlined" />
                    </TableCell>
                    <TableCell>{call.outcome ?? '—'}</TableCell>
                    <TableCell>{formatWhen(call.started_at)}</TableCell>
                    <TableCell>{formatDuration(call.duration_seconds)}</TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => void openDetail(call)}>
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {nextCursor ? (
            <Button
              variant="outlined"
              onClick={() => load(nextCursor)}
              loading={loadingMore}
              sx={{ alignSelf: 'flex-start' }}
            >
              Load more
            </Button>
          ) : null}
        </Stack>
      ) : null}

      <Dialog
        open={detail != null || detailLoading}
        onClose={() => setDetail(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Call details</DialogTitle>
        <DialogContent dividers>
          {detailLoading && !detail ? (
            <Skeleton height={120} />
          ) : detail ? (
            <Stack spacing={1.5}>
              <Typography variant="body2">SID: {detail.call_sid}</Typography>
              <Typography variant="body2">Status: {detail.status}</Typography>
              <Typography variant="body2">Outcome: {detail.outcome ?? '—'}</Typography>
              <Typography variant="body2">From: {detail.from_number ?? '—'}</Typography>
              <Typography variant="body2">Started: {formatWhen(detail.started_at)}</Typography>
              <Typography variant="body2">
                Duration: {formatDuration(detail.duration_seconds)}
              </Typography>
              {detail.transcript ? (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Transcript
                  </Typography>
                  <Typography
                    component="pre"
                    variant="body2"
                    sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}
                  >
                    {detail.transcript}
                  </Typography>
                </Box>
              ) : detail.has_transcript === false ? (
                <Typography variant="body2" color="text.secondary">
                  No transcript stored for this call.
                </Typography>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetail(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
