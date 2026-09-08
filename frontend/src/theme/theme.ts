import { createTheme } from '@mui/material/styles'

import { componentOverrides } from './components'
import {
  darkPaletteOptions,
  designTokens,
  paletteOptions,
  typographyOptions,
} from './tokens'

export { designTokens, semanticDark, semanticLight, semanticCssVariables } from './tokens'

const noneShadows = [
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
] as const

const theme = createTheme({
  cssVariables: {
    colorSchemeSelector: 'data-mui-color-scheme',
  },
  defaultColorScheme: 'light',
  colorSchemes: {
    light: { palette: paletteOptions },
    dark: { palette: darkPaletteOptions },
  },
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  shadows: noneShadows as any,
  components: componentOverrides,
})

export default theme
