import LoginIcon from '@mui/icons-material/Login'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type FormEvent } from 'react'
import { Link as RouterLink, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { useSnackbar } from '../components/SnackbarProvider'
import { safeNextPath } from '../utils/safeNextPath'

export function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const location = useLocation()
  const from = safeNextPath((location.state as { from?: string } | null)?.from)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!email.trim() || !password) {
      setError('Email and password are required')
      return
    }
    setLoading(true)
    try {
      await login(email.trim(), password)
      notify('Signed in', 'success')
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed')
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
            Voice2Appointment
          </Typography>
          <Typography variant="body1">Sign in to manage calls, calendar, and analytics.</Typography>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
          fullWidth
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          fullWidth
        />

        <Button type="submit" variant="contained" loading={loading} startIcon={<LoginIcon />}>
          Login
        </Button>

        <Typography variant="body2" sx={{ textAlign: 'center' }}>
          No account?{' '}
          <Button component={RouterLink} to="/register" variant="text" size="small">
            Register
          </Button>
          {' · '}
          <Button component={RouterLink} to="/" variant="text" size="small">
            Home
          </Button>
        </Typography>
      </Stack>
    </Box>
  )
}
