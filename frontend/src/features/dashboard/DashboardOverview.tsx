import AddIcon from '@mui/icons-material/Add'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { Link as RouterLink } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { getDashboardSummary } from '../../api/dashboard'
import { queryKeys } from '../../api/queryKeys'
import { queryStaleTime } from '../../app/queryClient'
import { PageHeader } from '../../components/PageHeader'
import { useApiHealth } from '../../hooks/useApiHealth'

function formatWhen(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function formatTodayLabel(timezone?: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      timeZone: timezone || undefined,
    }).format(new Date())
  } catch {
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    }).format(new Date())
  }
}

function Metric({
  label,
  value,
  to,
  loading,
}: {
  label: string
  value: string | number
  to: string
  loading: boolean
}) {
  return (
    <Box
      component={RouterLink}
      to={to}
      sx={{
        textDecoration: 'none',
        color: 'inherit',
        display: 'block',
        py: 1,
        minWidth: 0,
        flex: '1 1 0',
        minHeight: 72,
        transition: 'opacity 0.2s',
        '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
        '&:hover': { opacity: 0.85 },
        '&:focus-visible': {
          outline: '3px solid var(--action-primary)',
          outlineOffset: 2,
        },
      }}
    >
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      {loading ? (
        <Skeleton width={48} height={36} />
      ) : (
        <Typography variant="h2" sx={{ mt: 0.5, lineHeight: 1.2 }}>
          {value}
        </Typography>
      )}
    </Box>
  )
}

function HealthRow({ label, ok, detail }: { label: string; ok: boolean | null; detail?: string }) {
  const tone =
    ok === null ? 'var(--text-secondary)' : ok ? 'var(--status-success)' : 'var(--status-warning)'
  return (
    <Stack
      direction="row"
      spacing={1.5}
      sx={{ alignItems: 'baseline', justifyContent: 'space-between', py: 0.5 }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Stack spacing={0} sx={{ alignItems: 'flex-end' }}>
        <Typography variant="body2" sx={{ color: tone, fontWeight: 500 }}>
          {ok === null ? '…' : ok ? 'OK' : 'Needs setup'}
        </Typography>
        {detail ? (
          <Typography variant="caption" color="text.secondary">
            {detail}
          </Typography>
        ) : null}
      </Stack>
    </Stack>
  )
}

export function DashboardOverview() {
  const apiHealth = useApiHealth()
  const summaryQuery = useQuery({
    queryKey: queryKeys.dashboard.summary,
    queryFn: ({ signal }) => getDashboardSummary(signal),
    staleTime: queryStaleTime.dashboard,
  })
  const summary = summaryQuery.data ?? null
  const loading = summaryQuery.isPending
  const error =
    summaryQuery.error == null
      ? null
      : summaryQuery.error instanceof ApiError
        ? summaryQuery.error.message
        : 'Failed to load dashboard'

  const load = () => {
    void summaryQuery.refetch()
  }

  const callsToday =
    summary?.operational?.calls_today?.value ?? summary?.call_statistics?.calls_today ?? '—'
  const bookingsToday =
    summary?.operational?.appointments_booked_today?.value ??
    summary?.appointments_today ??
    '—'
  const completion =
    summary?.operational?.completion_rate?.value != null
      ? `${Math.round(summary.operational.completion_rate.value * 100)}%`
      : summary?.call_statistics?.completion_rate != null
        ? `${Math.round(summary.call_statistics.completion_rate * 100)}%`
        : '—'
  const attention =
    summary?.operational?.attention_needed?.value ??
    summary?.call_statistics?.attention_today ??
    0

  const attentionCount = typeof attention === 'number' ? attention : 0
  const timezoneLabel = summary?.timezone
  const stale = summary?.freshness?.stale
  const provider = summary?.provider_status
  const assistantOk =
    apiHealth.status === 'loading' ? null : apiHealth.status === 'ok' && Boolean(provider?.deepgram)
  const calendarOk = summary
    ? Boolean(provider?.calendar ?? summary.calendar_connected)
    : null
  const telephonyOk = summary ? Boolean(provider?.twilio) : null

  return (
    <Stack spacing={4}>
      <PageHeader
        title="Today"
        subtitle={
          timezoneLabel
            ? `${formatTodayLabel(timezoneLabel)} · ${timezoneLabel}`
            : formatTodayLabel()
        }
        actions={
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Button
              variant="contained"
              component={RouterLink}
              to="/reservations"
              startIcon={<AddIcon />}
            >
              New booking
            </Button>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={load}
              disabled={loading}
              aria-label="Refresh dashboard"
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

      {stale ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/analytics">
              Analytics
            </Button>
          }
        >
          Twilio analytics sync looks stale
          {summary?.freshness?.source_synced_at
            ? ` (last sync ${formatWhen(summary.freshness.source_synced_at)})`
            : ''}
          .
        </Alert>
      ) : null}

      {/* 1. Attention */}
      <Stack spacing={1.25}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'baseline', justifyContent: 'space-between' }}
        >
          <Typography variant="h3">Needs attention</Typography>
          <Button component={RouterLink} to="/calls" size="small">
            Open calls
          </Button>
        </Stack>
        {loading ? (
          <Skeleton variant="rounded" height={40} width="60%" />
        ) : attentionCount > 0 ? (
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Typography variant="body1">
              <Box component="span" sx={{ fontWeight: 600 }}>
                {attentionCount}
              </Box>{' '}
              call{attentionCount === 1 ? '' : 's'} need follow-up today.
            </Typography>
            <Button
              component={RouterLink}
              to="/calls"
              variant="outlined"
              sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
            >
              Review attention queue
            </Button>
          </Stack>
        ) : (
          <Typography variant="body1" color="text.secondary">
            Nothing needs attention right now.
          </Typography>
        )}
      </Stack>

      {/* 2. Today's metrics */}
      <Stack spacing={1}>
        <Typography variant="overline" color="text.secondary">
          Today
        </Typography>
        <Stack
          direction="row"
          spacing={0}
          divider={<Divider orientation="vertical" flexItem />}
          sx={{
            flexWrap: 'wrap',
            columnGap: 3,
            rowGap: 1,
            '& > *': { minWidth: 100 },
          }}
        >
          <Metric label="Calls" value={callsToday} to="/calls" loading={loading} />
          <Metric label="Bookings" value={bookingsToday} to="/reservations" loading={loading} />
          <Metric label="Completion" value={completion} to="/calls" loading={loading} />
          <Metric label="Attention" value={attention} to="/calls" loading={loading} />
        </Stack>
      </Stack>

      {/* 3. Upcoming */}
      <Stack spacing={1.25}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'baseline', justifyContent: 'space-between' }}
        >
          <Typography variant="h3">Upcoming</Typography>
          <Button component={RouterLink} to="/reservations" size="small">
            All bookings
          </Button>
        </Stack>
        {loading ? (
          <Stack spacing={1}>
            <Skeleton variant="text" width="70%" />
            <Skeleton variant="text" width="55%" />
            <Skeleton variant="text" width="60%" />
          </Stack>
        ) : !summary?.upcoming?.length ? (
          <Typography variant="body1" color="text.secondary">
            No upcoming appointments. Create one from Bookings.
          </Typography>
        ) : (
          <List disablePadding>
            {summary.upcoming.slice(0, 8).map((item) => (
              <ListItem key={item.id} divider sx={{ px: 0 }}>
                <ListItemText
                  primary={item.summary}
                  secondary={`${formatWhen(item.start_datetime)} · ${item.status}`}
                />
              </ListItem>
            ))}
          </List>
        )}
      </Stack>

      {/* 4. System health (secondary) */}
      <Stack spacing={0.5} sx={{ maxWidth: 480, pt: 1 }}>
        <Typography variant="overline" color="text.secondary">
          System health
        </Typography>
        {loading ? (
          <Skeleton width={220} height={72} />
        ) : (
          <>
            <HealthRow
              label="Assistant"
              ok={assistantOk}
              detail={
                apiHealth.status === 'ok'
                  ? provider?.deepgram
                    ? 'API + voice ready'
                    : 'API up · Deepgram not configured'
                  : apiHealth.status === 'loading'
                    ? undefined
                    : 'API unreachable'
              }
            />
            <HealthRow
              label="Calendar"
              ok={calendarOk}
              detail={
                summary?.integrations?.calendar_account
                  ? summary.integrations.calendar_account
                  : undefined
              }
            />
            <HealthRow
              label="Telephony"
              ok={telephonyOk}
              detail={
                summary?.integrations?.twilio_last_synced_at
                  ? `Last sync ${formatWhen(summary.integrations.twilio_last_synced_at)}`
                  : undefined
              }
            />
          </>
        )}
        <Button
          component={RouterLink}
          to="/integrations"
          size="small"
          sx={{ mt: 1, alignSelf: 'flex-start' }}
        >
          Manage integrations
        </Button>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
          KPI definitions live in{' '}
          <Box component={RouterLink} to="/analytics" sx={{ color: 'inherit' }}>
            Analytics
          </Box>
          .
        </Typography>
      </Stack>
    </Stack>
  )
}
