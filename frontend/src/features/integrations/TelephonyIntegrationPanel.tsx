import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getMe, updateMe } from '../../api/users'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { UserProfile } from '../../types'

const SECRET_PLACEHOLDER = '••••••••'

/** Twilio telephony credentials (Integrations → Phone). */
export function TelephonyIntegrationPanel() {
  const { notify } = useSnackbar()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [telephony, setTelephony] = useState({
    twilio_account_sid: '',
    twilio_auth_token: '',
    twilio_phone_number: '',
  })

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getMe()
      .then((me) => {
        setProfile(me)
        setTelephony({
          twilio_account_sid: me.twilio_account_sid ?? '',
          twilio_auth_token: me.twilio_auth_token_set ? SECRET_PLACEHOLDER : '',
          twilio_phone_number: me.twilio_phone_number ?? '',
        })
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load telephony settings')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <Stack spacing={2} sx={{ maxWidth: 480 }}>
        <Skeleton variant="rounded" height={56} />
        <Skeleton variant="rounded" height={56} />
        <Skeleton variant="rounded" height={56} />
      </Stack>
    )
  }

  if (error) {
    return (
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
    )
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      <TextField
        label="Account SID"
        value={telephony.twilio_account_sid}
        onChange={(e) => setTelephony((t) => ({ ...t, twilio_account_sid: e.target.value }))}
        fullWidth
        autoComplete="off"
      />
      <TextField
        label="Auth Token"
        type="password"
        value={telephony.twilio_auth_token}
        onChange={(e) => setTelephony((t) => ({ ...t, twilio_auth_token: e.target.value }))}
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
        onChange={(e) => setTelephony((t) => ({ ...t, twilio_phone_number: e.target.value }))}
        fullWidth
        helperText="E.164 format, for example +32470123456"
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
          if (telephony.twilio_auth_token && telephony.twilio_auth_token !== SECRET_PLACEHOLDER) {
            body.twilio_auth_token = telephony.twilio_auth_token
          }
          setSaving(true)
          updateMe(body)
            .then((next) => {
              setProfile(next)
              setTelephony({
                twilio_account_sid: next.twilio_account_sid ?? '',
                twilio_auth_token: next.twilio_auth_token_set ? SECRET_PLACEHOLDER : '',
                twilio_phone_number: next.twilio_phone_number ?? '',
              })
              notify('Telephony settings saved', 'success')
            })
            .catch((err: unknown) => {
              notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
            })
            .finally(() => setSaving(false))
        }}
      >
        Save telephony
      </Button>
    </Stack>
  )
}
