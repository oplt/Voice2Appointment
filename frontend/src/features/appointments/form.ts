import type { Appointment, AppointmentCreate } from '../../types'

export type AppointmentFormState = {
  summary: string
  description: string
  start_datetime: string
  end_datetime: string
  timezone: string
  status: string
  client_name: string
  client_phone: string
  client_email: string
  notes: string
}

export function emptyAppointmentForm(): AppointmentFormState {
  return {
    summary: '',
    description: '',
    start_datetime: '',
    end_datetime: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    status: 'pending',
    client_name: '',
    client_phone: '',
    client_email: '',
    notes: '',
  }
}

function toLocalInputValue(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function appointmentForm(item: Appointment): AppointmentFormState {
  return {
    summary: item.summary,
    description: item.description ?? '',
    start_datetime: toLocalInputValue(item.start_datetime),
    end_datetime: toLocalInputValue(item.end_datetime),
    timezone: item.timezone || 'UTC',
    status: item.status || 'pending',
    client_name: item.client_name ?? '',
    client_phone: item.client_phone ?? '',
    client_email: item.client_email ?? '',
    notes: item.notes ?? '',
  }
}

export function appointmentPayload(form: AppointmentFormState): AppointmentCreate {
  const toIso = (value: string) => (value ? new Date(value).toISOString() : '')
  return {
    summary: form.summary.trim(),
    description: form.description.trim() || null,
    start_datetime: toIso(form.start_datetime),
    end_datetime: toIso(form.end_datetime),
    timezone: form.timezone.trim() || 'UTC',
    status: form.status,
    client_name: form.client_name.trim() || null,
    client_phone: form.client_phone.trim() || null,
    client_email: form.client_email.trim() || null,
    notes: form.notes.trim() || null,
  }
}

export function formatAppointmentTime(iso: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}
