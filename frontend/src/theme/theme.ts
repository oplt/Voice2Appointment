import { createTheme } from '@mui/material/styles'

import { componentOverrides } from './components'
import { designTokens, paletteOptions, typographyOptions } from './tokens'

export { designTokens }

const theme = createTheme({
  palette: paletteOptions,
  typography: typographyOptions,
  shape: {
    borderRadius: designTokens.radius.button,
  },
  spacing: 8,
  breakpoints: {
    values: {
      xs: 0,
      sm: 768,
      md: 1024,
      lg: 1440,
      xl: 1920,
    },
  },
  transitions: {
    duration: {
      shortest: 150,
      shorter: 200,
      short: 250,
      standard: 330,
      complex: 375,
      enteringScreen: 225,
      leavingScreen: 195,
    },
    easing: {
      easeInOut: 'cubic-bezier(0.5, 0, 0, 0.75)',
      easeOut: 'cubic-bezier(0.5, 0, 0, 0.75)',
      easeIn: 'cubic-bezier(0.5, 0, 0, 0.75)',
      sharp: 'cubic-bezier(0.5, 0, 0, 0.75)',
    },
  },
  shadows: [
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
    'none',
  ],
  components: componentOverrides,
})

export default theme
