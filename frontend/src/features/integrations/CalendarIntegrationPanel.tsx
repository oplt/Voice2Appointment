import CloudDoneOutlinedIcon from '@mui/icons-material/CloudDoneOutlined'
import LinkOffOutlinedIcon from '@mui/icons-material/LinkOffOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  disconnectGoogleCalendar,
  getCalendarStatus,
  startGoogleCalendarConnect,
  updateCalendarPreferences,
} from '../../api/calendars'
import { ApiError } from '../../api/client'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { CalendarStatus } from '../../types'

function validTimezone(value: string) {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: value })
    return true
  } catch {
    return false
  }
}

/** Google Calendar connect + preferences (Integrations → Calendar). */
export function CalendarIntegrationPanel() {
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const location = useLocation()
  const [calStatus, setCalStatus] = useState<CalendarStatus | null>(null)
  const [calendarError, setCalendarError] = useState<string | null>(null)
  const [calendar, setCalendar] = useState({ calendar_id: '', time_zone: '' })
  const [saving, setSaving] = useState(false)
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  const load = useCallback(() => {
    setCalendarError(null)
    getCalendarStatus()
      .then((status) => {
        setCalStatus(status)
        setCalendar({
          calendar_id: status.calendar_id ?? '',
          time_zone: status.time_zone ?? '',
        })
      })
      .catch((err: unknown) => {
        setCalendarError(err instanceof ApiError ? err.message : 'Failed to load calendar settings')
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const outcome = new URLSearchParams(location.search).get('google')
    if (!outcome) return
    const messages: Record<string, string> = {
      connected: 'Google Calendar connected',
      denied: 'Google Calendar connection was denied',
      error: 'Google Calendar connection failed',
    }
    notify(messages[outcome] ?? messages.error, outcome === 'connected' ? 'success' : 'error')
    navigate(location.pathname, { replace: true })
    load()
  }, [load, location.pathname, location.search, navigate, notify])

  const onDisconnect = async () => {
    setDisconnecting(true)
    try {
      await disconnectGoogleCalendar()
      notify('Google Calendar disconnected', 'success')
      setDisconnectOpen(false)
      load()
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Disconnect failed', 'error')
    } finally {
      setDisconnecting(false)
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      {calendarError ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {calendarError}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Chip
          label={calStatus?.connected ? 'Connected' : 'Not connected'}
          color={calStatus?.connected ? 'success' : 'default'}
          variant="outlined"
        />
        {calStatus?.account_email ? (
          <Typography variant="body2" color="text.secondary">
            {calStatus.account_email}
          </Typography>
        ) : null}
      </Stack>
      <Alert severity="info">
        Connect Google Calendar with a secure server-side OAuth flow. Tokens never appear in the
        browser.
      </Alert>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap' }}>
        <Button
          variant="contained"
          startIcon={<CloudDoneOutlinedIcon />}
          disabled={saving}
          onClick={() => {
            void startGoogleCalendarConnect()
              .then((res) => {
                window.location.assign(res.authorization_url)
              })
              .catch((err: unknown) => {
                notify(
                  err instanceof ApiError ? err.message : 'Failed to start Google connect',
                  'error',
                )
              })
          }}
        >
          Connect Google
        </Button>
        <Button
          variant="outlined"
          color="error"
          startIcon={<LinkOffOutlinedIcon />}
          onClick={() => setDisconnectOpen(true)}
          disabled={!calStatus?.connected || Boolean(calendarError)}
        >
          Disconnect
        </Button>
      </Stack>
      <TextField
        label="Calendar ID"
        value={calendar.calendar_id}
        onChange={(e) => setCalendar((c) => ({ ...c, calendar_id: e.target.value }))}
        fullWidth
        placeholder="primary"
        disabled={!calStatus?.connected || Boolean(calendarError)}
      />
      <TextField
        label="Time zone"
        value={calendar.time_zone}
        onChange={(e) => setCalendar((c) => ({ ...c, time_zone: e.target.value }))}
        fullWidth
        placeholder="Europe/Brussels"
        disabled={!calStatus?.connected}
        helperText="IANA name, for example Europe/Brussels"
      />
      <Button
        variant="contained"
        disabled={saving || !calStatus?.connected || Boolean(calendarError)}
        loading={saving}
        sx={{ alignSelf: 'flex-start' }}
        onClick={() => {
          const timezone = calendar.time_zone.trim()
          if (timezone && !validTimezone(timezone)) {
            notify('Time zone must be a valid IANA name, for example Europe/Brussels.', 'error')
            return
          }
          setSaving(true)
          updateCalendarPreferences({
            calendar_id: calendar.calendar_id.trim() || 'primary',
            time_zone: timezone || undefined,
          })
            .then((status) => {
              setCalStatus(status)
              notify('Calendar settings saved', 'success')
            })
            .catch((err: unknown) => {
              notify(
                err instanceof ApiError ? err.message : 'Failed to save calendar settings',
                'error',
              )
            })
            .finally(() => setSaving(false))
        }}
      >
        Save calendar preferences
      </Button>

      <ConfirmDialog
        open={disconnectOpen}
        title="Disconnect Google Calendar?"
        description="This disconnect clears the stored calendar credentials for this account."
        confirmLabel="Disconnect"
        confirmColor="error"
        loading={disconnecting}
        onClose={() => {
          if (!disconnecting) setDisconnectOpen(false)
        }}
        onConfirm={onDisconnect}
      />
    </Stack>
  )
}
