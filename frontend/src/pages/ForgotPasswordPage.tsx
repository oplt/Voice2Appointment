import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type FormEvent } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { requestPasswordReset } from '../api/auth'
import { ApiError } from '../api/client'
import { useSnackbar } from '../components/SnackbarProvider'

const RESET_REQUEST_CONFIRMATION = 'If an account exists for this email, reset instructions have been sent.'

export function ForgotPasswordPage() {
  const { notify } = useSnackbar()
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setMessage(null)
    if (!email.trim()) {
      setError('Email is required')
      return
    }
    setLoading(true)
    try {
      await requestPasswordReset(email.trim())
      setMessage(RESET_REQUEST_CONFIRMATION)
      notify('If an account exists, reset instructions were sent', 'info')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: 2,
      }}
    >
      <Stack
        component="form"
        onSubmit={onSubmit}
        spacing={2.5}
        sx={{ width: '100%', maxWidth: 400 }}
      >
        <Stack spacing={1}>
          <Typography variant="h1" sx={{ fontSize: '2rem' }}>
            Reset password
          </Typography>
          <Typography variant="body1">
            Enter your account email. We always show the same confirmation message.
          </Typography>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}
        {message ? <Alert severity="success">{message}</Alert> : null}

        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          fullWidth
          required
        />
        <Button type="submit" variant="contained" loading={loading} fullWidth>
          Send reset link
        </Button>
        <Button component={RouterLink} to="/?mode=signIn" variant="text">
          Back to sign in
        </Button>
      </Stack>
    </Box>
  )
}
