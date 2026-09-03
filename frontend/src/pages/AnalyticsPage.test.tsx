import { describe, expect, it } from 'vitest'

import type { AnalyticsSummary } from '../types'

function hasSeries(block: { labels: string[]; values: number[] } | undefined) {
  return Boolean(block?.labels?.length && block.values.length)
}

describe('analytics summary shape', () => {
  it('treats compact JSON series as chart-ready without PNG/GeoJSON', () => {
    const summary: AnalyticsSummary = {
      total_calls: 2,
      total_duration: 2,
      avg_duration: 1,
      total_cost: 0.03,
      calls_over_time: { labels: ['2026-09-01'], values: [2] },
      duration_distribution: { labels: ['1-2'], values: [2] },
      cost_over_time: { labels: ['2026-09-01'], values: [0.03] },
      top_numbers: { labels: ['+1'], values: [2] },
      peak_hours_days: {
        weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        hours: Array.from({ length: 24 }, (_, i) => i),
        matrix: Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0)),
      },
      top_countries: [{ country: 'Belgium', iso3: 'BEL', calls: 2 }],
      geo_country_counts: [{ country: 'Belgium', iso3: 'BEL', calls: 2 }],
    }

    expect(hasSeries(summary.calls_over_time)).toBe(true)
    expect(summary.top_countries[0]?.iso3).toBe('BEL')
    expect('call_details' in summary).toBe(false)
  })
})
