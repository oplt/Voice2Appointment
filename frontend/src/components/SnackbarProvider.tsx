import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import Alert from '@mui/material/Alert'
import Snackbar from '@mui/material/Snackbar'

type Severity = 'success' | 'info' | 'warning' | 'error'

type SnackbarContextValue = {
  notify: (message: string, severity?: Severity) => void
}

const SnackbarContext = createContext<SnackbarContextValue | null>(null)

type SnackbarProviderProps = {
  children: ReactNode
}

export function SnackbarProvider({ children }: SnackbarProviderProps) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [severity, setSeverity] = useState<Severity>('info')

  const notify = useCallback((nextMessage: string, nextSeverity: Severity = 'info') => {
    setMessage(nextMessage)
    setSeverity(nextSeverity)
    setOpen(true)
  }, [])

  const value = useMemo(() => ({ notify }), [notify])

  return (
    <SnackbarContext.Provider value={value}>
      {children}
      <Snackbar
        open={open}
        autoHideDuration={4000}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={severity} variant="filled" onClose={() => setOpen(false)}>
          {message}
        </Alert>
      </Snackbar>
    </SnackbarContext.Provider>
  )
}

export function useSnackbar(): SnackbarContextValue {
  const ctx = useContext(SnackbarContext)
  if (!ctx) {
    throw new Error('useSnackbar must be used within SnackbarProvider')
  }
  return ctx
}
