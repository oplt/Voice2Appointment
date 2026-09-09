import Box from '@mui/material/Box'
import Grid from '@mui/material/Grid'
import Typography from '@mui/material/Typography'
import { BarChart } from '@mui/x-charts/BarChart'
import { LineChart } from '@mui/x-charts/LineChart'

import { ChartWithTable, HeatmapWithTable } from '../../components/ChartWithTable'
import type { AnalyticsPeakHeatmap, AnalyticsSummary } from '../../types'
import { designTokens } from '../../theme/tokens'

function hasSeries(block: { labels: string[]; values: number[] } | undefined) {
  return Boolean(block?.labels?.length && block.values.length)
}

function seriesSummary(labels: string[], values: number[], unit: string) {
  const total = values.reduce((a, b) => a + b, 0)
  const peakIdx = values.reduce((best, v, i) => (v > (values[best] ?? 0) ? i : best), 0)
  const peakLabel = labels[peakIdx] ?? '—'
  return `${values.length} points; total ${total} ${unit}; peak ${values[peakIdx] ?? 0} on ${peakLabel}.`
}

function PeakHeatmap({ data }: { data: AnalyticsPeakHeatmap }) {
  const max = Math.max(0, ...data.matrix.flat())
  return (
    <HeatmapWithTable
      title="Peak hours by weekday"
      summary={`Peak cell intensity scales with call count (max ${max}). Full matrix including zeros is in the table.`}
      weekdays={data.weekdays}
      hours={data.hours}
      matrix={data.matrix}
    >
      <Box sx={{ overflowX: 'auto' }}>
        <Box
          role="img"
          aria-label="Heatmap of call volume by weekday and hour; open the data table for exact values"
          sx={{
            display: 'grid',
            gridTemplateColumns: `48px repeat(${data.hours.length}, minmax(14px, 1fr))`,
            gap: 0.5,
            minWidth: 420,
          }}
        >
          <Box />
          {data.hours.map((hour) => (
            <Typography
              key={hour}
              variant="caption"
              color="text.secondary"
              sx={{ textAlign: 'center', fontSize: 10 }}
            >
              {hour % 6 === 0 ? hour : ''}
            </Typography>
          ))}
          {data.weekdays.map((day, rowIdx) => (
            <Box key={day} sx={{ display: 'contents' }}>
              <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
                {day}
              </Typography>
              {data.hours.map((hour) => {
                const value = data.matrix[rowIdx]?.[hour] ?? 0
                const intensity = max > 0 ? value / max : 0
                return (
                  <Box
                    key={`${day}-${hour}`}
                    title={`${day} ${hour}:00 — ${value} calls`}
                    sx={{
                      aspectRatio: '1',
                      borderRadius: 0.5,
                      bgcolor: designTokens.colors.electricBlue,
                      opacity: value === 0 ? 0.08 : 0.15 + intensity * 0.85,
                      border:
                        value > 0
                          ? `1px solid ${designTokens.colors.carbonDark}`
                          : '1px solid transparent',
                    }}
                  />
                )
              })}
            </Box>
          ))}
        </Box>
      </Box>
    </HeatmapWithTable>
  )
}

const chartSectionSx = {
  contentVisibility: 'auto' as const,
  containIntrinsicSize: '0 320px',
}

type AnalyticsChartsProps = {
  summary: AnalyticsSummary
  currency: string | null | undefined
  costLabel: string
}

/** Lazy-loaded chart visualizations — keep out of the initial analytics route chunk. */
export function AnalyticsCharts({ summary, currency, costLabel }: AnalyticsChartsProps) {
  return (
    <Grid container spacing={2} sx={chartSectionSx}>
      {hasSeries(summary.calls_over_time) ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <ChartWithTable
            title="Calls by day"
            summary={seriesSummary(
              summary.calls_over_time.labels,
              summary.calls_over_time.values,
              'calls',
            )}
            labels={summary.calls_over_time.labels}
            values={summary.calls_over_time.values}
            valueLabel="Calls"
          >
            <BarChart
              height={280}
              xAxis={[{ data: summary.calls_over_time.labels, scaleType: 'band' }]}
              series={[
                {
                  data: summary.calls_over_time.values,
                  label: 'Calls',
                  color: designTokens.colors.electricBlue,
                },
              ]}
              margin={{ left: 40, right: 16, top: 24, bottom: 40 }}
            />
          </ChartWithTable>
        </Grid>
      ) : null}

      {hasSeries(summary.cost_over_time) ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <ChartWithTable
            title={`Cost by day${currency ? ` (${currency})` : ''}`}
            summary={seriesSummary(
              summary.cost_over_time.labels,
              summary.cost_over_time.values,
              currency || 'cost',
            )}
            labels={summary.cost_over_time.labels}
            values={summary.cost_over_time.values}
            valueLabel={costLabel}
          >
            <LineChart
              height={280}
              xAxis={[{ data: summary.cost_over_time.labels, scaleType: 'point' }]}
              series={[
                {
                  data: summary.cost_over_time.values,
                  label: costLabel,
                  color: designTokens.colors.carbonDark,
                  area: false,
                },
              ]}
              margin={{ left: 40, right: 16, top: 24, bottom: 40 }}
            />
          </ChartWithTable>
        </Grid>
      ) : null}

      {!hasSeries(summary.cost_over_time) &&
      summary.cost_over_time_by_currency &&
      Object.keys(summary.cost_over_time_by_currency).length > 0
        ? Object.entries(summary.cost_over_time_by_currency).map(([unit, series]) =>
            hasSeries(series) ? (
              <Grid key={unit} size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
                <ChartWithTable
                  title={`Cost by day (${unit})`}
                  summary={seriesSummary(series.labels, series.values, unit)}
                  labels={series.labels}
                  values={series.values}
                  valueLabel={`Cost (${unit})`}
                >
                  <LineChart
                    height={280}
                    xAxis={[{ data: series.labels, scaleType: 'point' }]}
                    series={[
                      {
                        data: series.values,
                        label: `Cost (${unit})`,
                        color: designTokens.colors.carbonDark,
                        area: false,
                      },
                    ]}
                    margin={{ left: 40, right: 16, top: 24, bottom: 40 }}
                  />
                </ChartWithTable>
              </Grid>
            ) : null,
          )
        : null}

      {hasSeries(summary.duration_distribution) ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <ChartWithTable
            title="Duration distribution (min)"
            summary={seriesSummary(
              summary.duration_distribution.labels,
              summary.duration_distribution.values,
              'calls',
            )}
            labels={summary.duration_distribution.labels}
            values={summary.duration_distribution.values}
            valueLabel="Calls"
          >
            <BarChart
              height={280}
              xAxis={[
                {
                  data: summary.duration_distribution.labels,
                  scaleType: 'band',
                },
              ]}
              series={[
                {
                  data: summary.duration_distribution.values,
                  label: 'Calls',
                  color: designTokens.colors.electricBlue,
                },
              ]}
              margin={{ left: 40, right: 16, top: 24, bottom: 40 }}
            />
          </ChartWithTable>
        </Grid>
      ) : null}

      {hasSeries(summary.top_numbers) ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <ChartWithTable
            title="Top destination numbers (masked)"
            summary="Phone labels show last four digits only."
            labels={summary.top_numbers.labels}
            values={summary.top_numbers.values}
            valueLabel="Calls"
          >
            <BarChart
              height={280}
              layout="horizontal"
              yAxis={[
                {
                  data: summary.top_numbers.labels,
                  scaleType: 'band',
                  width: 110,
                },
              ]}
              series={[
                {
                  data: summary.top_numbers.values,
                  label: 'Calls',
                  color: designTokens.colors.carbonDark,
                },
              ]}
              margin={{ left: 16, right: 16, top: 24, bottom: 24 }}
            />
          </ChartWithTable>
        </Grid>
      ) : null}

      {summary.top_countries.length > 0 ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <ChartWithTable
            title="Top countries"
            summary={`${summary.top_countries.length} countries in range.`}
            labels={summary.top_countries.map((c) => c.country)}
            values={summary.top_countries.map((c) => c.calls)}
            valueLabel="Calls"
          >
            <BarChart
              height={280}
              layout="horizontal"
              yAxis={[
                {
                  data: summary.top_countries.map((c) => c.country),
                  scaleType: 'band',
                  width: 110,
                },
              ]}
              series={[
                {
                  data: summary.top_countries.map((c) => c.calls),
                  label: 'Calls',
                  color: designTokens.colors.electricBlue,
                },
              ]}
              margin={{ left: 16, right: 16, top: 24, bottom: 24 }}
            />
          </ChartWithTable>
        </Grid>
      ) : null}

      {summary.peak_hours_days?.matrix?.length ? (
        <Grid size={{ xs: 12, md: 6 }} sx={chartSectionSx}>
          <PeakHeatmap data={summary.peak_hours_days} />
        </Grid>
      ) : null}
    </Grid>
  )
}
