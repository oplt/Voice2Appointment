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
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { getCall, listCalls } from '../../api/calls'
import { queryKeys } from '../../api/queryKeys'
import { PageHeader } from '../../components/PageHeader'
import type { CallSession } from '../../types'

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

export function CallsView() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [includeTranscript, setIncludeTranscript] = useState(false)

  const listQuery = useInfiniteQuery({
    queryKey: queryKeys.calls.list,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listCalls({ limit: 25, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })

  const detailQuery = useQuery({
    queryKey: queryKeys.calls.detail(selectedId ?? 0),
    queryFn: () => getCall(selectedId!, includeTranscript),
    enabled: selectedId != null,
  })

  const calls = listQuery.data?.pages.flatMap((page) => page.items) ?? []
  const nextCursor = listQuery.hasNextPage
    ? (listQuery.data?.pages.at(-1)?.next_cursor ?? null)
    : null
  const loading = listQuery.isPending
  const loadingMore = listQuery.isFetchingNextPage
  const error =
    listQuery.error == null
      ? null
      : listQuery.error instanceof ApiError
        ? listQuery.error.message
        : 'Failed to load calls'
  const paginationError =
    listQuery.isFetchNextPageError && listQuery.error instanceof ApiError
      ? listQuery.error.message
      : listQuery.isFetchNextPageError
        ? 'Failed to load more calls'
        : null

  const detail = detailQuery.data ?? null
  const detailLoading = detailQuery.isFetching
  const detailError =
    detailQuery.error == null
      ? null
      : detailQuery.error instanceof ApiError
        ? detailQuery.error.message
        : 'Unable to load call details'

  const openDetail = (call: CallSession) => {
    setIncludeTranscript(call.transcript_available === true)
    setSelectedId(call.id)
  }

  const closeDetail = () => {
    setSelectedId(null)
  }

  const refresh = () => {
    void listQuery.refetch()
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
              onClick={refresh}
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
            <Button color="inherit" size="small" onClick={refresh}>
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
          <Stack spacing={1.5} sx={{ display: { xs: 'flex', md: 'none' } }}>
            {calls.map((call) => (
              <Box
                key={call.id}
                component="button"
                type="button"
                onClick={() => openDetail(call)}
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
                  {call.direction ?? 'unknown'} · {call.summary ?? call.status}
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
                  <TableCell>Direction</TableCell>
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
                    <TableCell>{call.direction ?? 'unknown'}</TableCell>
                    <TableCell>
                      <Chip size="small" label={call.status} variant="outlined" />
                    </TableCell>
                    <TableCell>{call.outcome ?? '—'}</TableCell>
                    <TableCell>{formatWhen(call.started_at)}</TableCell>
                    <TableCell>{formatDuration(call.duration_seconds)}</TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => openDetail(call)}>
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {nextCursor ? (
            <Stack spacing={1} sx={{ alignSelf: 'flex-start' }}>
              {paginationError ? (
                <Alert
                  severity="warning"
                  action={
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => void listQuery.fetchNextPage()}
                    >
                      Retry
                    </Button>
                  }
                >
                  {paginationError}
                </Alert>
              ) : null}
              <Button
                variant="outlined"
                onClick={() => void listQuery.fetchNextPage()}
                loading={loadingMore}
              >
                Load more
              </Button>
            </Stack>
          ) : null}
        </Stack>
      ) : null}

      <Dialog
        open={selectedId != null}
        onClose={closeDetail}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Call details</DialogTitle>
        <DialogContent dividers>
          {detailLoading ? (
            <Skeleton height={120} />
          ) : detailError ? (
            <Alert severity="error">{detailError}</Alert>
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
              ) : detail.transcript_purged ? (
                <Typography variant="body2" color="text.secondary">
                  Transcript is no longer available under the retention policy.
                </Typography>
              ) : detail.has_transcript === false ? (
                <Typography variant="body2" color="text.secondary">
                  No transcript stored for this call.
                </Typography>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDetail}>Close</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
