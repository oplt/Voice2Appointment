import CloudDownloadOutlinedIcon from '@mui/icons-material/CloudDownloadOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import Grid from '@mui/material/Grid'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { BarChart } from '@mui/x-charts/BarChart'
import { LineChart } from '@mui/x-charts/LineChart'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fetchTwilioAnalytics, getAnalyticsSummary } from '../api/analytics'
import { ApiError } from '../api/client'
import { ChartWithTable } from '../components/ChartWithTable'
import { PageHeader } from '../components/PageHeader'
import { useSnackbar } from '../components/SnackbarProvider'
import type { AnalyticsPeakHeatmap, AnalyticsSummary } from '../types'
import { designTokens } from '../theme/tokens'

/** Local calendar YYYY-MM-DD (no UTC shift). */
function toLocalDateInput(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseLocalDate(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (Number.isNaN(d.getTime())) return null
  return d
}

function defaultDates() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 29)
  return { start: toLocalDateInput(start), end: toLocalDateInput(end) }
}

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
  const [showTable, setShowTable] = useState(false)
  return (
    <Stack spacing={1}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          Peak cell intensity scales with call count (max {max}). Values are also in the table.
        </Typography>
        <Button size="small" variant="text" onClick={() => setShowTable((v) => !v)}>
          {showTable ? 'Hide table' : 'Show table'}
        </Button>
      </Stack>
      <Box sx={{ overflowX: 'auto' }} aria-hidden={showTable}>
        <Box
          role="img"
          aria-label="Heatmap of call volume by weekday and hour"
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
                    aria-label={`${day} ${hour}:00, ${value} calls`}
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
      {showTable ? (
        <TableContainer>
          <Table size="small" aria-label="Peak hours data table">
            <TableHead>
              <TableRow>
                <TableCell>Weekday</TableCell>
                <TableCell>Hour</TableCell>
                <TableCell align="right">Calls</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.weekdays.flatMap((day, rowIdx) =>
                data.hours
                  .map((hour) => ({
                    day,
                    hour,
                    value: data.matrix[rowIdx]?.[hour] ?? 0,
                  }))
                  .filter((cell) => cell.value > 0)
                  .map((cell) => (
                    <TableRow key={`${cell.day}-${cell.hour}`}>
                      <TableCell>{cell.day}</TableCell>
                      <TableCell>{cell.hour}:00</TableCell>
                      <TableCell align="right">{cell.value}</TableCell>
                    </TableRow>
                  )),
              )}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </Stack>
  )
}

type FilterState = { start: string; end: string; compare: boolean }

export function AnalyticsPage() {
  const { notify } = useSnackbar()
  const defaults = useMemo(() => defaultDates(), [])
  const [searchParams, setSearchParams] = useSearchParams()

  const appliedFromUrl = useMemo<FilterState>(() => {
    const start = searchParams.get('start') || defaults.start
    const end = searchParams.get('end') || defaults.end
    const compare = searchParams.get('compare') === '1'
    return { start, end, compare }
  }, [searchParams, defaults])

  const [draft, setDraft] = useState<FilterState>(appliedFromUrl)
  const [applied, setApplied] = useState<FilterState>(appliedFromUrl)
  const [filterError, setFilterError] = useState<string | null>(null)
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)

  useEffect(() => {
    setDraft(appliedFromUrl)
    setApplied(appliedFromUrl)
  }, [appliedFromUrl])

  const load = useCallback((filters: FilterState) => {
    setLoading(true)
    setError(null)
    getAnalyticsSummary({
      start: filters.start,
      end: filters.end,
      compare: filters.compare,
    })
      .then(setSummary)
      .catch((err: unknown) => {
        setSummary(null)
        setError(err instanceof ApiError ? err.message : 'Failed to load analytics')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load(applied)
  }, [applied, load])

  const validateDraft = (next: FilterState): string | null => {
    const start = parseLocalDate(next.start)
    const end = parseLocalDate(next.end)
    if (!start || !end) return 'Enter valid start and end dates (YYYY-MM-DD).'
    if (start > end) return 'Start date must be on or before end date.'
    const span = Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1
    if (span > 366) return 'Range cannot exceed 366 days.'
    return null
  }

  const onApply = () => {
    const err = validateDraft(draft)
    setFilterError(err)
    if (err) return
    const next = { ...draft }
    setApplied(next)
    const params = new URLSearchParams()
    params.set('start', next.start)
    params.set('end', next.end)
    if (next.compare) params.set('compare', '1')
    setSearchParams(params, { replace: true })
  }

  const applyPreset = (days: number) => {
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - (days - 1))
    setDraft((d) => ({
      ...d,
      start: toLocalDateInput(start),
      end: toLocalDateInput(end),
    }))
  }

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
      load(applied)
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Twilio fetch failed', 'error')
    } finally {
      setFetching(false)
    }
  }

  const currency = summary?.currency || summary?.reporting_currency || null
  const costLabel = currency ? `Cost (${currency})` : 'Cost'

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Analytics"
        subtitle="Call volume, cost, and booking funnel — charts render in the browser."
        actions={
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => load(applied)}
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

      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' } }}
          useFlexGap
        >
          <TextField
            label="Start date"
            type="date"
            value={draft.start}
            onChange={(e) => setDraft((d) => ({ ...d, start: e.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="End date"
            type="date"
            value={draft.end}
            onChange={(e) => setDraft((d) => ({ ...d, end: e.target.value }))}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={draft.compare}
                onChange={(e) => setDraft((d) => ({ ...d, compare: e.target.checked }))}
              />
            }
            label="Compare prior period"
          />
          <Button variant="contained" onClick={onApply} disabled={loading}>
            Apply
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <Button size="small" variant="outlined" onClick={() => applyPreset(7)}>
            Last 7 days
          </Button>
          <Button size="small" variant="outlined" onClick={() => applyPreset(30)}>
            Last 30 days
          </Button>
          <Button size="small" variant="outlined" onClick={() => applyPreset(90)}>
            Last 90 days
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
            Applied {applied.start} → {applied.end}
            {summary?.timezone ? ` (${summary.timezone})` : ''}
          </Typography>
        </Stack>
        {filterError ? <Alert severity="warning">{filterError}</Alert> : null}
      </Stack>

      {summary?.stale ? (
        <Alert severity="warning">
          Analytics may be stale
          {summary.source_synced_at
            ? ` (last Twilio sync ${summary.source_synced_at})`
            : ' (no Twilio sync recorded)'}
          . Fetch Twilio to refresh.
        </Alert>
      ) : null}

      {summary?.generated_at ? (
        <Typography variant="caption" color="text.secondary">
          Generated {summary.generated_at}
          {summary.source_synced_at ? ` · source synced ${summary.source_synced_at}` : ''}
        </Typography>
      ) : null}

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => load(applied)}>
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
                {summary?.comparison ? (
                  <Typography variant="caption" color="text.secondary">
                    Prior {summary.comparison.total_calls.prior} (
                    {summary.comparison.total_calls.delta >= 0 ? '+' : ''}
                    {summary.comparison.total_calls.delta})
                  </Typography>
                ) : null}
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
                  {costLabel}
                </Typography>
                <Typography variant="h3">
                  {summary?.total_cost != null
                    ? `${summary.total_cost.toFixed(2)}${currency ? ` ${currency}` : ''}`
                    : summary?.totals_by_currency
                      ? 'Mixed'
                      : '—'}
                </Typography>
              </Box>
            </Grid>
          </Grid>

          {summary?.comparison ? (
            <Alert severity="info">{summary.comparison.label}</Alert>
          ) : null}

          {summary?.funnel?.stages?.length ? (
            <Stack spacing={1}>
              <Typography variant="h3">Booking funnel</Typography>
              <Typography variant="body2" color="text.secondary">
                Each call counted at most once per stage. Historical rows without outcomes stay in
                Unknown.
              </Typography>
              <TableContainer>
                <Table size="small" aria-label="Booking funnel stages">
                  <TableHead>
                    <TableRow>
                      <TableCell>Stage</TableCell>
                      <TableCell align="right">Calls</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.funnel.stages.map((stage) => (
                      <TableRow key={stage.id}>
                        <TableCell>{stage.label}</TableCell>
                        <TableCell align="right">{stage.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {summary.funnel.failure_categories.length > 0 ? (
                <TableContainer>
                  <Table size="small" aria-label="Failure categories">
                    <TableHead>
                      <TableRow>
                        <TableCell>Failure category</TableCell>
                        <TableCell align="right">Count</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {summary.funnel.failure_categories.map((row) => (
                        <TableRow key={row.code}>
                          <TableCell>{row.code}</TableCell>
                          <TableCell align="right">{row.count}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}
            </Stack>
          ) : null}

          {!hasChartData && !error ? (
            <Alert severity="info">
              No series for this range. Fetch Twilio data or widen the date filter.
            </Alert>
          ) : null}

          {hasChartData && summary ? (
            <Grid container spacing={2}>
              {hasSeries(summary.calls_over_time) ? (
                <Grid size={{ xs: 12, md: 6 }}>
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
                <Grid size={{ xs: 12, md: 6 }}>
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

              {hasSeries(summary.duration_distribution) ? (
                <Grid size={{ xs: 12, md: 6 }}>
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
                <Grid size={{ xs: 12, md: 6 }}>
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
                <Grid size={{ xs: 12, md: 6 }}>
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
