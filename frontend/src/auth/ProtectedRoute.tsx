import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './AuthProvider'

export function ProtectedRoute() {
  const { isAuthenticated, isReady, authError, retryBootstrap } = useAuth()
  const location = useLocation()

  if (!isReady) {
    return (
      <Box
        role="status"
        aria-live="polite"
        aria-busy="true"
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <CircularProgress aria-label="Checking sign-in" />
        <Typography variant="body2" color="text.secondary">
          Checking sign-in…
        </Typography>
      </Box>
    )
  }

  if (authError && !isAuthenticated) {
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
        <Stack spacing={2} sx={{ maxWidth: 420, width: '100%' }}>
          <Typography variant="h2" component="h1">
            Sign-in check failed
          </Typography>
          <Alert severity="error">{authError}</Alert>
          <Stack direction="row" spacing={1}>
            <Button variant="contained" onClick={retryBootstrap}>
              Retry
            </Button>
            <Button variant="outlined" href="/?mode=signIn">
              Go to sign in
            </Button>
          </Stack>
        </Stack>
      </Box>
    )
  }

  if (!isAuthenticated) {
    return (
      <Navigate
        to="/?mode=signIn"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  return <Outlet />
}
