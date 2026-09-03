import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Component, createRef, type ErrorInfo, type ReactNode, type RefObject } from 'react'
import { Link as RouterLink } from 'react-router-dom'

type Props = { children: ReactNode }
type State = { error: Error | null }

export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null }
  private headingRef: RefObject<HTMLHeadingElement | null> = createRef()

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Route error', error, info.componentStack)
  }

  componentDidUpdate(_: Props, prevState: State) {
    if (this.state.error && !prevState.error) {
      this.headingRef.current?.focus()
    }
  }

  render() {
    if (this.state.error) {
      return (
        <Box
          role="alert"
          sx={{
            minHeight: '50vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            px: 2,
          }}
        >
          <Stack spacing={2} sx={{ maxWidth: 480, width: '100%' }}>
            <Typography
              ref={this.headingRef}
              variant="h2"
              component="h1"
              tabIndex={-1}
              sx={{ outline: 'none' }}
            >
              Something went wrong
            </Typography>
            <Alert severity="error">This page failed to render. You can retry or go home.</Alert>
            <Stack direction="row" spacing={1}>
              <Button variant="contained" onClick={() => this.setState({ error: null })}>
                Retry
              </Button>
              <Button component={RouterLink} to="/dashboard" variant="outlined">
                Dashboard
              </Button>
            </Stack>
          </Stack>
        </Box>
      )
    }
    return this.props.children
  }
}

export function RouteLoadingFallback() {
  return (
    <Box
      role="status"
      aria-live="polite"
      aria-busy="true"
      sx={{
        minHeight: '40vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <CircularProgress aria-label="Loading page" />
      <Typography variant="body2" color="text.secondary">
        Loading…
      </Typography>
    </Box>
  )
}
