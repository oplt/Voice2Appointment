/** Tenant-local analytics filter helpers (calendar days, no JS Date rollover). */

export type AnalyticsFilterState = {
  start: string
  end: string
  compare: boolean
}

export type AnalyticsMeta = {
  timezone: string
  today: string
  default_range_days: number
  max_range_days: number
  default_range: { start: string; end: string }
}

export type FilterFieldErrors = {
  start?: string
  end?: string
  range?: string
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** Parse YYYY-MM-DD as a real calendar date; reject rollover (e.g. 2026-02-31). */
export function parseStrictDate(value: string): { y: number; m: number; d: number } | null {
  const match = ISO_DATE.exec(value.trim())
  if (!match) return null
  const y = Number(match[1])
  const m = Number(match[2])
  const d = Number(match[3])
  if (m < 1 || m > 12 || d < 1 || d > 31) return null
  const probe = new Date(Date.UTC(y, m - 1, d))
  if (
    probe.getUTCFullYear() !== y ||
    probe.getUTCMonth() !== m - 1 ||
    probe.getUTCDate() !== d
  ) {
    return null
  }
  return { y, m, d }
}

/** Calendar-day arithmetic in UTC noon space (DST-safe for date-only values). */
export function addCalendarDays(isoDate: string, deltaDays: number): string {
  const parsed = parseStrictDate(isoDate)
  if (!parsed) throw new Error(`Invalid date: ${isoDate}`)
  const dt = new Date(Date.UTC(parsed.y, parsed.m - 1, parsed.d))
  dt.setUTCDate(dt.getUTCDate() + deltaDays)
  const y = dt.getUTCFullYear()
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const d = String(dt.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function inclusiveDaySpan(start: string, end: string): number | null {
  const a = parseStrictDate(start)
  const b = parseStrictDate(end)
  if (!a || !b) return null
  const startMs = Date.UTC(a.y, a.m - 1, a.d)
  const endMs = Date.UTC(b.y, b.m - 1, b.d)
  return Math.floor((endMs - startMs) / 86_400_000) + 1
}

/** Equal-length prior period immediately before start (matches backend prior_period). */
export function priorPeriod(start: string, end: string): { start: string; end: string } | null {
  const span = inclusiveDaySpan(start, end)
  if (span == null || span < 1) return null
  const priorEnd = addCalendarDays(start, -1)
  const priorStart = addCalendarDays(priorEnd, -(span - 1))
  return { start: priorStart, end: priorEnd }
}

export function comparisonLabel(start: string, end: string): string | null {
  const prior = priorPeriod(start, end)
  const span = inclusiveDaySpan(start, end)
  if (!prior || span == null) return null
  return `Prior ${span} day(s): ${prior.start} → ${prior.end}`
}

/** Local calendar YYYY-MM-DD for an instant in an IANA timezone. */
export function tenantCalendarDate(timeZone: string, instant: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(instant)
  const y = parts.find((p) => p.type === 'year')?.value
  const m = parts.find((p) => p.type === 'month')?.value
  const d = parts.find((p) => p.type === 'day')?.value
  if (!y || !m || !d) throw new Error(`Cannot format date in ${timeZone}`)
  return `${y}-${m}-${d}`
}

export function defaultFiltersFromMeta(meta: AnalyticsMeta): AnalyticsFilterState {
  return {
    start: meta.default_range.start,
    end: meta.default_range.end,
    compare: false,
  }
}

export function presetRange(
  meta: AnalyticsMeta,
  days: number,
  instant: Date = new Date(),
): Pick<AnalyticsFilterState, 'start' | 'end'> {
  const end = meta.today || tenantCalendarDate(meta.timezone, instant)
  const start = addCalendarDays(end, -(days - 1))
  return { start, end }
}

export function validateFilters(
  next: AnalyticsFilterState,
  maxRangeDays: number,
): FilterFieldErrors | null {
  const errors: FilterFieldErrors = {}
  const start = parseStrictDate(next.start)
  const end = parseStrictDate(next.end)
  if (!start) errors.start = 'Enter a valid start date (YYYY-MM-DD).'
  if (!end) errors.end = 'Enter a valid end date (YYYY-MM-DD).'
  if (start && end) {
    const span = inclusiveDaySpan(next.start, next.end)
    if (span == null || span < 1) {
      errors.range = 'Start date must be on or before end date.'
    } else if (span > maxRangeDays) {
      errors.range = `Range cannot exceed ${maxRangeDays} days.`
    }
  }
  return Object.keys(errors).length ? errors : null
}

export function filtersEqual(a: AnalyticsFilterState, b: AnalyticsFilterState): boolean {
  return a.start === b.start && a.end === b.end && a.compare === b.compare
}

export function filterKey(filters: AnalyticsFilterState): string {
  return `${filters.start}|${filters.end}|${filters.compare ? '1' : '0'}`
}

export function filtersFromSearchParams(
  params: URLSearchParams,
  defaults: AnalyticsFilterState,
): { filters: AnalyticsFilterState; explicit: boolean } {
  const hasStart = params.has('start')
  const hasEnd = params.has('end')
  const hasCompare = params.has('compare')
  const explicit = hasStart || hasEnd || hasCompare
  return {
    explicit,
    filters: {
      start: params.get('start') || defaults.start,
      end: params.get('end') || defaults.end,
      compare: params.get('compare') === '1' || params.get('compare') === 'true',
    },
  }
}

export function filtersToSearchParams(filters: AnalyticsFilterState): URLSearchParams {
  const params = new URLSearchParams()
  params.set('start', filters.start)
  params.set('end', filters.end)
  if (filters.compare) params.set('compare', '1')
  return params
}
