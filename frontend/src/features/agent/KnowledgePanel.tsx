import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import {
  createKnowledge,
  listKnowledge,
  patchKnowledge,
  type KnowledgeEntry,
} from '../../api/knowledge'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

type KnowledgeDraft = {
  title: string
  content: string
  active: boolean
}

export function KnowledgePanel() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [knowledgeOpen, setKnowledgeOpen] = useState(false)
  const [editingKnowledge, setEditingKnowledge] = useState<KnowledgeEntry | null>(null)
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeDraft>({
    title: '',
    content: '',
    active: true,
  })

  const knowledgeQuery = useQuery({
    queryKey: queryKeys.knowledge.list,
    queryFn: listKnowledge,
  })

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

  const knowledgeEntries = knowledgeQuery.data ?? []

  return (
    <>
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
    </>
  )
}
