import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'

export function HomePage() {
  const { isAuthenticated } = useAuth()

  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: 2,
      }}
    >
      <Stack spacing={3} sx={{ maxWidth: 520, textAlign: 'center', alignItems: 'center' }}>
        <Typography variant="h1">Voice2Appointment</Typography>
        <Typography variant="body1">
          Voice scheduling, calendar sync, and call analytics — Tesla-minimal interface.
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Button
            component={RouterLink}
            to={isAuthenticated ? '/dashboard' : '/login'}
            variant="contained"
          >
            {isAuthenticated ? 'Open dashboard' : 'Login'}
          </Button>
          <Button component={RouterLink} to="/calendar" variant="outlined">
            Calendar
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}
