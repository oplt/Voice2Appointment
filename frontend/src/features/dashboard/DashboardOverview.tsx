import AddIcon from '@mui/icons-material/Add'
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined'
import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined'
import EventOutlinedIcon from '@mui/icons-material/EventOutlined'
import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
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
      label: 'Today',
      value: summary?.appointments_today ?? '—',
      to: '/appointments',
    },
    {
      label: 'This week',
      value: summary?.appointments_week ?? '—',
      to: '/appointments',
    },
    {
      label: 'Upcoming',
      value: summary?.upcoming?.length ?? '—',
      to: '/calendar',
    },
  ] as const

  const provider = summary?.provider_status
  const callsToday =
    summary?.call_statistics?.calls_today ??
    summary?.call_statistics?.total_calls ??
    null

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Dashboard"
        subtitle="What matters now — appointments, calendar, and providers."
        actions={
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
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
          <Grid key={card.label} size={{ xs: 12, sm: 4 }}>
            <Card
              component={RouterLink}
              to={card.to}
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
                      label={`${callsToday} calls`}
                      variant="outlined"
                    />
                  ) : null}
                </Stack>
              )}
            </Stack>

            <Stack spacing={1}>
              <Typography variant="h3">Providers</Typography>
              {loading ? (
                <Skeleton width={200} height={32} />
              ) : (
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                  <Chip
                    label={`Twilio: ${provider?.twilio ? 'ready' : '—'}`}
                    size="small"
                    variant="outlined"
                  />
                  <Chip
                    label={`Deepgram: ${provider?.deepgram ? 'ready' : '—'}`}
                    size="small"
                    variant="outlined"
                  />
                  <Chip
                    label={`Calendar: ${(provider?.calendar ?? summary?.calendar_connected) ? 'ready' : '—'}`}
                    size="small"
                    variant="outlined"
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

            {summary?.recent_calls && summary.recent_calls.length > 0 ? (
              <Box>
                <Typography variant="h3" sx={{ mb: 1 }}>
                  Recent calls
                </Typography>
                <List dense disablePadding>
                  {summary.recent_calls.slice(0, 4).map((call) => (
                    <ListItem key={call.call_sid} sx={{ px: 0 }} divider>
                      <ListItemText
                        primary={call.from_number ?? call.call_sid}
                        secondary={call.status ?? '—'}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            ) : null}
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  )
}
