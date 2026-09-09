import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './app/App'
import { AppProviders } from './app/providers'
import { AuthProvider } from './auth/AuthProvider'
import { SnackbarProvider } from './components/SnackbarProvider'
import theme from './theme/theme'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme} defaultMode="light" modeStorageKey="v2a-color-mode">
      <CssBaseline />
      <BrowserRouter>
        <AppProviders>
          <AuthProvider>
            <SnackbarProvider>
              <App />
            </SnackbarProvider>
          </AuthProvider>
        </AppProviders>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
