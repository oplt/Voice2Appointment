# Booking policy

Each account has one tenant-scoped policy shared by HTTP appointment creation and
the voice calendar tools. Read or replace it with:

```text
GET /api/v1/users/me/booking-policy
PUT /api/v1/users/me/booking-policy
```

Example:

```json
{
  "default_service_duration_minutes": 30,
  "service_durations_minutes": {
    "Consultation": 45,
    "Follow-up": 20
  },
  "buffer_before_minutes": 10,
  "buffer_after_minutes": 10,
  "business_hours": {
    "monday": [{"start": "09:00", "end": "17:00"}],
    "tuesday": [{"start": "09:00", "end": "17:00"}]
  }
}
```

Day keys are lowercase English weekday names and times are local `HH:MM` values.
When `business_hours` is empty, hours are unrestricted for backward compatibility.
When it is non-empty, omitted days are closed. Named service matching ignores case;
its configured duration is enforced. If an appointment omits `end_datetime`, the
named duration or default duration supplies it.

Creates and time-changing updates reject out-of-hours slots with HTTP 422 and
tenant appointment conflicts, including buffer time, with HTTP 409. Voice booking
also checks the selected Google calendar before mutation.
