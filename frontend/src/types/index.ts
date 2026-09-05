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
  has_twilio?: boolean
  has_deepgram?: boolean
  image_file?: string
}

export type ApiErrorBody = {
  detail?: string | { msg: string }[] | { code?: string; message?: string }
  message?: string
}

export type AppointmentStatus = 'pending' | 'confirmed' | 'cancelled' | 'completed' | 'failed' | string

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
  provider_sync_status?: string
  transcript?: string | null
}

/** Non-sensitive fields returned by the paginated appointment list. */
export type AppointmentListItem = Pick<
  Appointment,
  'id' | 'summary' | 'start_datetime' | 'end_datetime' | 'timezone' | 'status'
> & {
  provider_sync_status: string
}

export type AppointmentCreate = {
  summary: string
  description?: string | null
  start_datetime: string
  end_datetime?: string | null
  timezone?: string
  status?: AppointmentStatus
  client_name?: string | null
  client_phone?: string | null
  client_email?: string | null
  notes?: string | null
}

export type AppointmentUpdate = Partial<AppointmentCreate>

/** Bounded delivery status — never includes recipient address or message body. */
export type NotificationDeliveryStatus = {
  id: number
  appointment_id: number
  kind: 'confirmation' | 'reminder' | string
  channel: string
  status: 'scheduled' | 'claimed' | 'sent' | 'failed' | 'skipped' | 'cancelled' | string
  error_code?: string | null
  sent_at?: string | null
  created_at?: string | null
}

export type CallSession = {
  id: number
  call_sid: string
  from_number?: string | null
  to_number?: string | null
  status: string
  started_at?: string | null
  ended_at?: string | null
  duration_seconds?: number | null
  outcome?: string | null
  terminal_reason?: string | null
  has_transcript?: boolean
  transcript_available?: boolean
  transcript_purged?: boolean
  direction?: string
  summary?: string
  transcript?: string | null
}

export type CallSessionList = {
  items: CallSession[]
  next_cursor?: string | null
  limit: number
}

/** @deprecated use CallSession */
export type RecentCall = CallSession

export type ProviderStatus = {
  twilio?: boolean
  deepgram?: boolean
  calendar?: boolean
}

export type DashboardKpi = {
  value: number | null
  definition: string
  window: string
  timezone: string
  drill_down: string
  exclusions: string
  numerator?: number
  denominator?: number
}

export type DashboardSummary = {
  appointments_today: number
  appointments_week: number
  upcoming: Appointment[]
  calendar_connected: boolean
  /** Count of call sessions in the last 7 local days. */
  recent_calls: number
  call_statistics?: {
    recent_calls?: number
    calls_today?: number
    completed_today?: number
    attention_today?: number
    completion_rate?: number | null
  }
  provider_status?: ProviderStatus
  integrations?: ProviderStatus & {
    twilio_last_synced_at?: string | null
    calendar_account?: string | null
  }
  operational?: {
    calls_today?: DashboardKpi
    completion_rate?: DashboardKpi
    appointments_booked_today?: DashboardKpi
    attention_needed?: DashboardKpi
    upcoming_appointments?: DashboardKpi
    appointments_today?: DashboardKpi
  }
  freshness?: {
    generated_at?: string
    source_synced_at?: string | null
    stale?: boolean
  }
  timezone?: string
  generated_at?: string
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
  title: string
  start: string
  end?: string
  allDay?: boolean
  url?: string | null
  description?: string | null
  location?: string | null
}

export type AvailabilitySlot = {
  start: string
  end: string
  available: boolean
}

export type BookingPolicy = {
  default_service_duration_minutes: number
  service_durations_minutes: Record<string, number>
  buffer_before_minutes: number
  buffer_after_minutes: number
  business_hours: Record<string, Array<{ start: string; end: string }>>
}

export type ProductPrefs = {
  notifications: {
    channel: 'email'
    confirmations_enabled: boolean
    reminders_enabled: boolean
    consent_at?: string | null
    quiet_hours_start?: string | null
    quiet_hours_end?: string | null
    reminder_hours_before: number
  }
  retention: {
    transcript_days: number
    recording_days: number
    legal_hold: boolean
  }
  transfer: {
    enabled: boolean
    destination_e164?: string | null
    business_hours_only: boolean
  }
  languages: {
    primary: string
    enabled: string[]
  }
}

export type ReadinessItem = {
  key: string
  label: string
  ok: boolean
  required: boolean
  fix_path: string
  detail: string
}

export type SetupReadiness = {
  ready: boolean
  items: ReadinessItem[]
  completed_required: number
  total_required: number
  test_call_hint: string
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
export type AnalyticsFunnelStage = {
  id: string
  label: string
  count: number
}

export type AnalyticsComparisonMetric = {
  current: number
  prior: number
  delta: number
  delta_pct: number | null
}

export type AnalyticsSummary = {
  total_calls: number
  total_duration: number
  avg_duration: number
  total_cost: number | null
  currency?: string | null
  reporting_currency?: string | null
  totals_by_currency?: Record<string, { calls: number; total_cost: number }>
  cost_over_time_by_currency?: Record<string, AnalyticsSeriesBlock>
  timezone?: string
  range?: { start: string | null; end: string | null }
  generated_at?: string | null
  source_synced_at?: string | null
  stale?: boolean
  stale_reason?: string | null
  cache_status?: 'hit' | 'miss' | string
  cache_age_seconds?: number | null
  truncated?: boolean
  phone_reidentification_allowed?: boolean
  calls_over_time: AnalyticsSeriesBlock
  duration_distribution: AnalyticsSeriesBlock
  cost_over_time: AnalyticsSeriesBlock
  top_numbers: AnalyticsSeriesBlock
  peak_hours_days: AnalyticsPeakHeatmap
  top_countries: AnalyticsCountry[]
  geo_country_counts: Array<{ country: string; iso3: string; calls: number }>
  funnel?: {
    stages: AnalyticsFunnelStage[]
    failure_categories: Array<{ code: string; count: number }>
    definitions?: Record<string, string>
    timezone?: string
    range?: { start: string; end: string }
  } | null
  comparison?: {
    range: { start: string; end: string }
    label: string
    total_calls: AnalyticsComparisonMetric
    total_duration: AnalyticsComparisonMetric
  } | null
}

export type UserProfileUpdate = {
  username?: string
  email?: string
  twilio_account_sid?: string | null
  twilio_auth_token?: string | null
  twilio_phone_number?: string | null
}
