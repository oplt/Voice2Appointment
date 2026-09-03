import Typography from '@mui/material/Typography'
import Stack from '@mui/material/Stack'
import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  subtitle?: string
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={2}
      sx={{
        mb: 3,
        alignItems: { sm: 'center' },
        justifyContent: 'space-between',
      }}
    >
      <Stack spacing={0.5}>
        <Typography variant="h1" sx={{ fontSize: { xs: '1.75rem', sm: '2.5rem' } }}>
          {title}
        </Typography>
        {subtitle ? <Typography variant="body1">{subtitle}</Typography> : null}
      </Stack>
      {actions}
    </Stack>
  )
}
