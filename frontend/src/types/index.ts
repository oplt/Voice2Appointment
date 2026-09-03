export type User = {
  id: number
  username: string
  email: string
}

/** Profile returned by GET/PATCH /api/v1/users/me (secrets masked). */
export type UserProfile = User & {
  twilio_account_sid?: string | null
  /** True when a token is stored; never the raw secret. */
  twilio_auth_token_set?: boolean
  twilio_phone_number?: string | null
  deepgram_api_key_set?: boolean
  config_json?: string | null
  calendar_id?: string | null
  time_zone?: string | null
}

export type ApiErrorBody = {
  detail?: string | { msg: string }[]
  message?: string
}

export type AppointmentStatus = 'pending' | 'confirmed' | 'cancelled' | 'completed' | string

export type Appointment = {
  id: number
  summary: string
  description?: string | null
  start_datetime: string
  end_datetime: string
  timezone: string
  status: AppointmentStatus
  client_name?: string | null
  client_phone?: string | null
  client_email?: string | null
  notes?: string | null
  google_calendar_event_id?: string | null
  google_calendar_link?: string | null
}

export type AppointmentCreate = {
  summary: string
  description?: string | null
  start_datetime: string
  end_datetime: string
  timezone?: string
  status?: AppointmentStatus
  client_name?: string | null
  client_phone?: string | null
  client_email?: string | null
  notes?: string | null
}

export type AppointmentUpdate = Partial<AppointmentCreate>

export type RecentCall = {
  id?: number
  call_sid: string
  from_number?: string | null
  to_number?: string | null
  status?: string | null
  started_at?: string | null
  duration_seconds?: number | null
}

export type ProviderStatus = {
  twilio?: boolean
  deepgram?: boolean
  calendar?: boolean
}

export type DashboardSummary = {
  appointments_today: number
  appointments_week: number
  upcoming: Appointment[]
  calendar_connected: boolean
  call_statistics?: Record<string, number | string | null>
  recent_calls?: RecentCall[]
  provider_status?: ProviderStatus
  embedded_link?: string | null
}

export type CalendarStatus = {
  connected: boolean
  provider?: string | null
  account_email?: string | null
  calendar_id?: string | null
  time_zone?: string | null
  embedded_link?: string | null
  status?: string | null
}

export type CalendarEvent = {
  id: string
  summary: string
  start: string
  end: string
  html_link?: string | null
}

export type AvailabilitySlot = {
  start: string
  end: string
  available: boolean
}

export type AnalyticsSeriesBlock = {
  labels: string[]
  values: number[]
}

export type AnalyticsCountry = {
  country: string
  iso3: string
  calls: number
  total_cost?: number
  avg_duration_min?: number
}

export type AnalyticsPeakHeatmap = {
  weekdays: string[]
  hours: number[]
  matrix: number[][]
}

/** Compact JSON from GET /api/v1/analytics/summary (charts render in-browser). */
export type AnalyticsSummary = {
  total_calls: number
  total_duration: number
  avg_duration: number
  total_cost: number
  calls_over_time: AnalyticsSeriesBlock
  duration_distribution: AnalyticsSeriesBlock
  cost_over_time: AnalyticsSeriesBlock
  top_numbers: AnalyticsSeriesBlock
  peak_hours_days: AnalyticsPeakHeatmap
  top_countries: AnalyticsCountry[]
  geo_country_counts: Array<{ country: string; iso3: string; calls: number }>
}

export type UserProfileUpdate = {
  username?: string
  email?: string
  twilio_account_sid?: string | null
  twilio_auth_token?: string | null
  twilio_phone_number?: string | null
  deepgram_api_key?: string | null
  config_json?: string | null
  calendar_id?: string | null
  time_zone?: string | null
}
