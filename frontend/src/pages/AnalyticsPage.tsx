import CloudDownloadOutlinedIcon from '@mui/icons-material/CloudDownloadOutlined'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
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
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  fetchTwilioAnalytics,
  getAnalyticsMeta,
  getAnalyticsSummary,
  getTwilioSyncStatus,
  type TwilioSyncStatus,
} from '../api/analytics'
import { ApiError } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { useSnackbar } from '../components/SnackbarProvider'
import { AnalyticsKpiSummary } from '../features/analytics/AnalyticsKpiSummary'
import { analyticsHasChartData } from '../features/analytics/chartData'
import {
  type AnalyticsFilterState,
  type AnalyticsMeta,
  type FilterFieldErrors,
  defaultFiltersFromMeta,
  filterKey,
  filtersEqual,
  filtersFromSearchParams,
  filtersToSearchParams,
  presetRange,
  validateFilters,
} from '../features/analytics/filters'
import type { AnalyticsSummary } from '../types'

const AnalyticsCharts = lazy(async () => {
  const mod = await import('../features/analytics/AnalyticsCharts')
  return { default: mod.AnalyticsCharts }
})

const EMPTY_SUMMARY: AnalyticsSummary | null = null

export function AnalyticsPage() {
  const { notify } = useSnackbar()
  const [searchParams, setSearchParams] = useSearchParams()

  const [meta, setMeta] = useState<AnalyticsMeta | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [draft, setDraft] = useState<AnalyticsFilterState | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FilterFieldErrors | null>(null)
  const [summary, setSummary] = useState<AnalyticsSummary | null>(EMPTY_SUMMARY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)
  const [twilioSyncStatus, setTwilioSyncStatus] = useState<TwilioSyncStatus | null>(null)

  const lastValidAppliedRef = useRef<AnalyticsFilterState | null>(null)
  const lastFetchedKeyRef = useRef<string | null>(null)

  const defaults = useMemo(
    () => (meta ? defaultFiltersFromMeta(meta) : null),
    [meta],
  )

  const urlParsed = useMemo(() => {
    if (!defaults) return null
    return filtersFromSearchParams(searchParams, defaults)
  }, [searchParams, defaults])

  const candidate = urlParsed?.filters ?? null
  const urlErrors = useMemo(
    () => (candidate && meta ? validateFilters(candidate, meta.max_range_days) : null),
    [candidate, meta],
  )

  const applied = useMemo(() => {
    if (!meta) return null
    if (urlErrors) return lastValidAppliedRef.current
    return candidate
  }, [candidate, meta, urlErrors])

  const appliedFetchKey = applied && !urlErrors ? filterKey(applied) : null

  useEffect(() => {
    const controller = new AbortController()
    getAnalyticsMeta(controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return
        setMeta(next)
        setTwilioSyncStatus(next.twilio_sync ?? null)
        setMetaError(null)
        setDraft((prev) => prev ?? defaultFiltersFromMeta(next))
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setMetaError(err instanceof ApiError ? err.message : 'Failed to load analytics settings')
        setLoading(false)
      })
    return () => {
      controller.abort()
    }
  }, [])

  // Sync draft from URL only when navigation changes applied filters (back/forward / Apply).
  useEffect(() => {
    if (!candidate || urlErrors) return
    setDraft((prev) => (prev && filtersEqual(prev, candidate) ? prev : candidate))
    setFieldErrors(null)
  }, [candidate, urlErrors])

  const load = useCallback((filters: AnalyticsFilterState, signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    getAnalyticsSummary(
      {
        start: filters.start,
        end: filters.end,
        compare: filters.compare,
      },
      signal,
    )
      .then((data) => {
        if (signal?.aborted) return
        setSummary(data)
      })
      .catch((err: unknown) => {
        if (signal?.aborted) return
        setSummary(null)
        setError(err instanceof ApiError ? err.message : 'Failed to load analytics')
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!meta) return
    if (urlErrors) {
      setFieldErrors(urlErrors)
      setLoading(false)
      return
    }
    if (!applied || !appliedFetchKey) return
    if (lastFetchedKeyRef.current === appliedFetchKey) return
    lastFetchedKeyRef.current = appliedFetchKey
    lastValidAppliedRef.current = applied
    const controller = new AbortController()
    load(applied, controller.signal)
    return () => {
      controller.abort()
    }
  }, [applied, appliedFetchKey, meta, urlErrors, load])

  const onApply = () => {
    if (!draft || !meta) return
    const err = validateFilters(draft, meta.max_range_days)
    setFieldErrors(err)
    if (err) return
    const next = { ...draft }
    // Canonical applied source = URL. One setSearchParams → one fetch key change.
    setSearchParams(filtersToSearchParams(next), { replace: true })
  }

  const applyPreset = (days: number) => {
    if (!meta) return
    const range = presetRange(meta, days)
    setDraft((d) => ({ ...(d ?? defaultFiltersFromMeta(meta)), ...range }))
    setFieldErrors(null)
  }

  const hasChartData = analyticsHasChartData(summary)

  const onFetchTwilio = async () => {
    if (!applied) return
    setFetching(true)
    try {
      const queued = await fetchTwilioAnalytics()
      setTwilioSyncStatus(queued)
      notify('Twilio sync queued', 'info')
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500))
        const status = await getTwilioSyncStatus()
        setTwilioSyncStatus(status)
        if (status.status === 'healthy') {
          notify('Twilio sync completed', 'success')
          lastFetchedKeyRef.current = null
          load(applied)
          break
        }
        if (status.status === 'error') {
          notify(status.error_code ?? 'Twilio sync failed', 'error')
          break
        }
      }
    } catch (err: unknown) {
      notify(err instanceof ApiError ? err.message : 'Twilio fetch failed', 'error')
    } finally {
      setFetching(false)
    }
  }

  const currency = summary?.currency || summary?.reporting_currency || null
  const costLabel = currency ? `Cost (${currency})` : 'Cost'
  const appliedLabel = applied ?? lastValidAppliedRef.current

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
              onClick={() => applied && load(applied)}
              disabled={loading || !applied}
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
              {fetching ? 'Syncing…' : 'Fetch Twilio'}
            </Button>
          </Stack>
        }
      />

      {metaError ? <Alert severity="error">{metaError}</Alert> : null}
      {twilioSyncStatus ? (
        <Alert severity={twilioSyncStatus.status === 'error' ? 'error' : 'info'}>
          Twilio sync: {twilioSyncStatus.status}
          {twilioSyncStatus.last_synced_at ? ` · last synced ${twilioSyncStatus.last_synced_at}` : ''}
        </Alert>
      ) : null}

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
            value={draft?.start ?? ''}
            onChange={(e) =>
              setDraft((d) => (d ? { ...d, start: e.target.value } : d))
            }
            error={Boolean(fieldErrors?.start)}
            helperText={fieldErrors?.start}
            disabled={!draft}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label="End date"
            type="date"
            value={draft?.end ?? ''}
            onChange={(e) => setDraft((d) => (d ? { ...d, end: e.target.value } : d))}
            error={Boolean(fieldErrors?.end)}
            helperText={fieldErrors?.end}
            disabled={!draft}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={draft?.compare ?? false}
                onChange={(e) =>
                  setDraft((d) => (d ? { ...d, compare: e.target.checked } : d))
                }
                disabled={!draft}
              />
            }
            label="Compare prior period"
          />
          <Button variant="contained" onClick={onApply} disabled={loading || !draft}>
            Apply
          </Button>
        </Stack>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <Button size="small" variant="outlined" onClick={() => applyPreset(7)} disabled={!meta}>
            Last 7 days
          </Button>
          <Button size="small" variant="outlined" onClick={() => applyPreset(30)} disabled={!meta}>
            Last 30 days
          </Button>
          <Button size="small" variant="outlined" onClick={() => applyPreset(90)} disabled={!meta}>
            Last 90 days
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
            {urlErrors
              ? 'URL filters invalid — correct dates to load'
              : appliedLabel
                ? `Applied ${appliedLabel.start} → ${appliedLabel.end}`
                : 'Loading filters…'}
            {meta?.timezone ? ` (${meta.timezone})` : ''}
            {meta ? ` · max ${meta.max_range_days}d` : ''}
          </Typography>
        </Stack>
        {fieldErrors?.range ? <Alert severity="warning">{fieldErrors.range}</Alert> : null}
        {urlErrors && summary ? (
          <Alert severity="warning">
            URL filters are invalid. Showing the last valid result until corrected.
          </Alert>
        ) : null}
      </Stack>

      {summary?.stale ? (
        <Alert severity="warning">
          Analytics may be stale
          {summary.stale_reason ? ` (${summary.stale_reason})` : ''}
          {summary.source_synced_at
            ? ` — last Twilio sync ${summary.source_synced_at}`
            : ' — no Twilio sync recorded'}
          . Fetch Twilio to refresh.
        </Alert>
      ) : null}

      {summary?.generated_at ? (
        <Typography variant="caption" color="text.secondary">
          Generated {summary.generated_at}
          {summary.cache_status ? ` · cache ${summary.cache_status}` : ''}
          {summary.cache_status === 'hit' && summary.cache_age_seconds != null
            ? ` (${summary.cache_age_seconds}s old)`
            : ''}
          {summary.source_synced_at ? ` · source synced ${summary.source_synced_at}` : ''}
        </Typography>
      ) : null}

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => applied && load(applied)}>
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
          <AnalyticsKpiSummary summary={summary} costLabel={costLabel} currency={currency} />

          {summary?.comparison ? (
            <Alert severity="info">{summary.comparison.label}</Alert>
          ) : null}

          {summary?.funnel?.stages?.length ? (
            <Stack spacing={1} sx={{ contentVisibility: 'auto', containIntrinsicSize: '0 240px' }}>
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
            <Suspense fallback={<Skeleton variant="rounded" height={280} />}>
              <AnalyticsCharts summary={summary} currency={currency} costLabel={costLabel} />
            </Suspense>
          ) : null}
        </>
      )}
    </Stack>
  )
}
