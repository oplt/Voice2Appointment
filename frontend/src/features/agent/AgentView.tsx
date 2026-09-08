import Alert from '@mui/material/Alert'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import { getMe } from '../../api/users'
import { PageHeader } from '../../components/PageHeader'
import { ProductPrefsPanels } from '../settings/ProductPrefsPanels'

export function AgentView() {
  const [tab, setTab] = useState(0)
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
    <Stack spacing={3}>
      <PageHeader
        title="Agent"
        subtitle="Voice, languages, handoff, instructions, and knowledge."
      />
      <Tabs
        value={tab}
        onChange={(_, value: number) => setTab(value)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Agent sections"
      >
        <Tab label="Voice" />
        <Tab label="Languages" />
        <Tab label="Handoff" />
        <Tab label="Instructions" />
        <Tab label="Knowledge" />
      </Tabs>

      {tab === 0 ? (
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
      ) : null}

      {tab === 1 ? (
        <ProductPrefsPanels sections={['languages']} saveLabel="Save language settings" />
      ) : null}

      {tab === 2 ? (
        <ProductPrefsPanels sections={['handoff']} saveLabel="Save handoff settings" />
      ) : null}

      {tab === 3 ? (
        <Stack spacing={2} sx={{ maxWidth: 560 }}>
          <Typography variant="h3">Instructions</Typography>
          <Typography variant="body1" color="text.secondary">
            System prompt and industry profile instructions are composed server-side from
            entitlements.
          </Typography>
          <Alert severity="info">
            Editable instruction drafts land with the knowledge editor. Use Industry profile
            assignment on the backend for now.
          </Alert>
        </Stack>
      ) : null}

      {tab === 4 ? (
        <Stack spacing={2} sx={{ maxWidth: 560 }}>
          <Typography variant="h3">Knowledge</Typography>
          <Typography variant="body1" color="text.secondary">
            FAQ and policy entries power voice answers for general and industry profiles.
          </Typography>
          <Alert severity="info">
            Knowledge CRUD UI arrives after catalog APIs expose org-scoped entries.
          </Alert>
        </Stack>
      ) : null}
    </Stack>
  )
}
