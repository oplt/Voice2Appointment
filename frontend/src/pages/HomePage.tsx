import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Grid from '@mui/material/Grid'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink, useLocation, useSearchParams } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'
import { HomeAuthCard, type AuthMode } from '../components/auth/HomeAuthCard'
import { designTokens } from '../theme/tokens'
import { safeNextPath } from '../utils/safeNextPath'

function resolveMode(raw: string | null, stateMode?: string): AuthMode {
  if (raw === 'signUp' || stateMode === 'signUp') return 'signUp'
  return 'signIn'
}

export function HomePage() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  const [params] = useSearchParams()
  const fromState = location.state as { from?: string; authMode?: string } | null
  const initialMode = resolveMode(params.get('mode'), fromState?.authMode)
  const nextPath = safeNextPath(fromState?.from)

  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh',
        px: { xs: 2, md: 4 },
        py: { xs: 3, md: 5 },
        backgroundColor: 'background.default',
      }}
    >
      <Grid
        container
        spacing={{ xs: 3, md: 4 }}
        sx={{ maxWidth: designTokens.layout.maxWidth, mx: 'auto', alignItems: 'stretch' }}
      >
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper
            variant="outlined"
            sx={{
              height: '100%',
              px: { xs: 3, md: 5 },
              py: { xs: 3.5, md: 5 },
              borderRadius: `${designTokens.radius.card}px`,
            }}
          >
            <Stack spacing={3}>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                <Chip label="Voice receptionist" color="primary" />
                <Chip label="Calendar-aware" variant="outlined" />
              </Stack>
              <Typography variant="h1" sx={{ maxWidth: 640 }}>
                Voice2Appointment
              </Typography>
              <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 560 }}>
                Answer inbound calls, book and reschedule appointments, and review analytics
                from one Tesla-minimal workspace.
              </Typography>
              {isAuthenticated ? (
                <Button
                  component={RouterLink}
                  to="/dashboard"
                  variant="contained"
                  sx={{ alignSelf: 'flex-start', minHeight: 44 }}
                >
                  Open dashboard
                </Button>
              ) : null}
            </Stack>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          {isAuthenticated ? (
            <Paper
              variant="outlined"
              sx={{
                height: '100%',
                p: 4,
                display: 'flex',
                alignItems: 'center',
                borderRadius: `${designTokens.radius.card}px`,
              }}
            >
              <Typography color="text.secondary">You are already signed in.</Typography>
            </Paper>
          ) : (
            <HomeAuthCard initialMode={initialMode} nextPath={nextPath} />
          )}
        </Grid>
      </Grid>
    </Box>
  )
}
