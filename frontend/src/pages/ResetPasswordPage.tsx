import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom'

import { confirmPasswordReset } from '../api/auth'
import { ApiError } from '../api/client'
import { useSnackbar } from '../components/SnackbarProvider'

export function ResetPasswordPage() {
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tokenFromUrl = params.get('token') || ''

  const [token, setToken] = useState(tokenFromUrl)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Capture token once, then scrub it from the URL/history.
  useEffect(() => {
    if (!tokenFromUrl) return
    setToken(tokenFromUrl)
    const next = new URLSearchParams(params)
    next.delete('token')
    setParams(next, { replace: true })
    // Also drop from history when possible.
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('token')
      window.history.replaceState({}, '', url.pathname + url.search)
    } catch {
      // ignore
    }
  }, [tokenFromUrl, params, setParams])

  const canSubmit = useMemo(
    () => Boolean(token && password.length >= 8 && password === confirm),
    [token, password, confirm],
  )

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!token) {
      setError('Reset link is missing or expired. Request a new one.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      await confirmPasswordReset(token, password)
      notify('Password updated. You can sign in.', 'success')
      navigate('/', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Invalid or expired reset link. Request a new one.',
      )
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
            Choose a new password
          </Typography>
          <Typography variant="body1">Use at least 8 characters.</Typography>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}
        {!token ? (
          <Alert severity="warning">
            No reset token found.{' '}
            <Button component={RouterLink} to="/forgot-password" size="small">
              Request a new link
            </Button>
          </Alert>
        ) : null}

        <TextField
          label="New password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          fullWidth
          required
        />
        <TextField
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          fullWidth
          required
        />
        <Button type="submit" variant="contained" loading={loading} disabled={!canSubmit} fullWidth>
          Update password
        </Button>
        <Button component={RouterLink} to="/?mode=signIn" variant="text">
          Back to sign in
        </Button>
      </Stack>
    </Box>
  )
}
