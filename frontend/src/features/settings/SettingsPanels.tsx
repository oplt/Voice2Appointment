import CloudDoneOutlinedIcon from '@mui/icons-material/CloudDoneOutlined'
import ChecklistOutlinedIcon from '@mui/icons-material/ChecklistOutlined'
import KeyOutlinedIcon from '@mui/icons-material/KeyOutlined'
import LinkOffOutlinedIcon from '@mui/icons-material/LinkOffOutlined'
import PersonOutlinedIcon from '@mui/icons-material/PersonOutlined'
import PhoneOutlinedIcon from '@mui/icons-material/PhoneOutlined'
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined'
import PolicyOutlinedIcon from '@mui/icons-material/PolicyOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { disconnectGoogleCalendar, getCalendarStatus, startGoogleCalendarConnect, updateCalendarPreferences } from '../../api/calendars'
import { ApiError } from '../../api/client'
import { getBookingPolicy, getMe, putBookingPolicy, updateMe } from '../../api/users'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { BookingPolicy, CalendarStatus, UserProfile } from '../../types'
import { ProductPrefsPanels } from './ProductPrefsPanels'
import { SetupChecklist } from './SetupChecklist'

const SECRET_PLACEHOLDER = '••••••••'
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

function validTimezone(value: string) {
  try { Intl.DateTimeFormat(undefined, { timeZone: value }); return true } catch { return false }
}

function validPolicy(policy: BookingPolicy): string | null {
  if (Object.entries(policy.service_durations_minutes).some(([name, minutes]) => !name.trim() || !Number.isInteger(minutes) || minutes < 5 || minutes > 480)) return 'Each service needs a name and a duration between 5 and 480 minutes.'
  for (const [day, windows] of Object.entries(policy.business_hours)) {
    if (windows.some((window) => !/^\d{2}:\d{2}$/.test(window.start) || !/^\d{2}:\d{2}$/.test(window.end) || window.start >= window.end)) return `${day} business hours must have an end after the start.`
  }
  return null
}

type AccountForm = {
  username: string
  email: string
}

type CalendarForm = {
  calendar_id: string
  time_zone: string
}

type TelephonyForm = {
  twilio_account_sid: string
  twilio_auth_token: string
  twilio_phone_number: string
}

export function SettingsPanels() {
  const { notify } = useSnackbar()
  const [tab, setTab] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [calStatus, setCalStatus] = useState<CalendarStatus | null>(null)
  const [calendarError, setCalendarError] = useState<string | null>(null)
  const [policyError, setPolicyError] = useState<string | null>(null)
  const [policyLoaded, setPolicyLoaded] = useState(false)

  const [account, setAccount] = useState<AccountForm>({ username: '', email: '' })
  const [calendar, setCalendar] = useState<CalendarForm>({ calendar_id: '', time_zone: '' })
  const [telephony, setTelephony] = useState<TelephonyForm>({
    twilio_account_sid: '',
    twilio_auth_token: '',
    twilio_phone_number: '',
  })
  const [policy, setPolicy] = useState<BookingPolicy>({
    default_service_duration_minutes: 30,
    service_durations_minutes: {},
    buffer_before_minutes: 0,
    buffer_after_minutes: 0,
    business_hours: {},
  })
  const [saving, setSaving] = useState(false)
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const applyProfile = (next: UserProfile, status: CalendarStatus | null) => {
    setProfile(next)
    setAccount({ username: next.username, email: next.email })
    if (status) {
      setCalendar({
        calendar_id: status.calendar_id ?? '',
        time_zone: status.time_zone ?? '',
      })
    }
    setTelephony({
      twilio_account_sid: next.twilio_account_sid ?? '',
      twilio_auth_token: next.twilio_auth_token_set ? SECRET_PLACEHOLDER : '',
      twilio_phone_number: next.twilio_phone_number ?? '',
    })
  }

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getMe()
      .then((me) => applyProfile(me, null))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load settings')
      })
      .finally(() => setLoading(false))
    setCalendarError(null)
    getCalendarStatus()
      .then((status) => {
        setCalStatus(status)
        setCalendar({ calendar_id: status.calendar_id ?? '', time_zone: status.time_zone ?? '' })
      })
      .catch((err: unknown) => {
        setCalendarError(err instanceof ApiError ? err.message : 'Failed to load calendar settings')
      })
    setPolicyError(null)
    setPolicyLoaded(false)
    getBookingPolicy()
      .then((booking) => {
        setPolicy(booking)
        setPolicyLoaded(true)
      })
      .catch((err: unknown) => {
        setPolicyError(err instanceof ApiError ? err.message : 'Failed to load booking policy')
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

  const savePatch = async (body: Parameters<typeof updateMe>[0], successMsg: string) => {
    setSaving(true)
    try {
      const next = await updateMe(body)
      applyProfile(next, calStatus)
      notify(successMsg, 'success')
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    } finally {
      setSaving(false)
    }
  }

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
    <Stack spacing={3}>
      <PageHeader
        title="Settings"
        subtitle="Account, calendar, telephony, voice, and booking policy."
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

      {loading ? (
        <Stack spacing={2}>
          <Skeleton variant="rounded" height={48} />
          <Skeleton variant="rounded" height={200} />
        </Stack>
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={(_, value: number) => setTab(value)}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="Settings sections"
          >
            <Tab icon={<PersonOutlinedIcon />} iconPosition="start" label="Account" />
            <Tab icon={<CloudDoneOutlinedIcon />} iconPosition="start" label="Calendar" />
            <Tab icon={<PhoneOutlinedIcon />} iconPosition="start" label="Telephony" />
            <Tab icon={<KeyOutlinedIcon />} iconPosition="start" label="Voice" />
            <Tab icon={<TuneOutlinedIcon />} iconPosition="start" label="Booking" />
            <Tab icon={<PolicyOutlinedIcon />} iconPosition="start" label="Product" />
            <Tab icon={<ChecklistOutlinedIcon />} iconPosition="start" label="Setup" />
          </Tabs>

          {tab === 0 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              <TextField
                label="Username"
                value={account.username}
                onChange={(e) => setAccount((a) => ({ ...a, username: e.target.value }))}
                fullWidth
                autoComplete="username"
              />
              <TextField
                label="Email"
                type="email"
                value={account.email}
                onChange={(e) => setAccount((a) => ({ ...a, email: e.target.value }))}
                fullWidth
                autoComplete="email"
              />
              <Button
                variant="contained"
                disabled={saving}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() =>
                  savePatch(
                    { username: account.username.trim(), email: account.email.trim() },
                    'Account updated',
                  )
                }
              >
                Save account
              </Button>
            </Stack>
          ) : null}

          {tab === 1 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              {calendarError ? (
                <Alert severity="error" action={<Button color="inherit" size="small" onClick={load}>Retry</Button>}>
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
                Connect Google Calendar with a secure server-side OAuth flow. Tokens
                never appear in the browser.
              </Alert>
              <Stack direction="row" spacing={2}>
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
            </Stack>
          ) : null}

          {tab === 2 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              <TextField
                label="Account SID"
                value={telephony.twilio_account_sid}
                onChange={(e) =>
                  setTelephony((t) => ({ ...t, twilio_account_sid: e.target.value }))
                }
                fullWidth
                autoComplete="off"
              />
              <TextField
                label="Auth Token"
                type="password"
                value={telephony.twilio_auth_token}
                onChange={(e) =>
                  setTelephony((t) => ({ ...t, twilio_auth_token: e.target.value }))
                }
                fullWidth
                autoComplete="new-password"
                helperText={
                  profile?.twilio_auth_token_set
                    ? 'Leave masked value unchanged to keep the existing token.'
                    : undefined
                }
              />
              <TextField
                label="Phone Number"
                value={telephony.twilio_phone_number}
                onChange={(e) =>
                  setTelephony((t) => ({ ...t, twilio_phone_number: e.target.value }))
                }
                fullWidth
              />
              <Button
                variant="contained"
                disabled={saving}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  const phone = telephony.twilio_phone_number.trim()
                  if (phone && !/^\+[1-9]\d{6,14}$/.test(phone)) {
                    notify('Phone number must use E.164 format, for example +32470123456.', 'error')
                    return
                  }
                  const body: Parameters<typeof updateMe>[0] = {
                    twilio_account_sid: telephony.twilio_account_sid.trim() || null,
                    twilio_phone_number: telephony.twilio_phone_number.trim() || null,
                  }
                  if (
                    telephony.twilio_auth_token &&
                    telephony.twilio_auth_token !== SECRET_PLACEHOLDER
                  ) {
                    body.twilio_auth_token = telephony.twilio_auth_token
                  }
                  void savePatch(body, 'Telephony settings saved')
                }}
              >
                Save telephony
              </Button>
            </Stack>
          ) : null}

          {tab === 3 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              <Typography variant="body2" color="text.secondary">
                Speech is powered by a platform-managed Deepgram credential
                (<code>DEEPGRAM_API_KEY</code>). Per-account keys are not collected.
              </Typography>
              <Alert severity={profile?.has_deepgram ? 'success' : 'warning'}>
                {profile?.has_deepgram
                  ? 'Deepgram is configured on the server.'
                  : 'Deepgram is not configured. Ask an administrator to set DEEPGRAM_API_KEY.'}
              </Alert>
            </Stack>
          ) : null}

          {tab === 4 ? (
            <Stack spacing={2} sx={{ maxWidth: 560 }}>
              <Typography variant="body2" color="text.secondary">
                Typed booking rules used by HTTP appointments and voice tools.
              </Typography>
              <TextField
                label="Default duration (minutes)"
                type="number"
                value={policy.default_service_duration_minutes}
                onChange={(e) =>
                  setPolicy((p) => ({
                    ...p,
                    default_service_duration_minutes: Number(e.target.value) || 30,
                  }))
                }
                fullWidth
                slotProps={{ htmlInput: { min: 5, max: 480 } }}
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Buffer before (minutes)"
                  type="number"
                  value={policy.buffer_before_minutes}
                  onChange={(e) =>
                    setPolicy((p) => ({
                      ...p,
                      buffer_before_minutes: Number(e.target.value) || 0,
                    }))
                  }
                  fullWidth
                  slotProps={{ htmlInput: { min: 0, max: 240 } }}
                />
                <TextField
                  label="Buffer after (minutes)"
                  type="number"
                  value={policy.buffer_after_minutes}
                  onChange={(e) =>
                    setPolicy((p) => ({
                      ...p,
                      buffer_after_minutes: Number(e.target.value) || 0,
                    }))
                  }
                  fullWidth
                  slotProps={{ htmlInput: { min: 0, max: 240 } }}
                />
              </Stack>
              {policyError ? <Alert severity="error" action={<Button color="inherit" size="small" onClick={load}>Retry</Button>}>{policyError}</Alert> : null}
              <Typography variant="subtitle2">Named service durations</Typography>
              {Object.entries(policy.service_durations_minutes).map(([name, minutes]) => (
                <Stack key={name} direction="row" spacing={1}>
                  <TextField label="Service" value={name} fullWidth onChange={(e) => setPolicy((p) => { const next = { ...p.service_durations_minutes }; delete next[name]; next[e.target.value] = minutes; return { ...p, service_durations_minutes: next } })} />
                  <TextField label="Minutes" type="number" value={minutes} sx={{ width: 130 }} slotProps={{ htmlInput: { min: 5, max: 480 } }} onChange={(e) => setPolicy((p) => ({ ...p, service_durations_minutes: { ...p.service_durations_minutes, [name]: Number(e.target.value) || 0 } }))} />
                  <IconButton aria-label={`Remove ${name}`} onClick={() => setPolicy((p) => { const next = { ...p.service_durations_minutes }; delete next[name]; return { ...p, service_durations_minutes: next } })}>×</IconButton>
                </Stack>
              ))}
              <Button sx={{ alignSelf: 'flex-start' }} onClick={() => setPolicy((p) => ({ ...p, service_durations_minutes: { ...p.service_durations_minutes, 'New service': 30 } }))}>Add service</Button>
              <Typography variant="subtitle2">Business hours</Typography>
              {DAYS.map((day) => {
                const window = policy.business_hours[day]?.[0]
                return <Stack key={day} direction={{ xs: 'column', sm: 'row' }} spacing={1}><Button variant={window ? 'text' : 'outlined'} sx={{ width: 110, textTransform: 'capitalize' }} onClick={() => !window && setPolicy((p) => ({ ...p, business_hours: { ...p.business_hours, [day]: [{ start: '09:00', end: '17:00' }] } }))}>{day}</Button>{window ? <><TextField label="Start" type="time" value={window.start} onChange={(e) => setPolicy((p) => ({ ...p, business_hours: { ...p.business_hours, [day]: [{ ...window, start: e.target.value }] } }))} /><TextField label="End" type="time" value={window.end} onChange={(e) => setPolicy((p) => ({ ...p, business_hours: { ...p.business_hours, [day]: [{ ...window, end: e.target.value }] } }))} /><IconButton aria-label={`Remove ${day} hours`} onClick={() => setPolicy((p) => { const next = { ...p.business_hours }; delete next[day]; return { ...p, business_hours: next } })}>×</IconButton></> : null}</Stack>
              })}
              <Button
                variant="contained"
                disabled={saving || !policyLoaded}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  const invalid = validPolicy(policy)
                  if (invalid) {
                    notify(invalid, 'error')
                    return
                  }
                  setSaving(true)
                  putBookingPolicy(policy)
                    .then((saved) => {
                      setPolicy(saved)
                      notify('Booking policy saved', 'success')
                    })
                    .catch((err: unknown) => {
                      notify(
                        err instanceof ApiError ? err.message : 'Failed to save policy',
                        'error',
                      )
                    })
                    .finally(() => setSaving(false))
                }}
              >
                Save booking policy
              </Button>
            </Stack>
          ) : null}

          {tab === 5 ? <ProductPrefsPanels /> : null}
          {tab === 6 ? <SetupChecklist /> : null}
        </>
      )}

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
