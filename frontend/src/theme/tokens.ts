import type { ThemeOptions } from '@mui/material/styles'

/**
 * Raw brand palette (DESIGN.md). Prefer semantic tokens in UI code.
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
    success: '#1B7A4E',
    warning: '#9A6700',
    error: '#B42318',
  },
  radius: {
    none: 0,
    button: 4,
    card: 8,
  },
  motion: {
    duration: '0.33s',
    easing: 'cubic-bezier(0.5, 0, 0, 0.75)',
  },
  layout: {
    maxWidth: 1383,
    ctaMinHeight: 44,
  },
  fontFamily: {
    display: '"Universal Sans Display", -apple-system, Arial, sans-serif',
    text: '"Universal Sans Text", -apple-system, Arial, sans-serif',
  },
} as const

/** Semantic product tokens — light scheme. */
export const semanticLight = {
  surface: {
    canvas: designTokens.colors.pureWhite,
    primary: designTokens.colors.pureWhite,
    secondary: designTokens.colors.lightAsh,
  },
  border: {
    subtle: designTokens.colors.cloudGray,
    strong: designTokens.colors.paleSilver,
  },
  text: {
    primary: designTokens.colors.carbonDark,
    secondary: designTokens.colors.graphite,
  },
  status: {
    success: designTokens.colors.success,
    warning: designTokens.colors.warning,
    error: designTokens.colors.error,
  },
  action: {
    primary: designTokens.colors.electricBlue,
  },
} as const

/** Semantic product tokens — dark scheme (prepared; not a blocking product requirement). */
export const semanticDark = {
  surface: {
    canvas: '#0F1115',
    primary: '#171A20',
    secondary: '#22262E',
  },
  border: {
    subtle: '#2C313A',
    strong: '#3E4450',
  },
  text: {
    primary: '#F5F6F7',
    secondary: '#C5C7CB',
  },
  status: {
    success: '#3DDC97',
    warning: '#F5C542',
    error: '#FF6B6B',
  },
  action: {
    primary: '#5B87F0',
  },
} as const

export type SemanticTokens = {
  surface: { canvas: string; primary: string; secondary: string }
  border: { subtle: string; strong: string }
  text: { primary: string; secondary: string }
  status: { success: string; warning: string; error: string }
  action: { primary: string }
}

export function semanticCssVariables(tokens: SemanticTokens): Record<string, string> {
  return {
    '--surface-canvas': tokens.surface.canvas,
    '--surface-primary': tokens.surface.primary,
    '--surface-secondary': tokens.surface.secondary,
    '--border-subtle': tokens.border.subtle,
    '--border-strong': tokens.border.strong,
    '--text-primary': tokens.text.primary,
    '--text-secondary': tokens.text.secondary,
    '--status-success': tokens.status.success,
    '--status-warning': tokens.status.warning,
    '--status-error': tokens.status.error,
    '--action-primary': tokens.action.primary,
  }
}

export const paletteOptions: ThemeOptions['palette'] = {
  mode: 'light',
  primary: {
    main: semanticLight.action.primary,
    contrastText: designTokens.colors.pureWhite,
  },
  secondary: {
    main: semanticLight.text.secondary,
    contrastText: designTokens.colors.pureWhite,
  },
  background: {
    default: semanticLight.surface.canvas,
    paper: semanticLight.surface.primary,
  },
  text: {
    primary: semanticLight.text.primary,
    secondary: semanticLight.text.secondary,
    disabled: designTokens.colors.silverFog,
  },
  divider: semanticLight.border.subtle,
  success: { main: semanticLight.status.success },
  warning: { main: semanticLight.status.warning },
  error: { main: semanticLight.status.error },
  action: {
    hover: 'rgba(23, 26, 32, 0.04)',
    selected: 'rgba(62, 106, 225, 0.08)',
    disabled: designTokens.colors.paleSilver,
    disabledBackground: semanticLight.surface.secondary,
  },
}

export const darkPaletteOptions: ThemeOptions['palette'] = {
  mode: 'dark',
  primary: {
    main: semanticDark.action.primary,
    contrastText: semanticDark.surface.canvas,
  },
  secondary: {
    main: semanticDark.text.secondary,
    contrastText: semanticDark.surface.canvas,
  },
  background: {
    default: semanticDark.surface.canvas,
    paper: semanticDark.surface.primary,
  },
  text: {
    primary: semanticDark.text.primary,
    secondary: semanticDark.text.secondary,
    disabled: '#7A7F88',
  },
  divider: semanticDark.border.subtle,
  success: { main: semanticDark.status.success },
  warning: { main: semanticDark.status.warning },
  error: { main: semanticDark.status.error },
  action: {
    hover: 'rgba(255, 255, 255, 0.06)',
    selected: 'rgba(91, 135, 240, 0.16)',
    disabled: '#5A5F69',
    disabledBackground: semanticDark.surface.secondary,
  },
}

/**
 * Typography: readable multi-line headings; ~16px body for forms/content;
 * 12–14px reserved for captions/metadata/dense tables.
 */
export const typographyOptions: ThemeOptions['typography'] = {
  fontFamily: designTokens.fontFamily.text,
  fontWeightLight: 400,
  fontWeightRegular: 400,
  fontWeightMedium: 500,
  fontWeightBold: 500,
  htmlFontSize: 16,
  h1: {
    fontFamily: designTokens.fontFamily.display,
    fontSize: 'clamp(1.75rem, 1.4rem + 1.2vw, 2.5rem)',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
    color: semanticLight.text.primary,
  },
  h2: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: 'clamp(1.25rem, 1.1rem + 0.5vw, 1.5rem)',
    fontWeight: 500,
    lineHeight: 1.2,
    letterSpacing: 'normal',
  },
  h3: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '1.125rem',
    fontWeight: 500,
    lineHeight: 1.25,
    letterSpacing: 'normal',
  },
  h4: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '1rem',
    fontWeight: 500,
    lineHeight: 1.25,
    letterSpacing: 'normal',
  },
  h5: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.25,
    letterSpacing: 'normal',
  },
  h6: {
    fontFamily: designTokens.fontFamily.text,
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.25,
    letterSpacing: 'normal',
  },
  subtitle1: {
    fontSize: '1rem',
    fontWeight: 500,
    lineHeight: 1.35,
  },
  subtitle2: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.4,
    color: designTokens.colors.pewter,
  },
  body1: {
    fontSize: '1rem',
    fontWeight: 400,
    lineHeight: 1.5,
    color: semanticLight.text.secondary,
  },
  body2: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.45,
    color: designTokens.colors.pewter,
  },
  button: {
    fontSize: '0.875rem',
    fontWeight: 500,
    lineHeight: 1.25,
    letterSpacing: 'normal',
    textTransform: 'none',
  },
  caption: {
    fontSize: '0.75rem',
    fontWeight: 400,
    lineHeight: 1.35,
    color: designTokens.colors.pewter,
  },
  overline: {
    fontSize: '0.75rem',
    fontWeight: 500,
    lineHeight: 1.35,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
  },
}
