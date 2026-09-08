import Box from '@mui/material/Box'

/** Visible on keyboard focus only — first tab stop. */
export function SkipLink() {
  return (
    <Box
      component="a"
      href="#main-content"
      sx={{
        position: 'absolute',
        left: -10000,
        top: 8,
        zIndex: 4000,
        px: 2,
        py: 1,
        bgcolor: 'var(--action-primary)',
        color: 'var(--surface-primary)',
        borderRadius: 1,
        fontWeight: 500,
        textDecoration: 'none',
        '&:focus': {
          left: 8,
          outline: '3px solid var(--text-primary)',
          outlineOffset: 2,
        },
      }}
    >
      Skip to main content
    </Box>
  )
}
