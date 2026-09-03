import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Alert from '@mui/material/Alert'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getProductPrefs, putProductPrefs } from '../../api/users'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { ProductPrefs } from '../../types'

const DEFAULT_PREFS: ProductPrefs = {
  notifications: {
    channel: 'email',
    confirmations_enabled: false,
    reminders_enabled: false,
    consent_at: null,
    quiet_hours_start: null,
    quiet_hours_end: null,
    reminder_hours_before: 24,
  },
  retention: {
    transcript_days: 30,
    recording_days: 14,
    legal_hold: false,
  },
  transfer: {
    enabled: false,
    destination_e164: null,
    business_hours_only: false,
  },
  languages: {
    primary: 'en',
    enabled: ['en'],
  },
}

export function ProductPrefsPanels() {
  const { notify } = useSnackbar()
  const [prefs, setPrefs] = useState<ProductPrefs>(DEFAULT_PREFS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getProductPrefs()
      .then(setPrefs)
      .catch(() => setPrefs(DEFAULT_PREFS))
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const saved = await putProductPrefs(prefs)
      setPrefs(saved)
      notify('Product settings saved', 'success')
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Typography color="text.secondary">Loading…</Typography>
  }

  return (
    <Stack spacing={3} sx={{ maxWidth: 560 }}>
      <Stack spacing={1.5}>
        <Typography variant="h3">Notifications</Typography>
        <Typography variant="body2" color="text.secondary">
          Email channel only. Enabling options records consent. Quiet hours use the calendar
          timezone.
        </Typography>
        <FormControlLabel
          control={
            <Switch
              checked={prefs.notifications.confirmations_enabled}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  notifications: {
                    ...p.notifications,
                    confirmations_enabled: e.target.checked,
                  },
                }))
              }
            />
          }
          label="Send booking confirmations"
        />
        <FormControlLabel
          control={
            <Switch
              checked={prefs.notifications.reminders_enabled}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  notifications: {
                    ...p.notifications,
                    reminders_enabled: e.target.checked,
                  },
                }))
              }
            />
          }
          label="Send appointment reminders"
        />
        <TextField
          label="Reminder hours before"
          type="number"
          value={prefs.notifications.reminder_hours_before}
          onChange={(e) =>
            setPrefs((p) => ({
              ...p,
              notifications: {
                ...p.notifications,
                reminder_hours_before: Number(e.target.value) || 24,
              },
            }))
          }
          slotProps={{ htmlInput: { min: 1, max: 168 } }}
        />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            label="Quiet hours start (HH:MM)"
            value={prefs.notifications.quiet_hours_start ?? ''}
            onChange={(e) =>
              setPrefs((p) => ({
                ...p,
                notifications: {
                  ...p.notifications,
                  quiet_hours_start: e.target.value || null,
                },
              }))
            }
            fullWidth
          />
          <TextField
            label="Quiet hours end (HH:MM)"
            value={prefs.notifications.quiet_hours_end ?? ''}
            onChange={(e) =>
              setPrefs((p) => ({
                ...p,
                notifications: {
                  ...p.notifications,
                  quiet_hours_end: e.target.value || null,
                },
              }))
            }
            fullWidth
          />
        </Stack>
        {prefs.notifications.consent_at ? (
          <Typography variant="caption" color="text.secondary">
            Consent recorded {prefs.notifications.consent_at}
          </Typography>
        ) : null}
      </Stack>

      <Stack spacing={1.5}>
        <Typography variant="h3">Privacy & retention</Typography>
        <TextField
          label="Transcript retention (days)"
          type="number"
          value={prefs.retention.transcript_days}
          onChange={(e) =>
            setPrefs((p) => ({
              ...p,
              retention: {
                ...p.retention,
                transcript_days: Number(e.target.value) || 30,
              },
            }))
          }
          slotProps={{ htmlInput: { min: 1, max: 365 } }}
        />
        <TextField
          label="Recording retention (days)"
          type="number"
          value={prefs.retention.recording_days}
          onChange={(e) =>
            setPrefs((p) => ({
              ...p,
              retention: {
                ...p.retention,
                recording_days: Number(e.target.value) || 14,
              },
            }))
          }
          slotProps={{ htmlInput: { min: 1, max: 365 } }}
        />
        <FormControlLabel
          control={
            <Switch
              checked={prefs.retention.legal_hold}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  retention: { ...p.retention, legal_hold: e.target.checked },
                }))
              }
            />
          }
          label="Legal hold (pause automatic deletion)"
        />
      </Stack>

      <Stack spacing={1.5}>
        <Typography variant="h3">Human handoff</Typography>
        <FormControlLabel
          control={
            <Switch
              checked={prefs.transfer.enabled}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  transfer: { ...p.transfer, enabled: e.target.checked },
                }))
              }
            />
          }
          label="Enable live call transfer"
        />
        <TextField
          label="Transfer destination (E.164)"
          value={prefs.transfer.destination_e164 ?? ''}
          onChange={(e) =>
            setPrefs((p) => ({
              ...p,
              transfer: { ...p.transfer, destination_e164: e.target.value || null },
            }))
          }
          placeholder="+15551234567"
          fullWidth
        />
        <FormControlLabel
          control={
            <Switch
              checked={prefs.transfer.business_hours_only}
              onChange={(e) =>
                setPrefs((p) => ({
                  ...p,
                  transfer: { ...p.transfer, business_hours_only: e.target.checked },
                }))
              }
            />
          }
          label="Only during business hours"
        />
      </Stack>

      <Stack spacing={1.5}>
        <Typography variant="h3">Languages</Typography>
        <Alert severity="info">
          Multilingual calls stay gated (P6-05) until evaluation thresholds pass. Primary language
          is English.
        </Alert>
      </Stack>

      <Button variant="contained" loading={saving} disabled={saving} onClick={() => void save()}>
        Save product settings
      </Button>
    </Stack>
  )
}
