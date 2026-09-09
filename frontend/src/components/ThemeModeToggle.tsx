import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined'
import IconButton from '@mui/material/IconButton'
import Tooltip from '@mui/material/Tooltip'
import { useColorScheme } from '@mui/material/styles'

/** Light/dark toggle for the app shell. Defaults to light via ThemeProvider. */
export function ThemeModeToggle() {
  const { mode, setMode, systemMode } = useColorScheme()
  if (!mode) {
    return null
  }
  const resolved = mode === 'system' ? systemMode : mode
  const isDark = resolved === 'dark'

  return (
    <Tooltip title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}>
      <IconButton
        color="inherit"
        onClick={() => setMode(isDark ? 'light' : 'dark')}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        size="small"
      >
        {isDark ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
      </IconButton>
    </Tooltip>
  )
}
