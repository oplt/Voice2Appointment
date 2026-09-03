import PersonAddAltOutlinedIcon from '@mui/icons-material/PersonAddAltOutlined'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type FormEvent } from 'react'
import { Link as RouterLink, Navigate, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { useSnackbar } from '../components/SnackbarProvider'

export function RegisterPage() {
  const { isAuthenticated, register } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
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
    if (!username.trim() || !email.trim() || !password) {
      setError('Username, email, and password are required')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      await register(username.trim(), email.trim(), password)
      notify('Account created', 'success')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Registration failed')
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
          <Typography variant="body1">Create an account to manage voice scheduling.</Typography>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}

        <TextField
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          fullWidth
        />
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
          autoComplete="new-password"
          required
          fullWidth
          helperText="At least 8 characters"
        />

        <Button
          type="submit"
          variant="contained"
          loading={loading}
          startIcon={<PersonAddAltOutlinedIcon />}
        >
          Register
        </Button>

        <Typography variant="body2" sx={{ textAlign: 'center' }}>
          Already have an account?{' '}
          <Button component={RouterLink} to="/login" variant="text" size="small">
            Login
          </Button>
        </Typography>
      </Stack>
    </Box>
  )
}
