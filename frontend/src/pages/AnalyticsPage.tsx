import CloudDownloadOutlinedIcon from '@mui/icons-material/CloudDownloadOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Grid from '@mui/material/Grid'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { BarChart } from '@mui/x-charts/BarChart'
import { LineChart } from '@mui/x-charts/LineChart'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { fetchTwilioAnalytics, getAnalyticsSummary } from '../api/analytics'
import { ApiError } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { useSnackbar } from '../components/SnackbarProvider'
import type { AnalyticsPeakHeatmap, AnalyticsSummary } from '../types'
import { designTokens } from '../theme/tokens'

function toDateInput(d: Date) {
  return d.toISOString().slice(0, 10)
}

function defaultDates() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  return { start: toDateInput(start), end: toDateInput(end) }
}

function hasSeries(block: { labels: string[]; values: number[] } | undefined) {
  return Boolean(block?.labels?.length && block.values.length)
}

function PeakHeatmap({ data }: { data: AnalyticsPeakHeatmap }) {
  const max = Math.max(0, ...data.matrix.flat())
  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Box
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
                <Tooltip key={`${day}-${hour}`} title={`${day} ${hour}:00 — ${value} calls`}>
                  <Box
                    sx={{
                      aspectRatio: '1',
                      borderRadius: 0.5,
                      bgcolor: designTokens.colors.electricBlue,
                      opacity: value === 0 ? 0.08 : 0.15 + intensity * 0.85,
                    }}
                  />
                </Tooltip>
              )
            })}
          </Box>
        ))}
      </Box>
    </Box>
  )
}

export function AnalyticsPage() {
  const { notify } = useSnackbar()
  const defaults = useMemo(() => defaultDates(), [])
  const [startDate, setStartDate] = useState(defaults.start)
  const [endDate, setEndDate] = useState(defaults.end)
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getAnalyticsSummary({ start: startDate, end: endDate })
      .then(setSummary)
      .catch((err: unknown) => {
        setSummary(null)
        setError(err instanceof ApiError ? err.message : 'Failed to load analytics')
      })
      .finally(() => setLoading(false))
  }, [startDate, endDate])

  useEffect(() => {
    load()
  }, [load])

  const hasChartData = Boolean(
    summary &&
      (hasSeries(summary.calls_over_time) ||
        hasSeries(summary.cost_over_time) ||
        hasSeries(summary.duration_distribution) ||
        hasSeries(summary.top_numbers) ||
        (summary.top_countries?.length ?? 0) > 0),
  )

  const onFetchTwilio = async () => {
    setFetching(true)
    try {
      const result = await fetchTwilioAnalytics()
      notify(result.message ?? 'Twilio data imported', 'success')
      load()
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Twilio fetch failed', 'error')
    } finally {
      setFetching(false)
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Analytics"
        subtitle="Call volume, cost, and geography from compact JSON — charts render in the browser."
        actions={
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={load}
              disabled={loading}
              aria-label="Refresh analytics"
            >
              Refresh
            </Button>
            <Button
              variant="contained"
              startIcon={<CloudDownloadOutlinedIcon />}
              onClick={onFetchTwilio}
              loading={fetching}
            >
              Fetch Twilio
            </Button>
          </Stack>
        }
      />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { sm: 'center' } }}
      >
        <TextField
          label="Start date"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <TextField
          label="End date"
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
        />
        <Button variant="outlined" onClick={load} disabled={loading}>
          Apply
        </Button>
      </Stack>

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <Stack spacing={2}>
          <Skeleton variant="rounded" height={80} />
          <Skeleton variant="rounded" height={280} />
        </Stack>
      ) : (
        <>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 3 }}>
              <Box sx={{ bgcolor: designTokens.colors.lightAsh, p: 2, borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Calls
                </Typography>
                <Typography variant="h3">{summary?.total_calls ?? '—'}</Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <Box sx={{ bgcolor: designTokens.colors.lightAsh, p: 2, borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Duration (min)
                </Typography>
                <Typography variant="h3">{summary?.total_duration ?? '—'}</Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <Box sx={{ bgcolor: designTokens.colors.lightAsh, p: 2, borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Avg (min)
                </Typography>
                <Typography variant="h3">{summary?.avg_duration ?? '—'}</Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <Box sx={{ bgcolor: designTokens.colors.lightAsh, p: 2, borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Cost
                </Typography>
                <Typography variant="h3">
                  {summary?.total_cost != null ? summary.total_cost.toFixed(2) : '—'}
                </Typography>
              </Box>
            </Grid>
          </Grid>

          {!hasChartData && !error ? (
            <Alert severity="info">
              No series for this range. Fetch Twilio data or widen the date filter.
            </Alert>
          ) : null}

          {hasChartData && summary ? (
            <Grid container spacing={2}>
              {hasSeries(summary.calls_over_time) ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Calls by day
                  </Typography>
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
                </Grid>
              ) : null}

              {hasSeries(summary.cost_over_time) ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Cost by day
                  </Typography>
                  <LineChart
                    height={280}
                    xAxis={[{ data: summary.cost_over_time.labels, scaleType: 'point' }]}
                    series={[
                      {
                        data: summary.cost_over_time.values,
                        label: 'Cost',
                        color: designTokens.colors.carbonDark,
                        area: false,
                      },
                    ]}
                    margin={{ left: 40, right: 16, top: 24, bottom: 40 }}
                  />
                </Grid>
              ) : null}

              {hasSeries(summary.duration_distribution) ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Duration distribution (min)
                  </Typography>
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
                </Grid>
              ) : null}

              {hasSeries(summary.top_numbers) ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Top destination numbers
                  </Typography>
                  <BarChart
                    height={280}
                    layout="horizontal"
                    yAxis={[{ data: summary.top_numbers.labels, scaleType: 'band', width: 110 }]}
                    series={[
                      {
                        data: summary.top_numbers.values,
                        label: 'Calls',
                        color: designTokens.colors.carbonDark,
                      },
                    ]}
                    margin={{ left: 16, right: 16, top: 24, bottom: 24 }}
                  />
                </Grid>
              ) : null}

              {summary.top_countries.length > 0 ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Top countries
                  </Typography>
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
                </Grid>
              ) : null}

              {summary.peak_hours_days?.matrix?.length ? (
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h3" sx={{ mb: 1 }}>
                    Peak hours by weekday
                  </Typography>
                  <PeakHeatmap data={summary.peak_hours_days} />
                </Grid>
              ) : null}
            </Grid>
          ) : null}
        </>
      )}
    </Stack>
  )
}
