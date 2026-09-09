import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
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
} from '../../api/knowledge'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

const INSTRUCTIONS_TITLE = 'instructions'

export function InstructionsPanel() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [instructionsText, setInstructionsText] = useState('')

  const knowledgeQuery = useQuery({
    queryKey: queryKeys.knowledge.list,
    queryFn: listKnowledge,
  })

  const profileQuery = useQuery({
    queryKey: queryKeys.industryProfile.current,
    queryFn: getIndustryProfile,
  })

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

  const instructionsSave = useMutation({
    mutationFn: async () => {
      const entries = knowledgeQuery.data ?? []
      const existing = entries.find((e) => e.title.toLowerCase() === INSTRUCTIONS_TITLE)
      const content = instructionsText.trim() || ' '
      if (existing) {
        return patchKnowledge(existing.id, {
          content,
          title: INSTRUCTIONS_TITLE,
          active: true,
        })
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

  return (
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
  )
}
