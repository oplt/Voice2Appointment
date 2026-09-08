import type { Components, Theme } from '@mui/material/styles'

import {
  designTokens,
  semanticCssVariables,
  semanticDark,
  semanticLight,
} from './tokens'

const transition = [
  `border-color ${designTokens.motion.duration}`,
  `background-color ${designTokens.motion.duration}`,
  `color ${designTokens.motion.duration}`,
  `box-shadow 0.25s`,
].join(', ')

const lightVars = semanticCssVariables(semanticLight)
const darkVars = semanticCssVariables(semanticDark)

export const componentOverrides: Components<Theme> = {
  MuiCssBaseline: {
    styleOverrides: {
      ':root': {
        ...lightVars,
        colorScheme: 'light',
      },
      '[data-mui-color-scheme="dark"]': {
        ...darkVars,
        colorScheme: 'dark',
      },
      html: {
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
        fontSize: '100%',
        textSizeAdjust: '100%',
      },
      body: {
        margin: 0,
        backgroundColor: 'var(--surface-canvas)',
        color: 'var(--text-primary)',
      },
      '@media (prefers-reduced-motion: reduce)': {
        '*, *::before, *::after': {
          animationDuration: '0.01ms !important',
          animationIterationCount: '1 !important',
          transitionDuration: '0.01ms !important',
          scrollBehavior: 'auto !important',
        },
      },
      '@media (forced-colors: active)': {
        '*, *::before, *::after': {
          borderColor: 'CanvasText',
        },
        a: {
          color: 'LinkText',
        },
        ':focus-visible': {
          outline: '3px solid Highlight',
          outlineOffset: 2,
        },
      },
      '@media (prefers-contrast: more)': {
        body: {
          backgroundColor: '#FFFFFF',
          color: '#000000',
        },
        ':focus-visible': {
          outlineWidth: 4,
        },
      },
      a: {
        color: designTokens.colors.pewter,
        textDecoration: 'none',
        transition: `color ${designTokens.motion.duration}`,
      },
      'a:hover': {
        color: 'var(--text-primary)',
        textDecoration: 'underline',
      },
      ':focus-visible': {
        outline: `3px solid var(--action-primary)`,
        outlineOffset: 3,
      },
    },
  },
  MuiButton: {
    defaultProps: {
      disableElevation: true,
    },
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.button,
        minHeight: designTokens.layout.ctaMinHeight,
        minWidth: 44,
        padding: '8px 16px',
        transition,
        boxShadow: 'none',
        '&:hover': {
          boxShadow: 'none',
        },
      },
      contained: {
        border: '3px solid transparent',
        '&.MuiButton-colorPrimary:hover': {
          backgroundColor: '#355dc9',
        },
        '&.MuiButton-colorPrimary:focus-visible': {
          borderColor: 'var(--text-primary)',
        },
      },
      outlined: {
        borderWidth: 2,
        borderColor: 'var(--border-strong)',
        color: 'var(--text-secondary)',
        backgroundColor: 'var(--surface-primary)',
        '&:hover': {
          borderWidth: 2,
          borderColor: 'var(--text-secondary)',
          backgroundColor: 'var(--surface-secondary)',
        },
      },
      text: {
        color: 'var(--text-primary)',
        minWidth: 44,
        '&:hover': {
          backgroundColor: 'rgba(23, 26, 32, 0.04)',
        },
      },
    },
  },
  MuiAppBar: {
    defaultProps: {
      elevation: 0,
      color: 'transparent',
    },
    styleOverrides: {
      root: {
        backgroundColor: designTokens.colors.frostedGlass,
        backdropFilter: 'blur(12px)',
        color: 'var(--text-primary)',
        borderBottom: '1px solid var(--border-subtle)',
        boxShadow: 'none',
      },
    },
  },
  MuiToolbar: {
    styleOverrides: {
      root: {
        minHeight: 56,
        gap: 8,
      },
    },
  },
  MuiCard: {
    defaultProps: {
      elevation: 0,
    },
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.card,
        boxShadow: 'none',
        border: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--surface-primary)',
        backgroundImage: 'none',
      },
    },
  },
  MuiPaper: {
    defaultProps: {
      elevation: 0,
    },
    styleOverrides: {
      root: {
        backgroundImage: 'none',
        boxShadow: 'none',
      },
      rounded: {
        borderRadius: designTokens.radius.card,
      },
    },
  },
  MuiTextField: {
    defaultProps: {
      variant: 'outlined',
      size: 'medium',
    },
  },
  MuiFormLabel: {
    styleOverrides: {
      root: {
        fontSize: '1rem',
      },
      asterisk: {
        color: 'var(--status-error)',
      },
    },
  },
  MuiInputBase: {
    styleOverrides: {
      root: {
        minHeight: 44,
        fontSize: '1rem',
      },
    },
  },
  MuiInput: {
    styleOverrides: {
      root: {
        fontSize: '1rem',
        color: 'var(--text-primary)',
        '&:before': {
          borderBottomColor: 'var(--border-strong)',
        },
        '&:hover:not(.Mui-disabled):before': {
          borderBottomColor: 'var(--text-secondary)',
        },
        '&:after': {
          borderBottomColor: 'var(--action-primary)',
        },
      },
      input: {
        '&::placeholder': {
          color: designTokens.colors.silverFog,
          opacity: 1,
        },
      },
    },
  },
  MuiOutlinedInput: {
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.button,
        fontSize: '1rem',
        backgroundColor: 'var(--surface-primary)',
        '& .MuiOutlinedInput-notchedOutline': {
          borderColor: 'var(--border-strong)',
        },
        '&:hover .MuiOutlinedInput-notchedOutline': {
          borderColor: 'var(--text-secondary)',
        },
        '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
          borderColor: 'var(--action-primary)',
          borderWidth: 2,
        },
        '&.Mui-error .MuiOutlinedInput-notchedOutline': {
          borderColor: 'var(--status-error)',
        },
      },
      input: {
        paddingTop: 12,
        paddingBottom: 12,
        '&::placeholder': {
          color: designTokens.colors.silverFog,
          opacity: 1,
        },
      },
    },
  },
  MuiFilledInput: {
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.button,
        backgroundColor: 'var(--surface-secondary)',
        '&:before': { display: 'none' },
        '&:after': { display: 'none' },
        '&:hover': {
          backgroundColor: 'var(--surface-secondary)',
        },
        '&.Mui-focused': {
          backgroundColor: 'var(--surface-secondary)',
          boxShadow: `inset 0 0 0 2px var(--action-primary)`,
        },
      },
    },
  },
  MuiFormHelperText: {
    styleOverrides: {
      root: {
        fontSize: '0.75rem',
        marginLeft: 0,
        '&.Mui-error': {
          color: 'var(--status-error)',
        },
      },
    },
  },
  MuiTab: {
    styleOverrides: {
      root: {
        textTransform: 'none',
        fontWeight: 500,
        fontSize: '0.875rem',
        minHeight: 48,
        color: designTokens.colors.pewter,
        '&.Mui-selected': {
          color: 'var(--text-primary)',
        },
      },
    },
  },
  MuiTabs: {
    styleOverrides: {
      indicator: {
        backgroundColor: 'var(--action-primary)',
        height: 2,
      },
    },
  },
  MuiChip: {
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.button,
        fontWeight: 500,
      },
    },
  },
  MuiIconButton: {
    styleOverrides: {
      root: {
        minWidth: 44,
        minHeight: 44,
      },
    },
  },
  MuiTableContainer: {
    styleOverrides: {
      root: {
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
        border: '1px solid var(--border-subtle)',
        borderRadius: designTokens.radius.card,
      },
    },
  },
  MuiDialog: {
    styleOverrides: {
      paper: {
        borderRadius: designTokens.radius.card,
        boxShadow: 'none',
        border: '1px solid var(--border-subtle)',
      },
    },
  },
  MuiTableCell: {
    styleOverrides: {
      root: {
        borderBottomColor: 'var(--border-subtle)',
        fontSize: '0.875rem',
      },
      head: {
        color: 'var(--text-primary)',
        fontWeight: 500,
        fontSize: '0.75rem',
      },
    },
  },
  MuiAlert: {
    styleOverrides: {
      root: {
        borderRadius: designTokens.radius.button,
        boxShadow: 'none',
      },
    },
  },
  MuiTooltip: {
    styleOverrides: {
      tooltip: {
        backgroundColor: designTokens.colors.carbonDark,
        fontSize: '0.75rem',
        borderRadius: designTokens.radius.button,
      },
    },
  },
  MuiLink: {
    styleOverrides: {
      root: {
        color: designTokens.colors.pewter,
        textDecoration: 'none',
        transition: `color ${designTokens.motion.duration}`,
        '&:hover': {
          color: 'var(--text-primary)',
          textDecoration: 'underline',
        },
      },
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: '1px solid var(--border-subtle)',
        boxShadow: 'none',
        backgroundColor: 'var(--surface-primary)',
      },
    },
  },
}
