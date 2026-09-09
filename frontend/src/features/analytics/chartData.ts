import type { AnalyticsSummary } from '../../types'

function hasSeries(block: { labels: string[]; values: number[] } | undefined) {
  return Boolean(block?.labels?.length && block.values.length)
}

/** Lightweight helper — keep out of the charts chunk so filters/KPIs stay lean. */
export function analyticsHasChartData(summary: AnalyticsSummary | null | undefined): boolean {
  if (!summary) return false
  return (
    hasSeries(summary.calls_over_time) ||
    hasSeries(summary.cost_over_time) ||
    hasSeries(summary.duration_distribution) ||
    hasSeries(summary.top_numbers) ||
    summary.top_countries.length > 0 ||
    Boolean(summary.peak_hours_days?.matrix?.length) ||
    Boolean(
      summary.cost_over_time_by_currency &&
        Object.values(summary.cost_over_time_by_currency).some((s) => hasSeries(s)),
    )
  )
}
