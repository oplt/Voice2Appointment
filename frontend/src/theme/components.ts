import type { Components, Theme } from '@mui/material/styles'

import { designTokens } from './tokens'

const transition = [
  `border-color ${designTokens.motion.duration}`,
  `background-color ${designTokens.motion.duration}`,
  `color ${designTokens.motion.duration}`,
  `box-shadow 0.25s`,
].join(', ')

export const componentOverrides: Components<Theme> = {
  MuiCssBaseline: {
    styleOverrides: {
      html: {
        WebkitFontSmoothing: 'antialiased',
        MozOsxFontSmoothing: 'grayscale',
      },
      body: {
        margin: 0,
        backgroundColor: designTokens.colors.pureWhite,
        color: designTokens.colors.carbonDark,
      },
      '@media (prefers-reduced-motion: reduce)': {
        '*, *::before, *::after': {
          animationDuration: '0.01ms !important',
          animationIterationCount: '1 !important',
          transitionDuration: '0.01ms !important',
          scrollBehavior: 'auto !important',
        },
      },
      a: {
        color: designTokens.colors.pewter,
        textDecoration: 'none',
        transition: `color ${designTokens.motion.duration}`,
      },
      'a:hover': {
        color: designTokens.colors.carbonDark,
        textDecoration: 'underline',
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
          borderColor: designTokens.colors.carbonDark,
        },
      },
      outlined: {
        borderWidth: 3,
        borderColor: designTokens.colors.cloudGray,
        color: designTokens.colors.graphite,
        backgroundColor: designTokens.colors.pureWhite,
        '&:hover': {
          borderWidth: 3,
          borderColor: designTokens.colors.paleSilver,
          backgroundColor: designTokens.colors.lightAsh,
        },
      },
      text: {
        color: designTokens.colors.carbonDark,
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
        color: designTokens.colors.carbonDark,
        borderBottom: 'none',
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
        border: 'none',
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
      variant: 'standard',
    },
  },
  MuiInput: {
    styleOverrides: {
      root: {
        fontSize: '0.875rem',
        color: designTokens.colors.carbonDark,
        '&:before': {
          borderBottomColor: designTokens.colors.paleSilver,
        },
        '&:hover:not(.Mui-disabled):before': {
          borderBottomColor: designTokens.colors.graphite,
        },
        '&:after': {
          borderBottomColor: designTokens.colors.electricBlue,
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
        fontSize: '0.875rem',
        '& .MuiOutlinedInput-notchedOutline': {
          borderColor: designTokens.colors.paleSilver,
        },
        '&:hover .MuiOutlinedInput-notchedOutline': {
          borderColor: designTokens.colors.graphite,
        },
        '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
          borderColor: designTokens.colors.electricBlue,
          borderWidth: 1,
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
  MuiFormHelperText: {
    styleOverrides: {
      root: {
        fontSize: '0.75rem',
        color: designTokens.colors.pewter,
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
          color: designTokens.colors.carbonDark,
        },
      },
    },
  },
  MuiTabs: {
    styleOverrides: {
      indicator: {
        backgroundColor: designTokens.colors.electricBlue,
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
      },
    },
  },
  MuiDialog: {
    styleOverrides: {
      paper: {
        borderRadius: designTokens.radius.card,
        boxShadow: 'none',
        border: `1px solid ${designTokens.colors.cloudGray}`,
      },
    },
  },
  MuiTableCell: {
    styleOverrides: {
      root: {
        borderBottomColor: designTokens.colors.cloudGray,
        fontSize: '0.875rem',
      },
      head: {
        color: designTokens.colors.carbonDark,
        fontWeight: 500,
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
        transition: `color ${designTokens.motion.duration}, box-shadow ${designTokens.motion.duration} ${designTokens.motion.easing}`,
        '&:hover': {
          color: designTokens.colors.carbonDark,
          textDecoration: 'underline',
        },
      },
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: 'none',
        boxShadow: 'none',
      },
    },
  },
}
