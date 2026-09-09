import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import { acceptInvitation } from '../../../api/tenancy'
import { useAuth } from '../../../auth/AuthProvider'
import { useSnackbar } from '../../../components/SnackbarProvider'

type AcceptInvitationPanelProps = {
  initialToken?: string
  /** When true, navigate home after success (dedicated invite page). */
  redirectOnSuccess?: boolean
}

export function AcceptInvitationPanel({
  initialToken = '',
  redirectOnSuccess = false,
}: AcceptInvitationPanelProps) {
  const { notify } = useSnackbar()
  const { retryBootstrap } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [token, setToken] = useState(initialToken)

  const acceptMutation = useMutation({
    mutationFn: () => acceptInvitation(token.trim()),
    onSuccess: () => {
      notify('Invitation accepted', 'success')
      setToken('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenancy.all })
      retryBootstrap()
      if (redirectOnSuccess) {
        navigate('/settings', { replace: true })
      }
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Could not accept invitation', 'error')
    },
  })

  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      <Typography variant="h3">Accept invitation</Typography>
      <Typography variant="body2" color="text.secondary">
        Paste the invitation token you received. The email must match your signed-in account.
      </Typography>
      <TextField
        label="Invitation token"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        fullWidth
        multiline
        minRows={2}
      />
      {acceptMutation.isError ? (
        <Alert severity="error">
          {acceptMutation.error instanceof ApiError
            ? acceptMutation.error.message
            : 'Accept failed'}
        </Alert>
      ) : null}
      <Button
        variant="contained"
        sx={{ alignSelf: 'flex-start' }}
        disabled={!token.trim() || acceptMutation.isPending}
        onClick={() => acceptMutation.mutate()}
      >
        Accept invitation
      </Button>
    </Stack>
  )
}
