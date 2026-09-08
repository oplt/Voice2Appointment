import Alert from '@mui/material/Alert'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { PageHeader } from './PageHeader'

type FeaturePlaceholderProps = {
  title: string
  description: string
}

/** Thin product-domain shell until Phase 9/11 wire full UI. */
export function FeaturePlaceholder({ title, description }: FeaturePlaceholderProps) {
  return (
    <Stack spacing={2}>
      <PageHeader title={title} />
      <Typography variant="body1" color="text.secondary">
        {description}
      </Typography>
      <Alert severity="info">
        Backend domain APIs remain the source of truth. This module is scaffolded for product
        architecture; full workflows land with later phases.
      </Alert>
    </Stack>
  )
}
