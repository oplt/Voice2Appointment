import type { Page, Route } from '@playwright/test'

const mockUser = {
  id: 1,
  username: 'e2e-user',
  email: 'e2e@example.com',
}

const mockDashboard = {
  appointments_today: 2,
  appointments_week: 5,
  upcoming: [],
  calendar_connected: true,
  recent_calls: 1,
  call_statistics: { calls_today: 1, recent_calls: 1, attention_today: 0, completion_rate: 1 },
  provider_status: { twilio: true, deepgram: true, calendar: true },
  operational: {
    calls_today: {
      value: 1,
      definition: 'Calls started in the local day.',
      window: 'local_day',
      timezone: 'UTC',
      drill_down: '/calls',
      exclusions: 'None',
    },
    attention_needed: {
      value: 0,
      definition: 'Needs follow-up.',
      window: 'local_day',
      timezone: 'UTC',
      drill_down: '/calls',
      exclusions: 'None',
    },
  },
  timezone: 'UTC',
  generated_at: '2026-09-08T12:00:00Z',
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

/** Cookie-session auth bootstrap + dashboard APIs for protected shells. */
export async function mockAuthenticatedApis(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const url = route.request().url()
    const method = route.request().method()

    if (url.includes('/api/v1/auth/me') && method === 'GET') {
      return json(route, mockUser)
    }
    if (url.includes('/api/v1/auth/csrf') || url.includes('/api/v1/auth/logout')) {
      return json(route, { message: 'ok' })
    }
    if (url.includes('/api/v1/calendars/status')) {
      return json(route, {
        connected: true,
        account_email: 'cal@example.com',
        calendar_id: 'primary',
        time_zone: 'UTC',
      })
    }
    if (url.includes('/api/v1/dashboard/summary')) {
      return json(route, mockDashboard)
    }
    if (url.includes('/api/v1/health') || url.includes('/health')) {
      return json(route, { status: 'ok' })
    }
    if (url.includes('/api/v1/users/me')) {
      return json(route, {
        ...mockUser,
        has_deepgram: true,
        has_twilio: true,
        twilio_auth_token_set: false,
      })
    }
    // Default: empty success for other GETs so shells do not crash.
    if (method === 'GET') {
      return json(route, {})
    }
    return json(route, { message: 'ok' })
  })
}
