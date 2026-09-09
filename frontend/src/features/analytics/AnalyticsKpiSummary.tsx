import type { ReactNode } from 'react'
import Box from '@mui/material/Box'
import Grid from '@mui/material/Grid'
import Typography from '@mui/material/Typography'

import type { AnalyticsSummary } from '../../types'
import { designTokens } from '../../theme/tokens'

type KpiProps = {
  summary: AnalyticsSummary | null
  costLabel: string
  currency: string | null | undefined
}

function KpiTile({
  label,
  value,
  hint,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
}) {
  return (
    <Box sx={{ bgcolor: designTokens.colors.lightAsh, p: 2, borderRadius: 1 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h3">{value}</Typography>
      {hint}
    </Box>
  )
}

/** KPI strip for analytics — kept out of the chart chunk. */
export function AnalyticsKpiSummary({ summary, costLabel, currency }: KpiProps) {
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, sm: 3 }}>
        <KpiTile
          label="Calls"
          value={summary?.total_calls ?? '—'}
          hint={
            summary?.comparison ? (
              <Typography variant="caption" color="text.secondary">
                Prior {summary.comparison.total_calls.prior} (
                {summary.comparison.total_calls.delta >= 0 ? '+' : ''}
                {summary.comparison.total_calls.delta})
              </Typography>
            ) : null
          }
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 3 }}>
        <KpiTile label="Duration (min)" value={summary?.total_duration ?? '—'} />
      </Grid>
      <Grid size={{ xs: 12, sm: 3 }}>
        <KpiTile label="Avg (min)" value={summary?.avg_duration ?? '—'} />
      </Grid>
      <Grid size={{ xs: 12, sm: 3 }}>
        <KpiTile
          label={costLabel}
          value={
            summary?.total_cost != null
              ? `${summary.total_cost.toFixed(2)}${currency ? ` ${currency}` : ''}`
              : summary?.totals_by_currency
                ? 'Mixed'
                : '—'
          }
        />
      </Grid>
    </Grid>
  )
}
