import CloudDoneOutlinedIcon from '@mui/icons-material/CloudDoneOutlined'
import KeyOutlinedIcon from '@mui/icons-material/KeyOutlined'
import LinkOffOutlinedIcon from '@mui/icons-material/LinkOffOutlined'
import PersonOutlinedIcon from '@mui/icons-material/PersonOutlined'
import PhoneOutlinedIcon from '@mui/icons-material/PhoneOutlined'
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'

import { disconnectGoogleCalendar, getCalendarStatus } from '../../api/calendars'
import { ApiError } from '../../api/client'
import { getMe, updateMe } from '../../api/users'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { CalendarStatus, UserProfile } from '../../types'

const SECRET_PLACEHOLDER = '••••••••'

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

type VoiceForm = {
  deepgram_api_key: string
}

export function SettingsPanels() {
  const { notify } = useSnackbar()
  const [tab, setTab] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [calStatus, setCalStatus] = useState<CalendarStatus | null>(null)

  const [account, setAccount] = useState<AccountForm>({ username: '', email: '' })
  const [calendar, setCalendar] = useState<CalendarForm>({ calendar_id: '', time_zone: '' })
  const [telephony, setTelephony] = useState<TelephonyForm>({
    twilio_account_sid: '',
    twilio_auth_token: '',
    twilio_phone_number: '',
  })
  const [voice, setVoice] = useState<VoiceForm>({ deepgram_api_key: '' })
  const [configJson, setConfigJson] = useState('')
  const [saving, setSaving] = useState(false)
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)

  const applyProfile = (next: UserProfile, status: CalendarStatus | null) => {
    setProfile(next)
    setAccount({ username: next.username, email: next.email })
    setCalendar({
      calendar_id: next.calendar_id ?? status?.calendar_id ?? '',
      time_zone: next.time_zone ?? status?.time_zone ?? '',
    })
    setTelephony({
      twilio_account_sid: next.twilio_account_sid ?? '',
      twilio_auth_token: next.twilio_auth_token_set ? SECRET_PLACEHOLDER : '',
      twilio_phone_number: next.twilio_phone_number ?? '',
    })
    setVoice({
      deepgram_api_key: next.deepgram_api_key_set ? SECRET_PLACEHOLDER : '',
    })
    setConfigJson(next.config_json ?? '')
  }

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      getMe(),
      getCalendarStatus().catch(() => null),
    ])
      .then(([me, status]) => {
        setCalStatus(status)
        applyProfile(me, status)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load settings')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

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
        subtitle="Account, calendar, telephony, voice, and agent config."
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
            <Tab icon={<TuneOutlinedIcon />} iconPosition="start" label="Config" />
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
                OAuth connect stays on the backend. Tokens never appear in the browser.
              </Alert>
              <TextField
                label="Calendar ID"
                value={calendar.calendar_id}
                onChange={(e) => setCalendar((c) => ({ ...c, calendar_id: e.target.value }))}
                fullWidth
                placeholder="primary"
              />
              <TextField
                label="Time zone"
                value={calendar.time_zone}
                onChange={(e) => setCalendar((c) => ({ ...c, time_zone: e.target.value }))}
                fullWidth
                placeholder="Europe/Brussels"
              />
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  disabled={saving}
                  loading={saving}
                  onClick={() =>
                    savePatch(
                      {
                        calendar_id: calendar.calendar_id.trim() || null,
                        time_zone: calendar.time_zone.trim() || null,
                      },
                      'Calendar settings saved',
                    )
                  }
                >
                  Save
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<LinkOffOutlinedIcon />}
                  onClick={() => setDisconnectOpen(true)}
                  disabled={!calStatus?.connected}
                >
                  Disconnect
                </Button>
              </Stack>
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
                Deepgram (speech-to-text) for the voice assistant.
              </Typography>
              <TextField
                label="Deepgram API Key"
                type="password"
                value={voice.deepgram_api_key}
                onChange={(e) => setVoice({ deepgram_api_key: e.target.value })}
                fullWidth
                autoComplete="new-password"
                helperText={
                  profile?.deepgram_api_key_set
                    ? 'Leave masked value unchanged to keep the existing key.'
                    : undefined
                }
              />
              <Button
                variant="contained"
                disabled={saving}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  const body: Parameters<typeof updateMe>[0] = {}
                  if (
                    voice.deepgram_api_key &&
                    voice.deepgram_api_key !== SECRET_PLACEHOLDER
                  ) {
                    body.deepgram_api_key = voice.deepgram_api_key
                  } else if (!voice.deepgram_api_key) {
                    body.deepgram_api_key = null
                  }
                  if (Object.keys(body).length === 0) {
                    notify('No changes to save', 'info')
                    return
                  }
                  void savePatch(body, 'Voice settings saved')
                }}
              >
                Save voice
              </Button>
            </Stack>
          ) : null}

          {tab === 4 ? (
            <Stack spacing={2} sx={{ maxWidth: 640 }}>
              <TextField
                label="Config JSON"
                multiline
                minRows={10}
                fullWidth
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
                placeholder='{"agent": {...}}'
                slotProps={{
                  input: { sx: { fontFamily: 'ui-monospace, monospace', fontSize: 13 } },
                }}
              />
              <Button
                variant="contained"
                disabled={saving}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  if (configJson.trim()) {
                    try {
                      JSON.parse(configJson)
                    } catch {
                      notify('Config must be valid JSON', 'error')
                      return
                    }
                  }
                  void savePatch(
                    { config_json: configJson.trim() || null },
                    'Config saved',
                  )
                }}
              >
                Save config
              </Button>
            </Stack>
          ) : null}
        </>
      )}

      <ConfirmDialog
        open={disconnectOpen}
        title="Disconnect Google Calendar?"
        description="Stored OAuth tokens will be revoked for this account."
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
