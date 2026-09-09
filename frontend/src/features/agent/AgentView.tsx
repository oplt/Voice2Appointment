import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import {
  createKnowledge,
  getIndustryProfile,
  listKnowledge,
  patchKnowledge,
  putIndustryProfile,
  type IndustryType,
  type KnowledgeEntry,
} from '../../api/knowledge'
import { queryKeys } from '../../api/queryKeys'
import { getMe } from '../../api/users'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import { ProductPrefsPanels } from '../settings/ProductPrefsPanels'

const INDUSTRY_TYPES: IndustryType[] = ['clinic', 'restaurant', 'salon', 'general']

const KNOWN_TOOLS = [
  'search_catalog',
  'catalog_search',
  'get_price',
  'book_appointment',
  'create_appointment',
  'create_reservation',
  'appointment_availability',
  'restaurant_availability',
  'reschedule_appointment',
  'cancel_appointment',
  'cancel_reservation',
  'request_human_handoff',
  'answer_faq',
  'provide_product_information',
  'take_message',
  'check_order_status',
  'send_secure_link',
  'create_quote_request',
  'join_waitlist',
  'find_visit_types',
  'find_practitioners',
] as const

const INSTRUCTIONS_TITLE = 'instructions'

type KnowledgeDraft = {
  title: string
  content: string
  active: boolean
}

export function AgentView() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState(0)
  const [deepgramOk, setDeepgramOk] = useState<boolean | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)

  const [knowledgeOpen, setKnowledgeOpen] = useState(false)
  const [editingKnowledge, setEditingKnowledge] = useState<KnowledgeEntry | null>(null)
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeDraft>({
    title: '',
    content: '',
    active: true,
  })

  const [industryType, setIndustryType] = useState<IndustryType>('general')
  const [instructionsText, setInstructionsText] = useState('')

  useEffect(() => {
    getMe()
      .then((me) => setDeepgramOk(Boolean(me.has_deepgram)))
      .catch((err: unknown) => {
        setVoiceError(err instanceof ApiError ? err.message : 'Failed to load voice status')
      })
  }, [])

  const knowledgeQuery = useQuery({
    queryKey: queryKeys.knowledge.list,
    queryFn: listKnowledge,
    enabled: tab === 4 || tab === 3,
  })

  const profileQuery = useQuery({
    queryKey: queryKeys.industryProfile.current,
    queryFn: getIndustryProfile,
    enabled: tab === 5 || tab === 6 || tab === 3,
  })

  useEffect(() => {
    const profile = profileQuery.data
    if (profile?.industry_type && INDUSTRY_TYPES.includes(profile.industry_type as IndustryType)) {
      setIndustryType(profile.industry_type as IndustryType)
    }
  }, [profileQuery.data])

  useEffect(() => {
    const entries = knowledgeQuery.data ?? []
    const instructions = entries.find(
      (e) => e.title.toLowerCase() === INSTRUCTIONS_TITLE,
    )
    if (instructions) {
      setInstructionsText(instructions.content)
      return
    }
    const meta = profileQuery.data?.metadata_json
    if (meta && typeof meta.instructions === 'string') {
      setInstructionsText(meta.instructions)
    }
  }, [knowledgeQuery.data, profileQuery.data])

  const knowledgeSave = useMutation({
    mutationFn: async () => {
      const body = {
        title: knowledgeDraft.title.trim(),
        content: knowledgeDraft.content.trim(),
        active: knowledgeDraft.active,
      }
      if (editingKnowledge) return patchKnowledge(editingKnowledge.id, body)
      return createKnowledge(body)
    },
    onSuccess: () => {
      notify(editingKnowledge ? 'Knowledge updated' : 'Knowledge created', 'success')
      setKnowledgeOpen(false)
      setEditingKnowledge(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const profileSave = useMutation({
    mutationFn: () => putIndustryProfile({ industry_type: industryType }),
    onSuccess: () => {
      notify('Industry profile saved', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.industryProfile.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const instructionsSave = useMutation({
    mutationFn: async () => {
      const entries = knowledgeQuery.data ?? []
      const existing = entries.find((e) => e.title.toLowerCase() === INSTRUCTIONS_TITLE)
      const content = instructionsText.trim() || ' '
      if (existing) {
        return patchKnowledge(existing.id, { content, title: INSTRUCTIONS_TITLE, active: true })
      }
      return createKnowledge({
        title: INSTRUCTIONS_TITLE,
        content,
        active: true,
      })
    },
    onSuccess: () => {
      notify('Instructions saved', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.knowledge.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  const knowledgeEntries = knowledgeQuery.data ?? []
  const enabledTools = (profileQuery.data?.enabled_tools ?? [])
    .map((t) => String(t))
    .filter(Boolean)
  const toolChecklist = Array.from(new Set([...KNOWN_TOOLS, ...enabledTools])).sort()

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
        <Tab label="Industry profile" />
        <Tab label="Capabilities" />
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
        <Stack spacing={2} sx={{ maxWidth: 640 }}>
          <Typography variant="h3">Instructions</Typography>
          <Typography variant="body1" color="text.secondary">
            Saved as a knowledge entry titled &quot;instructions&quot; (fallback to industry
            profile metadata when present).
          </Typography>
          <TextField
            label="Agent instructions"
            value={instructionsText}
            onChange={(e) => setInstructionsText(e.target.value)}
            fullWidth
            multiline
            minRows={8}
          />
          <Button
            variant="contained"
            sx={{ alignSelf: 'flex-start' }}
            disabled={instructionsSave.isPending}
            onClick={() => instructionsSave.mutate()}
          >
            Save instructions
          </Button>
        </Stack>
      ) : null}

      {tab === 4 ? (
        <Stack spacing={2}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
          >
            <Typography variant="body1" color="text.secondary">
              FAQ and policy entries power voice answers.
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => {
                setEditingKnowledge(null)
                setKnowledgeDraft({ title: '', content: '', active: true })
                setKnowledgeOpen(true)
              }}
            >
              New entry
            </Button>
          </Stack>
          {knowledgeQuery.isPending ? (
            <CircularProgress size={28} />
          ) : knowledgeQuery.error ? (
            <Alert severity="error">
              {knowledgeQuery.error instanceof ApiError
                ? knowledgeQuery.error.message
                : 'Failed to load knowledge'}
            </Alert>
          ) : knowledgeEntries.length === 0 ? (
            <Typography color="text.secondary">No knowledge entries yet.</Typography>
          ) : (
            <List disablePadding>
              {knowledgeEntries.map((entry) => (
                <ListItem
                  key={entry.id}
                  divider
                  secondaryAction={
                    <Button
                      size="small"
                      onClick={() => {
                        setEditingKnowledge(entry)
                        setKnowledgeDraft({
                          title: entry.title,
                          content: entry.content,
                          active: entry.active,
                        })
                        setKnowledgeOpen(true)
                      }}
                    >
                      Edit
                    </Button>
                  }
                >
                  <ListItemText
                    primary={entry.title}
                    secondary={entry.active ? entry.content.slice(0, 120) : 'Inactive'}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </Stack>
      ) : null}

      {tab === 5 ? (
        <Stack spacing={2} sx={{ maxWidth: 480 }}>
          <Typography variant="h3">Industry profile</Typography>
          {profileQuery.isPending ? (
            <CircularProgress size={28} />
          ) : profileQuery.error ? (
            <Alert severity="error">
              {profileQuery.error instanceof ApiError
                ? profileQuery.error.message
                : 'Failed to load industry profile'}
            </Alert>
          ) : (
            <>
              {!profileQuery.data ? (
                <Alert severity="info">No profile assigned yet — pick an industry type below.</Alert>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Scheduling mode: {profileQuery.data.scheduling_mode}
                </Typography>
              )}
              <TextField
                select
                label="Industry type"
                value={industryType}
                onChange={(e) => setIndustryType(e.target.value as IndustryType)}
                fullWidth
              >
                {INDUSTRY_TYPES.map((type) => (
                  <MenuItem key={type} value={type}>
                    {type}
                  </MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                sx={{ alignSelf: 'flex-start' }}
                disabled={profileSave.isPending}
                onClick={() => profileSave.mutate()}
              >
                Save industry type
              </Button>
            </>
          )}
        </Stack>
      ) : null}

      {tab === 6 ? (
        <Stack spacing={2} sx={{ maxWidth: 560 }}>
          <Typography variant="h3">Capabilities / Enabled tools</Typography>
          <Typography variant="body1" color="text.secondary">
            Read-only checklist from the industry profile. Changing industry type resets the
            enabled tool set.
          </Typography>
          {profileQuery.isPending ? (
            <CircularProgress size={28} />
          ) : !profileQuery.data ? (
            <Alert severity="info">Assign an industry profile to see enabled tools.</Alert>
          ) : (
            <Stack spacing={0.5}>
              {toolChecklist.map((tool) => {
                const on = enabledTools.includes(tool)
                return (
                  <FormControlLabel
                    key={tool}
                    control={<Checkbox checked={on} disabled />}
                    label={tool.replaceAll('_', ' ')}
                  />
                )
              })}
            </Stack>
          )}
        </Stack>
      ) : null}

      <Dialog
        open={knowledgeOpen}
        onClose={() => !knowledgeSave.isPending && setKnowledgeOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{editingKnowledge ? 'Edit knowledge' : 'New knowledge'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              label="Title"
              value={knowledgeDraft.title}
              onChange={(e) =>
                setKnowledgeDraft({ ...knowledgeDraft, title: e.target.value })
              }
              fullWidth
              required
            />
            <TextField
              label="Content"
              value={knowledgeDraft.content}
              onChange={(e) =>
                setKnowledgeDraft({ ...knowledgeDraft, content: e.target.value })
              }
              fullWidth
              required
              multiline
              minRows={5}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={knowledgeDraft.active}
                  onChange={(e) =>
                    setKnowledgeDraft({ ...knowledgeDraft, active: e.target.checked })
                  }
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setKnowledgeOpen(false)} disabled={knowledgeSave.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              !knowledgeDraft.title.trim() ||
              !knowledgeDraft.content.trim() ||
              knowledgeSave.isPending
            }
            onClick={() => knowledgeSave.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
