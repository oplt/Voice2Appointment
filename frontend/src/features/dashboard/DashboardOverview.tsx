import AddIcon from '@mui/icons-material/Add'
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined'
import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined'
import EventOutlinedIcon from '@mui/icons-material/EventOutlined'
import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import Grid from '@mui/material/Grid'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { getDashboardSummary } from '../../api/dashboard'
import { PageHeader } from '../../components/PageHeader'
import { useApiHealth } from '../../hooks/useApiHealth'
import type { DashboardSummary } from '../../types'
import { designTokens } from '../../theme/tokens'

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

export function DashboardOverview() {
  const apiHealth = useApiHealth()
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getDashboardSummary()
      .then(setSummary)
      .catch((err: unknown) => {
        setSummary(null)
        setError(err instanceof ApiError ? err.message : 'Failed to load dashboard')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const kpis = [
    {
      label: 'Calls today',
      value: summary?.operational?.calls_today?.value ?? summary?.call_statistics?.calls_today ?? '—',
      to: '/calls',
      hint: summary?.operational?.calls_today?.definition,
    },
    {
      label: 'Booked today',
      value:
        summary?.operational?.appointments_booked_today?.value ??
        summary?.appointments_today ??
        '—',
      to: '/appointments',
      hint: summary?.operational?.appointments_booked_today?.definition,
    },
    {
      label: 'Completion',
      value:
        summary?.operational?.completion_rate?.value != null
          ? `${Math.round(summary.operational.completion_rate.value * 100)}%`
          : summary?.call_statistics?.completion_rate != null
            ? `${Math.round(summary.call_statistics.completion_rate * 100)}%`
            : '—',
      to: '/calls',
      hint: summary?.operational?.completion_rate?.definition,
    },
    {
      label: 'Needs attention',
      value:
        summary?.operational?.attention_needed?.value ??
        summary?.call_statistics?.attention_today ??
        '—',
      to: '/calls',
      hint: summary?.operational?.attention_needed?.definition,
    },
    {
      label: 'Upcoming',
      value:
        summary?.operational?.upcoming_appointments?.value ??
        summary?.upcoming?.length ??
        '—',
      to: '/appointments',
      hint: summary?.operational?.upcoming_appointments?.definition,
    },
  ] as const

  const provider = summary?.provider_status
  const callsToday =
    summary?.operational?.calls_today?.value ?? summary?.call_statistics?.calls_today
  const recentCallsCount = summary?.recent_calls
  const timezoneLabel = summary?.timezone
  const generatedAt = summary?.generated_at
  const stale = summary?.freshness?.stale

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Dashboard"
        subtitle={
          timezoneLabel
            ? `What matters now — appointments, calendar, and providers (${timezoneLabel}).`
            : 'What matters now — appointments, calendar, and providers.'
        }
        actions={
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Chip
              label={
                apiHealth.status === 'ok'
                  ? 'API ok'
                  : apiHealth.status === 'loading'
                    ? 'API…'
                    : 'API down'
              }
              color={apiHealth.status === 'ok' ? 'success' : 'default'}
              variant="outlined"
              onClick={apiHealth.refresh}
              aria-label="Refresh API health"
            />
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

      <Grid container spacing={2}>
        {kpis.map((card) => (
          <Grid key={card.label} size={{ xs: 12, sm: 6, md: 4, lg: 2.4 }}>
            <Card
              component={RouterLink}
              to={card.to}
              title={card.hint}
              sx={{
                textDecoration: 'none',
                display: 'block',
                bgcolor: designTokens.colors.lightAsh,
                border: `1px solid ${designTokens.colors.cloudGray}`,
              }}
            >
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="body2" color="text.secondary">
                    {card.label}
                  </Typography>
                  {loading ? (
                    <Skeleton width={64} height={36} />
                  ) : (
                    <Typography variant="h3">{card.value}</Typography>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {stale ? (
        <Alert severity="warning">
          Twilio analytics sync looks stale
          {summary?.freshness?.source_synced_at
            ? ` (last sync ${formatWhen(summary.freshness.source_synced_at)})`
            : ''}
          . Refresh from Analytics.
        </Alert>
      ) : null}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Stack spacing={1.5}>
            <Typography variant="h3">Upcoming appointments</Typography>
            {loading ? (
              <Stack spacing={1}>
                <Skeleton variant="rounded" height={56} />
                <Skeleton variant="rounded" height={56} />
              </Stack>
            ) : !summary?.upcoming?.length ? (
              <Alert severity="info">
                No upcoming appointments. Create one from Appointments.
              </Alert>
            ) : (
              <List disablePadding>
                {summary.upcoming.slice(0, 6).map((item) => (
                  <ListItem
                    key={item.id}
                    divider
                    sx={{ px: 0 }}
                    secondaryAction={
                      <Chip label={item.status} size="small" variant="outlined" />
                    }
                  >
                    <ListItemText
                      primary={item.summary}
                      secondary={formatWhen(item.start_datetime)}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, md: 5 }}>
          <Stack spacing={2}>
            <Stack spacing={1}>
              <Typography variant="h3">Status</Typography>
              {loading ? (
                <Skeleton width={160} height={32} />
              ) : (
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                  <Chip
                    icon={<CalendarMonthOutlinedIcon />}
                    label={
                      summary?.calendar_connected ? 'Calendar connected' : 'Calendar offline'
                    }
                    color={summary?.calendar_connected ? 'success' : 'default'}
                    variant="outlined"
                  />
                  {callsToday != null ? (
                    <Chip
                      icon={<PhoneInTalkOutlinedIcon />}
                      label={`${callsToday} calls today`}
                      variant="outlined"
                    />
                  ) : null}
                  {typeof recentCallsCount === 'number' ? (
                    <Chip
                      component={RouterLink}
                      to="/calls"
                      clickable
                      icon={<PhoneInTalkOutlinedIcon />}
                      label={`${recentCallsCount} calls (7d)`}
                      variant="outlined"
                    />
                  ) : null}
                </Stack>
              )}
              {generatedAt ? (
                <Typography variant="caption" color="text.secondary">
                  Generated {formatWhen(generatedAt)}
                </Typography>
              ) : null}
            </Stack>

            <Stack spacing={1}>
              <Typography variant="h3">Providers</Typography>
              {loading ? (
                <Skeleton width={200} height={32} />
              ) : (
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                  <Chip
                    label={provider?.twilio ? 'Twilio ready' : 'Twilio not configured'}
                    size="small"
                    variant="outlined"
                    color={provider?.twilio ? 'success' : 'default'}
                  />
                  <Chip
                    label={provider?.deepgram ? 'Deepgram ready' : 'Deepgram not configured'}
                    size="small"
                    variant="outlined"
                    color={provider?.deepgram ? 'success' : 'default'}
                  />
                  <Chip
                    label={
                      (provider?.calendar ?? summary?.calendar_connected)
                        ? 'Calendar ready'
                        : 'Calendar not connected'
                    }
                    size="small"
                    variant="outlined"
                    color={
                      (provider?.calendar ?? summary?.calendar_connected) ? 'success' : 'default'
                    }
                  />
                </Stack>
              )}
            </Stack>

            <Stack spacing={1}>
              <Typography variant="h3">Quick actions</Typography>
              <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                <Button
                  component={RouterLink}
                  to="/appointments"
                  variant="contained"
                  startIcon={<AddIcon />}
                >
                  New appointment
                </Button>
                <Button
                  component={RouterLink}
                  to="/calendar"
                  variant="outlined"
                  startIcon={<EventOutlinedIcon />}
                >
                  Calendar
                </Button>
                <Button
                  component={RouterLink}
                  to="/analytics"
                  variant="outlined"
                  startIcon={<AnalyticsOutlinedIcon />}
                >
                  Analytics
                </Button>
                <Button
                  component={RouterLink}
                  to="/settings"
                  variant="outlined"
                  startIcon={<SettingsOutlinedIcon />}
                >
                  Settings
                </Button>
              </Stack>
            </Stack>
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  )
}
