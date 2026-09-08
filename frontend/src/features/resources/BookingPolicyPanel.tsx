import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getBookingPolicy, putBookingPolicy } from '../../api/users'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { BookingPolicy } from '../../types'

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

function validPolicy(policy: BookingPolicy): string | null {
  if (
    Object.entries(policy.service_durations_minutes).some(
      ([name, minutes]) =>
        !name.trim() || !Number.isInteger(minutes) || minutes < 5 || minutes > 480,
    )
  ) {
    return 'Each service needs a name and a duration between 5 and 480 minutes.'
  }
  for (const [day, windows] of Object.entries(policy.business_hours)) {
    if (
      windows.some(
        (window) =>
          !/^\d{2}:\d{2}$/.test(window.start) ||
          !/^\d{2}:\d{2}$/.test(window.end) ||
          window.start >= window.end,
      )
    ) {
      return `${day} business hours must have an end after the start.`
    }
  }
  return null
}

/** Business hours + booking buffers (Business → Resources). */
export function BookingPolicyPanel() {
  const { notify } = useSnackbar()
  const [policy, setPolicy] = useState<BookingPolicy>({
    default_service_duration_minutes: 30,
    service_durations_minutes: {},
    buffer_before_minutes: 0,
    buffer_after_minutes: 0,
    business_hours: {},
  })
  const [policyError, setPolicyError] = useState<string | null>(null)
  const [policyLoaded, setPolicyLoaded] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
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

  if (!policyLoaded && !policyError) {
    return (
      <Stack spacing={2} sx={{ maxWidth: 560 }}>
        <Skeleton variant="rounded" height={56} />
        <Skeleton variant="rounded" height={120} />
      </Stack>
    )
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 560 }}>
      <Typography variant="body2" color="text.secondary">
        Typed booking rules used by HTTP appointments and voice tools. Prefer catalog durations when
        services are modeled in Services & Products.
      </Typography>
      {policyError ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {policyError}
        </Alert>
      ) : null}
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
      <Typography variant="subtitle2">Named service durations</Typography>
      {Object.entries(policy.service_durations_minutes).map(([name, minutes]) => (
        <Stack key={name} direction="row" spacing={1}>
          <TextField
            label="Service"
            value={name}
            fullWidth
            onChange={(e) =>
              setPolicy((p) => {
                const next = { ...p.service_durations_minutes }
                delete next[name]
                next[e.target.value] = minutes
                return { ...p, service_durations_minutes: next }
              })
            }
          />
          <TextField
            label="Minutes"
            type="number"
            value={minutes}
            sx={{ width: 130 }}
            slotProps={{ htmlInput: { min: 5, max: 480 } }}
            onChange={(e) =>
              setPolicy((p) => ({
                ...p,
                service_durations_minutes: {
                  ...p.service_durations_minutes,
                  [name]: Number(e.target.value) || 0,
                },
              }))
            }
          />
          <IconButton
            aria-label={`Remove ${name}`}
            onClick={() =>
              setPolicy((p) => {
                const next = { ...p.service_durations_minutes }
                delete next[name]
                return { ...p, service_durations_minutes: next }
              })
            }
          >
            ×
          </IconButton>
        </Stack>
      ))}
      <Button
        sx={{ alignSelf: 'flex-start' }}
        onClick={() =>
          setPolicy((p) => ({
            ...p,
            service_durations_minutes: { ...p.service_durations_minutes, 'New service': 30 },
          }))
        }
      >
        Add service
      </Button>
      <Typography variant="subtitle2">Business hours</Typography>
      {DAYS.map((day) => {
        const window = policy.business_hours[day]?.[0]
        return (
          <Stack key={day} direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <Button
              variant={window ? 'text' : 'outlined'}
              sx={{ width: 110, textTransform: 'capitalize' }}
              onClick={() =>
                !window &&
                setPolicy((p) => ({
                  ...p,
                  business_hours: {
                    ...p.business_hours,
                    [day]: [{ start: '09:00', end: '17:00' }],
                  },
                }))
              }
            >
              {day}
            </Button>
            {window ? (
              <>
                <TextField
                  label="Start"
                  type="time"
                  value={window.start}
                  onChange={(e) =>
                    setPolicy((p) => ({
                      ...p,
                      business_hours: {
                        ...p.business_hours,
                        [day]: [{ ...window, start: e.target.value }],
                      },
                    }))
                  }
                />
                <TextField
                  label="End"
                  type="time"
                  value={window.end}
                  onChange={(e) =>
                    setPolicy((p) => ({
                      ...p,
                      business_hours: {
                        ...p.business_hours,
                        [day]: [{ ...window, end: e.target.value }],
                      },
                    }))
                  }
                />
                <IconButton
                  aria-label={`Remove ${day} hours`}
                  onClick={() =>
                    setPolicy((p) => {
                      const next = { ...p.business_hours }
                      delete next[day]
                      return { ...p, business_hours: next }
                    })
                  }
                >
                  ×
                </IconButton>
              </>
            ) : null}
          </Stack>
        )
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
              notify(err instanceof ApiError ? err.message : 'Failed to save policy', 'error')
            })
            .finally(() => setSaving(false))
        }}
      >
        Save booking policy
      </Button>
    </Stack>
  )
}
