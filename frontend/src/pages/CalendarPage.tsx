import EventAvailableOutlinedIcon from '@mui/icons-material/EventAvailableOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import {
  checkCalendarAvailability,
  getCalendarEmbed,
  getCalendarStatus,
  listCalendarEvents,
} from '../api/calendars'
import { ApiError } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { useSnackbar } from '../components/SnackbarProvider'
import type { CalendarEvent, CalendarStatus } from '../types'

function formatWhen(iso: string | undefined, timezone: string | null | undefined) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: timezone ?? undefined,
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function defaultRange() {
  const now = new Date()
  const end = new Date(now)
  end.setDate(end.getDate() + 14)
  return { timeMin: now.toISOString(), timeMax: end.toISOString() }
}

function safeExternalUrl(url?: string | null): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'https:' && ['calendar.google.com', 'www.google.com'].includes(parsed.hostname)) return parsed.toString()
  } catch {
    return null
  }
  return null
}

export function CalendarPage() {
  const { notify } = useSnackbar()
  const [status, setStatus] = useState<CalendarStatus | null>(null)
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [statusLoading, setStatusLoading] = useState(true)
  const [eventsLoading, setEventsLoading] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [embedUrl, setEmbedUrl] = useState<string | null>(null)
  const [embedError, setEmbedError] = useState<string | null>(null)

  const [availStart, setAvailStart] = useState('')
  const [availEnd, setAvailEnd] = useState('')
  const [availResult, setAvailResult] = useState<string | null>(null)
  const [availLoading, setAvailLoading] = useState(false)

  const range = useMemo(() => defaultRange(), [])

  const load = useCallback(() => {
    setStatusLoading(true)
    setStatusError(null)
    setEventsError(null)
    setEmbedError(null)
    setEmbedUrl(null)
    getCalendarStatus()
      .then((nextStatus) => {
        setStatus(nextStatus)
        if (!nextStatus.connected) {
          setEvents([])
          setEventsLoading(false)
          return
        }
        setEventsLoading(true)
        void getCalendarEmbed()
          .then((embed) => setEmbedUrl(safeExternalUrl(embed.embed_url)))
          .catch((err: unknown) => setEmbedError(err instanceof ApiError ? err.message : 'Failed to load calendar embed'))
        return listCalendarEvents({ ...range, timezone: nextStatus.time_zone ?? undefined })
          .then((result) => setEvents(result.items))
          .catch((err: unknown) => {
            setEvents([])
            setEventsError(err instanceof ApiError ? err.message : 'Failed to load events')
          })
          .finally(() => setEventsLoading(false))
      })
      .catch((err: unknown) => {
        setStatus(null)
        setEvents([])
        setStatusError(err instanceof ApiError ? err.message : 'Failed to load calendar status')
      })
      .finally(() => setStatusLoading(false))
  }, [range])

  useEffect(() => {
    load()
  }, [load])

  const onCheckAvailability = async (event: FormEvent) => {
    event.preventDefault()
    setAvailResult(null)
    if (!availStart || !availEnd) {
      setAvailResult('Start and end are required')
      return
    }
    setAvailLoading(true)
    try {
      const data = await checkCalendarAvailability({
        start: new Date(availStart).toISOString(),
        end: new Date(availEnd).toISOString(),
      })
      if (Array.isArray(data)) {
        const free = data.filter((s) => s.available).length
        setAvailResult(`${free} of ${data.length} slots available`)
      } else if (typeof data.available === 'boolean') {
        setAvailResult(data.available ? 'Available' : 'Not available')
      } else {
        const slots = data.slots ?? []
        const free = slots.filter((s) => s.available).length
        setAvailResult(`${free} of ${slots.length} slots available`)
      }
      notify('Availability checked', 'success')
    } catch (err: unknown) {
      setAvailResult(err instanceof ApiError ? err.message : 'Availability check failed')
    } finally {
      setAvailLoading(false)
    }
  }

  const loading = statusLoading || eventsLoading

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Calendar"
        subtitle="Google Calendar embed and upcoming events."
        actions={
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={load}
            disabled={loading}
            aria-label="Refresh calendar"
          >
            Refresh
          </Button>
        }
      />

      {statusError ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {statusError}
        </Alert>
      ) : null}

      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
      >
        {statusLoading ? (
          <Skeleton width={180} height={32} />
        ) : (
          <>
            <Chip
              label={status?.connected ? 'Connected' : 'Not connected'}
              color={status?.connected ? 'success' : 'default'}
              variant="outlined"
            />
            {status?.account_email ? (
              <Typography variant="body2" color="text.secondary">
                {status.account_email}
              </Typography>
            ) : null}
            {status?.time_zone ? (
              <Typography variant="body2" color="text.secondary">
                {status.time_zone}
              </Typography>
            ) : null}
          </>
        )}
      </Stack>

      {statusLoading ? (
        <Skeleton variant="rounded" height={420} />
      ) : embedUrl ? (
        <Box
          component="iframe"
          title="Google Calendar"
          src={embedUrl}
          sx={{
            width: '100%',
            height: { xs: 360, md: 520 },
            border: 0,
            borderRadius: 1,
          }}
        />
      ) : !statusError ? (
        <Alert
          severity="info"
          action={
            !status?.connected ? (
              <Button color="inherit" size="small" component={RouterLink} to="/settings">
                Open Settings
              </Button>
            ) : undefined
          }
        >
          {status?.connected
            ? embedError ?? 'Calendar embed is unavailable. Events still appear below.'
            : 'Connect Google Calendar in Settings to see your schedule.'}
        </Alert>
      ) : null}

      <Stack spacing={1.5}>
        <Typography variant="h3">Events (next 14 days)</Typography>
        {eventsError ? (
          <Alert
            severity="warning"
            action={
              <Button color="inherit" size="small" onClick={load}>
                Retry
              </Button>
            }
          >
            {eventsError}
          </Alert>
        ) : null}
        {eventsLoading ? (
          <Stack spacing={1}>
            <Skeleton variant="rounded" height={48} />
            <Skeleton variant="rounded" height={48} />
          </Stack>
        ) : !status?.connected && !statusLoading ? (
          <Alert severity="info">Connect Google Calendar to load events.</Alert>
        ) : events.length === 0 && !eventsError ? (
          <Alert severity="info">No events in this range.</Alert>
        ) : (
          <List disablePadding>
            {events.map((ev) => {
              const link = safeExternalUrl(ev.url)
              const when = ev.allDay
                ? `${ev.start} (all day)`
                : `${formatWhen(ev.start, status?.time_zone)}${ev.end ? ` – ${formatWhen(ev.end, status?.time_zone)}` : ''}`
              return (
                <ListItem key={ev.id} divider sx={{ px: 0 }}>
                  <ListItemText primary={ev.title || '(No title)'} secondary={when} />
                  {link ? (
                    <Button
                      href={link}
                      target="_blank"
                      rel="noopener noreferrer"
                      size="small"
                      variant="text"
                    >
                      Open
                    </Button>
                  ) : null}
                </ListItem>
              )
            })}
          </List>
        )}
      </Stack>

      <Stack
        component="form"
        onSubmit={onCheckAvailability}
        spacing={2}
        sx={{ maxWidth: 560 }}
      >
        <Typography variant="h3">Check availability</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            label="Start"
            type="datetime-local"
            value={availStart}
            onChange={(e) => setAvailStart(e.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="End"
            type="datetime-local"
            value={availEnd}
            onChange={(e) => setAvailEnd(e.target.value)}
            fullWidth
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </Stack>
        <Button
          type="submit"
          variant="contained"
          startIcon={<EventAvailableOutlinedIcon />}
          loading={availLoading}
          disabled={!status?.connected}
          sx={{ alignSelf: 'flex-start' }}
        >
          Check
        </Button>
        {availResult ? <Alert severity="info">{availResult}</Alert> : null}
      </Stack>
    </Stack>
  )
}
