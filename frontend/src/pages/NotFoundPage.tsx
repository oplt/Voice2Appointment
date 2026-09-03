import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import { Link as RouterLink } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <Box
      sx={{
        minHeight: '60vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        textAlign: 'center',
        px: 2,
      }}
    >
      <Typography variant="h1">404</Typography>
      <Typography variant="body1">Page not found.</Typography>
      <Button component={RouterLink} to="/dashboard" variant="contained">
        Back to dashboard
      </Button>
    </Box>
  )
}
