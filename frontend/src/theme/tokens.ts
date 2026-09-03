import type { ThemeOptions } from '@mui/material/styles'

/**
 * Tesla-inspired tokens from DESIGN.md.
 * Universal Sans is proprietary — use the documented system fallbacks.
 */
export const designTokens = {
  colors: {
    electricBlue: '#3E6AE1',
    pureWhite: '#FFFFFF',
    lightAsh: '#F4F4F4',
    carbonDark: '#171A20',
    graphite: '#393C41',
    pewter: '#5C5E62',
    silverFog: '#8E8E8E',
    cloudGray: '#EEEEEE',
    paleSilver: '#D0D1D2',
    frostedGlass: 'rgba(255, 255, 255, 0.75)',
    overlay: 'rgba(128, 128, 128, 0.65)',
  },
  radius: {
    none: 0,
    button: 4,
    card: 12,
  },
  motion: {
    duration: '0.33s',
    easing: 'cubic-bezier(0.5, 0, 0, 0.75)',
  },
  layout: {
    maxWidth: 1383,
    ctaWidth: 200,
    ctaMinHeight: 40,
  },
  fontFamily: {
    display: '"Universal Sans Display", -apple-system, Arial, sans-serif',
    text: '"Universal Sans Text", -apple-system, Arial, sans-serif',
  },
} as const

export const paletteOptions: ThemeOptions['palette'] = {
  mode: 'light',
  primary: {
    main: designTokens.colors.electricBlue,
    contrastText: designTokens.colors.pureWhite,
  },
  secondary: {
    main: designTokens.colors.graphite,
    contrastText: designTokens.colors.pureWhite,
  },
  background: {
    default: designTokens.colors.pureWhite,
    paper: designTokens.colors.pureWhite,
  },
  text: {
    primary: designTokens.colors.carbonDark,
    secondary: designTokens.colors.graphite,
    disabled: designTokens.colors.silverFog,
  },
  divider: designTokens.colors.cloudGray,
  action: {
    hover: 'rgba(23, 26, 32, 0.04)',
    selected: 'rgba(62, 106, 225, 0.08)',
    disabled: designTokens.colors.paleSilver,
    disabledBackground: designTokens.colors.lightAsh,
  },
}

export const typographyOptions: ThemeOptions['typography'] = {
  fontFamily: designTokens.fontFamily.text,
  fontWeightLight: 400,
  fontWeightRegular: 400,
  fontWeightMedium: 500,
  fontWeightBold: 500,
  h1: {
    fontFamily: designTokens.fontFamily.display,
    fontSize: '2.5rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
    color: designTokens.colors.carbonDark,
  },
  h2: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '1.375rem',
    fontWeight: 400,
    lineHeight: 0.91,
    letterSpacing: 'normal',
  },
  h3: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '1.0625rem',
    fontWeight: 500,
    lineHeight: 1.18,
    letterSpacing: 'normal',
  },
  h4: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '1rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
  },
  h5: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
  },
  h6: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
  },
  subtitle1: {
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.2,
  },
  subtitle2: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.43,
    color: designTokens.colors.pewter,
  },
  body1: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.43,
    color: designTokens.colors.graphite,
  },
  body2: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.43,
    color: designTokens.colors.pewter,
  },
  button: {
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
    textTransform: 'none',
  },
  caption: {
    fontSize: '0.75rem',
    fontWeight: 400,
    lineHeight: 1.33,
    color: designTokens.colors.pewter,
  },
  overline: {
    fontSize: '0.75rem',
    fontWeight: 500,
    lineHeight: 1.33,
    letterSpacing: 'normal',
    textTransform: 'none',
  },
}
