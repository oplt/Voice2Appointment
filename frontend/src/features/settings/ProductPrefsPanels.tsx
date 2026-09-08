import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Alert from '@mui/material/Alert'
import Checkbox from '@mui/material/Checkbox'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getProductPrefs, patchProductPrefs } from '../../api/users'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { ProductPrefs } from '../../types'

export type PrefSection = 'notifications' | 'privacy' | 'handoff' | 'languages'

type ProductPrefsPanelsProps = {
  /** Progressive disclosure: Settings vs Agent surface different sections. */
  sections?: PrefSection[]
  saveLabel?: string
}

const ALL_SECTIONS: PrefSection[] = ['notifications', 'privacy', 'handoff', 'languages']

export function ProductPrefsPanels({
  sections = ALL_SECTIONS,
  saveLabel = 'Save product settings',
}: ProductPrefsPanelsProps) {
  const { notify } = useSnackbar()
  const [prefs, setPrefs] = useState<ProductPrefs | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [transcriptConsent, setTranscriptConsent] = useState(false)

  const show = (section: PrefSection) => sections.includes(section)

  const updatePrefs = (update: (current: ProductPrefs) => ProductPrefs) => {
    setPrefs((current) => (current ? update(current) : current))
  }

  const load = () => {
    getProductPrefs()
      .then((loaded) => {
        setPrefs(loaded)
        setTranscriptConsent(false)
      })
      .catch((err: unknown) => {
        setPrefs(null)
        setLoadError(err instanceof ApiError ? err.message : 'Could not load product settings.')
      })
      .finally(() => setLoading(false))
  }

  const retryLoad = () => {
    setLoading(true)
    setLoadError(null)
    load()
  }

  useEffect(() => {
    load()
  }, [])

  const save = async () => {
    if (!prefs) return
    setSaving(true)
    try {
      const saved = await patchProductPrefs({
        ...prefs,
        transcript_storage_consent: transcriptConsent,
      })
      setPrefs(saved)
      setTranscriptConsent(false)
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

  if (!prefs) {
    return (
      <Stack spacing={2} sx={{ maxWidth: 560 }}>
        <Alert severity="error">{loadError ?? 'Could not load product settings.'}</Alert>
        <Button variant="outlined" onClick={retryLoad}>
          Retry loading settings
        </Button>
      </Stack>
    )
  }

  const requiresTranscriptConsent =
    show('privacy') && prefs.transcripts.storage_enabled && !prefs.transcripts.consent_at

  return (
    <Stack spacing={3} sx={{ maxWidth: 560 }}>
      {show('notifications') ? (
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
                  updatePrefs((p) => ({
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
                  updatePrefs((p) => ({
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
              updatePrefs((p) => ({
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
                updatePrefs((p) => ({
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
                updatePrefs((p) => ({
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
      ) : null}

      {show('privacy') ? (
        <Stack spacing={1.5}>
          <Typography variant="h3">Privacy & retention</Typography>
          <FormControlLabel
            control={
              <Switch
                checked={prefs.transcripts.storage_enabled}
                onChange={(e) => {
                  updatePrefs((p) => ({
                    ...p,
                    transcripts: { ...p.transcripts, storage_enabled: e.target.checked },
                  }))
                  if (!e.target.checked) setTranscriptConsent(false)
                }}
              />
            }
            label="Store voice transcripts"
          />
          {requiresTranscriptConsent ? (
            <Stack spacing={1}>
              <Alert severity="warning">
                Confirm that you have obtained permission before storing call transcripts.
              </Alert>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={transcriptConsent}
                    onChange={(e) => setTranscriptConsent(e.target.checked)}
                  />
                }
                label="I confirm that transcript storage consent has been obtained"
              />
            </Stack>
          ) : null}
          <FormControlLabel
            control={
              <Switch
                checked={prefs.transcripts.redact_phone_numbers}
                onChange={(e) =>
                  updatePrefs((p) => ({
                    ...p,
                    transcripts: { ...p.transcripts, redact_phone_numbers: e.target.checked },
                  }))
                }
              />
            }
            label="Redact phone numbers in stored transcripts"
          />
          {prefs.transcripts.consent_at ? (
            <Typography variant="caption" color="text.secondary">
              Transcript storage consent recorded {prefs.transcripts.consent_at}
            </Typography>
          ) : null}
          <TextField
            label="Transcript retention (days)"
            type="number"
            value={prefs.retention.transcript_days}
            onChange={(e) =>
              updatePrefs((p) => ({
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
              updatePrefs((p) => ({
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
                  updatePrefs((p) => ({
                    ...p,
                    retention: { ...p.retention, legal_hold: e.target.checked },
                  }))
                }
              />
            }
            label="Legal hold (pause automatic deletion)"
          />
        </Stack>
      ) : null}

      {show('handoff') ? (
        <Stack spacing={1.5}>
          <Typography variant="h3">Human handoff</Typography>
          <FormControlLabel
            control={
              <Switch
                checked={prefs.transfer.enabled}
                onChange={(e) =>
                  updatePrefs((p) => ({
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
              updatePrefs((p) => ({
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
                  updatePrefs((p) => ({
                    ...p,
                    transfer: { ...p.transfer, business_hours_only: e.target.checked },
                  }))
                }
              />
            }
            label="Only during business hours"
          />
        </Stack>
      ) : null}

      {show('languages') ? (
        <Stack spacing={1.5}>
          <Typography variant="h3">Languages</Typography>
          <Alert severity="info">
            Multilingual calls stay gated (P6-05) until evaluation thresholds pass. Primary language
            is English.
          </Alert>
        </Stack>
      ) : null}

      <Button
        variant="contained"
        loading={saving}
        disabled={saving || (requiresTranscriptConsent && !transcriptConsent)}
        onClick={() => void save()}
      >
        {saveLabel}
      </Button>
    </Stack>
  )
}
