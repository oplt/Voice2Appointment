import Alert from '@mui/material/Alert'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getMe } from '../../api/users'

export function VoicePanel() {
  const [deepgramOk, setDeepgramOk] = useState<boolean | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)

  useEffect(() => {
    getMe()
      .then((me) => setDeepgramOk(Boolean(me.has_deepgram)))
      .catch((err: unknown) => {
        setVoiceError(err instanceof ApiError ? err.message : 'Failed to load voice status')
      })
  }, [])

  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      <Typography variant="body2" color="text.secondary">
        Speech is powered by a platform-managed Deepgram credential (
        <code>DEEPGRAM_API_KEY</code>). Per-account keys are not collected.
      </Typography>
      {voiceError ? <Alert severity="error">{voiceError}</Alert> : null}
      {deepgramOk == null && !voiceError ? (
        <Typography color="text.secondary">Checking…</Typography>
      ) : null}
      {deepgramOk != null ? (
        <Alert severity={deepgramOk ? 'success' : 'warning'}>
          {deepgramOk
            ? 'Deepgram is configured on the server.'
            : 'Deepgram is not configured. Ask an administrator to set DEEPGRAM_API_KEY.'}
        </Alert>
      ) : null}
    </Stack>
  )
}
