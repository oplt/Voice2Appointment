import { describe, expect, it } from 'vitest'

import {
  addCalendarDays,
  comparisonLabel,
  defaultFiltersFromMeta,
  filtersFromSearchParams,
  inclusiveDaySpan,
  parseStrictDate,
  priorPeriod,
  presetRange,
  tenantCalendarDate,
  validateFilters,
  type AnalyticsMeta,
} from './filters'

const meta: AnalyticsMeta = {
  timezone: 'America/Los_Angeles',
  today: '2026-03-10',
  default_range_days: 30,
  max_range_days: 90,
  default_range: { start: '2026-02-09', end: '2026-03-10' },
}

describe('analytics filter helpers', () => {
  it('rejects rolled-over calendar dates', () => {
    expect(parseStrictDate('2026-02-31')).toBeNull()
    expect(parseStrictDate('2026-02-28')).toEqual({ y: 2026, m: 2, d: 28 })
    expect(parseStrictDate('2024-02-29')).toEqual({ y: 2024, m: 2, d: 29 })
    expect(parseStrictDate('2025-02-29')).toBeNull()
  })

  it('uses server max range, not a hard-coded 366', () => {
    const ok = validateFilters(
      { start: '2026-01-01', end: '2026-04-02', compare: false },
      meta.max_range_days,
    )
    expect(ok?.range).toMatch(/90/)
    expect(
      validateFilters(
        { start: '2026-03-01', end: '2026-03-10', compare: false },
        meta.max_range_days,
      ),
    ).toBeNull()
  })

  it('flags reversed and malformed ranges with field errors', () => {
    expect(
      validateFilters({ start: '2026-03-10', end: '2026-03-01', compare: false }, 366)?.range,
    ).toBeTruthy()
    const bad = validateFilters({ start: '2026-02-31', end: '2026-03-01', compare: false }, 366)
    expect(bad?.start).toBeTruthy()
  })

  it('builds presets from tenant today, not browser local day', () => {
    const range = presetRange(meta, 7)
    expect(range).toEqual({ start: '2026-03-04', end: '2026-03-10' })
    expect(defaultFiltersFromMeta(meta)).toEqual({
      start: '2026-02-09',
      end: '2026-03-10',
      compare: false,
    })
  })

  it('differs tenant today from browser-local near midnight boundaries', () => {
    // 2026-03-11 06:30 UTC → still 2026-03-10 in LA, already 2026-03-11 in Brussels.
    const instant = new Date('2026-03-11T06:30:00Z')
    expect(tenantCalendarDate('America/Los_Angeles', instant)).toBe('2026-03-10')
    expect(tenantCalendarDate('Europe/Brussels', instant)).toBe('2026-03-11')
  })

  it('keeps calendar math stable across spring/fall DST transitions', () => {
    // US spring forward 2026-03-08; fall back 2026-11-01.
    expect(addCalendarDays('2026-03-07', 2)).toBe('2026-03-09')
    expect(addCalendarDays('2026-10-31', 2)).toBe('2026-11-02')
    expect(inclusiveDaySpan('2026-03-07', '2026-03-09')).toBe(3)
    expect(tenantCalendarDate('America/New_York', new Date('2026-03-08T06:30:00Z'))).toBe(
      '2026-03-08',
    )
    expect(tenantCalendarDate('America/New_York', new Date('2026-11-01T05:30:00Z'))).toBe(
      '2026-11-01',
    )
  })

  it('matches backend prior-period comparison math and labels', () => {
    expect(priorPeriod('2026-03-01', '2026-03-10')).toEqual({
      start: '2026-02-19',
      end: '2026-02-28',
    })
    expect(comparisonLabel('2026-03-01', '2026-03-10')).toBe(
      'Prior 10 day(s): 2026-02-19 → 2026-02-28',
    )
  })

  it('parses URL state without fetching invalid values as applied defaults blindly', () => {
    const params = new URLSearchParams('start=2026-02-31&end=2026-03-01&compare=1')
    const parsed = filtersFromSearchParams(params, defaultFiltersFromMeta(meta))
    expect(parsed.explicit).toBe(true)
    expect(parsed.filters.compare).toBe(true)
    expect(validateFilters(parsed.filters, meta.max_range_days)?.start).toBeTruthy()
  })
})
