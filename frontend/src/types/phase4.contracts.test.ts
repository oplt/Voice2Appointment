import { describe, expect, it } from 'vitest'

import type { CalendarEvent, CallSession, CallSessionList, DashboardSummary } from '../types'

describe('phase 4 frontend contracts', () => {
  it('maps calendar events with title/url/allDay (not summary/html_link)', () => {
    const event: CalendarEvent = {
      id: 'evt-1',
      title: 'Consult',
      start: '2026-09-03T10:00:00Z',
      end: '2026-09-03T10:30:00Z',
      allDay: false,
      url: 'https://calendar.example/event/1',
    }
    expect(event.title).toBe('Consult')
    expect(event.url).toMatch(/^https:/)
    expect('summary' in event).toBe(false)
    expect('html_link' in event).toBe(false)
  })

  it('treats recent_calls as a count and calls list as paginated items', () => {
    const summary: DashboardSummary = {
      appointments_today: 1,
      appointments_week: 2,
      upcoming: [],
      calendar_connected: true,
      recent_calls: 4,
      call_statistics: { calls_today: 1, recent_calls: 4 },
      provider_status: { twilio: true, deepgram: true, calendar: true },
      timezone: 'UTC',
      generated_at: '2026-09-03T12:00:00Z',
    }
    expect(typeof summary.recent_calls).toBe('number')
    expect(Array.isArray(summary.recent_calls)).toBe(false)

    const page: CallSessionList = {
      items: [
        {
          id: 1,
          call_sid: 'CA1',
          status: 'completed',
          has_transcript: true,
        } satisfies CallSession,
      ],
      next_cursor: 'abc',
      limit: 50,
    }
    expect(page.items).toHaveLength(1)
    expect(page.items[0]?.transcript).toBeUndefined()
  })
})
