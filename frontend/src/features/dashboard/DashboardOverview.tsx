import AddIcon from '@mui/icons-material/Add'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Grid from '@mui/material/Grid'
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
        p: 1.5,
        borderRadius: 1,
        border: '1px solid var(--border-subtle)',
        bgcolor: 'var(--surface-secondary)',
        minHeight: 88,
        transition: 'background-color 0.2s',
        '&:hover': { bgcolor: 'var(--surface-primary)' },
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
      sx={{ alignItems: 'baseline', justifyContent: 'space-between', py: 0.75 }}
    >
      <Typography variant="body2">{label}</Typography>
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
    queryFn: getDashboardSummary,
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
    <Stack spacing={3}>
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

      <Grid container spacing={1.5}>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Calls" value={callsToday} to="/calls" loading={loading} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Bookings" value={bookingsToday} to="/reservations" loading={loading} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Completion" value={completion} to="/calls" loading={loading} />
        </Grid>
        <Grid size={{ xs: 6, md: 3 }}>
          <Metric label="Attention" value={attention} to="/calls" loading={loading} />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Box
            sx={{
              border: '1px solid var(--border-subtle)',
              borderRadius: 1,
              p: { xs: 2, sm: 2.5 },
              bgcolor: 'var(--surface-primary)',
              minHeight: 280,
            }}
          >
            <Stack
              direction="row"
              spacing={1}
              sx={{ alignItems: 'baseline', justifyContent: 'space-between', mb: 1.5 }}
            >
              <Typography variant="h3">Needs attention</Typography>
              <Button component={RouterLink} to="/calls" size="small">
                Open calls
              </Button>
            </Stack>
            {loading ? (
              <Stack spacing={1}>
                <Skeleton variant="rounded" height={48} />
                <Skeleton variant="rounded" height={48} />
              </Stack>
            ) : attentionCount > 0 ? (
              <Stack spacing={1.5}>
                <Typography variant="body1">
                  {attentionCount} call{attentionCount === 1 ? '' : 's'} need follow-up today.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Review failed bookings, transfers, and incomplete sessions.
                </Typography>
                <Button
                  component={RouterLink}
                  to="/calls"
                  variant="outlined"
                  sx={{ alignSelf: 'flex-start' }}
                >
                  Review attention queue
                </Button>
              </Stack>
            ) : (
              <Typography variant="body1" color="text.secondary">
                Nothing needs attention right now.
              </Typography>
            )}
          </Box>
        </Grid>

        <Grid size={{ xs: 12, lg: 7 }}>
          <Box
            sx={{
              border: '1px solid var(--border-subtle)',
              borderRadius: 1,
              p: { xs: 2, sm: 2.5 },
              bgcolor: 'var(--surface-primary)',
              minHeight: 280,
            }}
          >
            <Stack
              direction="row"
              spacing={1}
              sx={{ alignItems: 'baseline', justifyContent: 'space-between', mb: 1.5 }}
            >
              <Typography variant="h3">Upcoming</Typography>
              <Button component={RouterLink} to="/reservations" size="small">
                All bookings
              </Button>
            </Stack>
            {loading ? (
              <Stack spacing={1}>
                <Skeleton variant="rounded" height={48} />
                <Skeleton variant="rounded" height={48} />
                <Skeleton variant="rounded" height={48} />
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
          </Box>
        </Grid>
      </Grid>

      <Box
        sx={{
          border: '1px solid var(--border-subtle)',
          borderRadius: 1,
          p: { xs: 2, sm: 2.5 },
          bgcolor: 'var(--surface-secondary)',
          maxWidth: 560,
        }}
      >
        <Typography variant="h3" sx={{ mb: 1 }}>
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
            <Divider />
            <HealthRow
              label="Calendar"
              ok={calendarOk}
              detail={
                summary?.integrations?.calendar_account
                  ? summary.integrations.calendar_account
                  : undefined
              }
            />
            <Divider />
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
          sx={{ mt: 1.5 }}
        >
          Manage integrations
        </Button>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          KPI definitions and exclusions live in{' '}
          <Box component={RouterLink} to="/analytics" sx={{ color: 'inherit' }}>
            Analytics
          </Box>
          .
        </Typography>
      </Box>
    </Stack>
  )
}
