import LoginIcon from '@mui/icons-material/Login'
import PersonAddIcon from '@mui/icons-material/PersonAdd'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { alpha } from '@mui/material/styles'
import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/AuthProvider'
import { useSnackbar } from '../SnackbarProvider'
import { designTokens } from '../../theme/tokens'
import { safeNextPath } from '../../utils/safeNextPath'

export type AuthMode = 'signIn' | 'signUp'

type HomeAuthCardProps = {
  initialMode?: AuthMode
  nextPath?: string
}

function ToggleButton({
  active,
  title,
  icon,
  onClick,
}: {
  active: boolean
  title: string
  icon: ReactNode
  onClick: () => void
}) {
  return (
    <Tooltip title={title}>
      <span>
        <IconButton
          type="button"
          aria-pressed={active}
          aria-label={title}
          onClick={onClick}
          color={active ? 'primary' : 'default'}
          sx={{ minHeight: 44, minWidth: 44, borderRadius: 1, width: '100%' }}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  )
}

function SignInForm({ nextPath }: { nextPath: string }) {
  const { login } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const validate = useCallback(() => {
    const next: { email?: string; password?: string } = {}
    if (!email.trim() || !/\S+@\S+\.\S+/.test(email)) {
      next.email = 'Please enter a valid email address.'
    }
    if (!password) {
      next.password = 'Password is required.'
    }
    setFieldErrors(next)
    return Object.keys(next).length === 0
  }, [email, password])

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setFormError(null)
    try {
      await login(email.trim(), password)
      notify('Signed in', 'success')
      navigate(nextPath, { replace: true })
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Sign in failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack component="form" onSubmit={onSubmit} noValidate spacing={2}>
      {formError ? <Alert severity="error">{formError}</Alert> : null}
      <TextField
        id="home-signin-email"
        label="Email"
        type="email"
        name="email"
        autoComplete="email"
        required
        fullWidth
        value={email}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          setEmail(e.target.value)
          setFormError(null)
          setFieldErrors((c) => ({ ...c, email: undefined }))
        }}
        error={Boolean(fieldErrors.email)}
        helperText={fieldErrors.email}
      />
      <TextField
        id="home-signin-password"
        label="Password"
        type="password"
        name="password"
        autoComplete="current-password"
        required
        fullWidth
        value={password}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          setPassword(e.target.value)
          setFormError(null)
          setFieldErrors((c) => ({ ...c, password: undefined }))
        }}
        error={Boolean(fieldErrors.password)}
        helperText={fieldErrors.password}
      />
      <Box sx={{ textAlign: 'right' }}>
        <Link component={RouterLink} to="/forgot-password" variant="body2">
          Forgot your password?
        </Link>
      </Box>
      <Button
        type="submit"
        variant="contained"
        loading={submitting}
        startIcon={<LoginIcon />}
        fullWidth
        sx={{ minHeight: 44 }}
      >
        Sign in
      </Button>
    </Stack>
  )
}

function SignUpForm() {
  const { register } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{
    username?: string
    email?: string
    password?: string
  }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const validate = useCallback(() => {
    const next: { username?: string; email?: string; password?: string } = {}
    if (username.trim().length < 2) {
      next.username = 'Username must be at least 2 characters.'
    }
    if (!email.trim() || !/\S+@\S+\.\S+/.test(email)) {
      next.email = 'Please enter a valid email address.'
    }
    if (!password || password.length < 8) {
      next.password = 'Password must be at least 8 characters.'
    }
    setFieldErrors(next)
    return Object.keys(next).length === 0
  }, [email, password, username])

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setFormError(null)
    try {
      await register(username.trim(), email.trim(), password)
      notify('Account created', 'success')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Sign up failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Stack component="form" onSubmit={onSubmit} noValidate spacing={2}>
      {formError ? <Alert severity="error">{formError}</Alert> : null}
      <TextField
        id="home-signup-username"
        label="Username"
        name="username"
        autoComplete="username"
        required
        fullWidth
        value={username}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          setUsername(e.target.value)
          setFormError(null)
          setFieldErrors((c) => ({ ...c, username: undefined }))
        }}
        error={Boolean(fieldErrors.username)}
        helperText={fieldErrors.username}
      />
      <TextField
        id="home-signup-email"
        label="Email"
        type="email"
        name="email"
        autoComplete="email"
        required
        fullWidth
        value={email}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          setEmail(e.target.value)
          setFormError(null)
          setFieldErrors((c) => ({ ...c, email: undefined }))
        }}
        error={Boolean(fieldErrors.email)}
        helperText={fieldErrors.email}
      />
      <TextField
        id="home-signup-password"
        label="Password"
        type="password"
        name="password"
        autoComplete="new-password"
        required
        fullWidth
        value={password}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          setPassword(e.target.value)
          setFormError(null)
          setFieldErrors((c) => ({ ...c, password: undefined }))
        }}
        error={Boolean(fieldErrors.password)}
        helperText={fieldErrors.password ?? 'At least 8 characters'}
      />
      <Button
        type="submit"
        variant="contained"
        loading={submitting}
        startIcon={<PersonAddIcon />}
        fullWidth
        sx={{ minHeight: 44 }}
      >
        Create account
      </Button>
    </Stack>
  )
}

function AuthFace({
  active,
  flipped,
  children,
}: {
  active: boolean
  flipped?: boolean
  children: ReactNode
}) {
  return (
    <Box
      aria-hidden={!active}
      sx={{
        position: flipped ? 'absolute' : 'relative',
        inset: flipped ? 0 : 'auto',
        backfaceVisibility: 'hidden',
        transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
        visibility: active ? 'visible' : 'hidden',
        pointerEvents: active ? 'auto' : 'none',
      }}
    >
      {children}
    </Box>
  )
}

export function HomeAuthCard({ initialMode = 'signIn', nextPath = '/dashboard' }: HomeAuthCardProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode)

  useEffect(() => {
    setMode(initialMode)
  }, [initialMode])

  const isSignIn = mode === 'signIn'

  return (
    <Paper
      variant="outlined"
      sx={{
        width: '100%',
        p: { xs: 2.25, sm: 3.75 },
        borderRadius: `${designTokens.radius.card}px`,
        overflow: 'hidden',
        backgroundColor: 'background.paper',
      }}
    >
      <Stack spacing={3}>
        <Stack spacing={1}>
          <Typography variant="overline" color="text.secondary">
            Account
          </Typography>
          <Typography component="h2" variant="h5">
            {isSignIn ? 'Sign in' : 'Create an account'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isSignIn
              ? 'Use your email to manage calls, calendar, and analytics.'
              : 'Set up Voice2Appointment for voice scheduling.'}
          </Typography>
        </Stack>

        <Box
          sx={(theme) => ({
            p: 0.5,
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: 0.75,
            borderRadius: 1,
            backgroundColor: alpha(theme.palette.text.primary, 0.04),
          })}
        >
          <ToggleButton
            active={isSignIn}
            title="Sign in"
            icon={<LoginIcon fontSize="small" />}
            onClick={() => setMode('signIn')}
          />
          <ToggleButton
            active={!isSignIn}
            title="Sign up"
            icon={<PersonAddIcon fontSize="small" />}
            onClick={() => setMode('signUp')}
          />
        </Box>

        <Box sx={{ perspective: 1400 }}>
          <Box
            sx={{
              position: 'relative',
              minHeight: { xs: isSignIn ? 280 : 360, sm: isSignIn ? 260 : 340 },
              transformStyle: 'preserve-3d',
              transform: isSignIn ? 'rotateY(0deg)' : 'rotateY(180deg)',
              transition: `transform ${designTokens.motion.duration} ${designTokens.motion.easing}, min-height 240ms ease`,
              '@media (prefers-reduced-motion: reduce)': {
                transition: 'none',
              },
            }}
          >
            <AuthFace active={isSignIn}>
              <SignInForm nextPath={safeNextPath(nextPath)} />
            </AuthFace>
            <AuthFace active={!isSignIn} flipped>
              <SignUpForm />
            </AuthFace>
          </Box>
        </Box>
      </Stack>
    </Paper>
  )
}
