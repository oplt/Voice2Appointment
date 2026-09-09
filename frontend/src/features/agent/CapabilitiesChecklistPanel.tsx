import Alert from '@mui/material/Alert'
import Checkbox from '@mui/material/Checkbox'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { getIndustryProfile } from '../../api/knowledge'
import { queryKeys } from '../../api/queryKeys'
import { getSetupReadiness } from '../../api/users'
import type { GlobalFeatureFlags } from '../../types'

const KNOWN_TOOLS = [
  'search_catalog',
  'catalog_search',
  'get_price',
  'book_appointment',
  'create_appointment',
  'create_reservation',
  'appointment_availability',
  'restaurant_availability',
  'reschedule_appointment',
  'cancel_appointment',
  'cancel_reservation',
  'request_human_handoff',
  'answer_faq',
  'provide_product_information',
  'take_message',
  'check_order_status',
  'send_secure_link',
  'create_quote_request',
  'join_waitlist',
  'find_visit_types',
  'find_practitioners',
] as const

const CATALOG_KILL_SWITCH_TOOLS = new Set<string>([
  'catalog_search',
  'search_catalog',
  'get_price',
  'answer_faq',
  'provide_product_information',
  'take_message',
  'check_order_status',
  'send_secure_link',
  'create_quote_request',
])

const RESERVATION_KILL_SWITCH_TOOLS = new Set<string>([
  'book_appointment',
  'create_appointment',
  'create_reservation',
  'modify_reservation',
  'cancel_reservation',
  'restaurant_availability',
  'join_waitlist',
  'promote_waitlist',
])

const INDUSTRY_VOICE_TOOLS_KILL_SWITCH = new Set<string>([
  'find_visit_types',
  'find_practitioners',
  'find_salon_services',
  'find_available_staff',
  'find_salon_availability',
  'estimate_service_price',
  'book_salon_service',
  'modify_salon_booking',
])

function toolAllowedByGlobalFeatures(
  tool: string,
  features: GlobalFeatureFlags | null,
): boolean {
  if (!features) return true

  if (CATALOG_KILL_SWITCH_TOOLS.has(tool)) return features.catalog_domain
  if (RESERVATION_KILL_SWITCH_TOOLS.has(tool)) return features.reservation_domain
  if (INDUSTRY_VOICE_TOOLS_KILL_SWITCH.has(tool)) return features.industry_voice_tools

  return true
}

export function CapabilitiesChecklistPanel() {
  const [features, setFeatures] = useState<GlobalFeatureFlags | null>(null)

  useEffect(() => {
    getSetupReadiness()
      .then((data) => setFeatures(data.features ?? null))
      .catch(() => {
        // If readiness is unavailable, keep showing the capability checklist.
      })
  }, [])

  const profileQuery = useQuery({
    queryKey: queryKeys.industryProfile.current,
    queryFn: getIndustryProfile,
  })

  const enabledTools = (profileQuery.data?.enabled_tools ?? [])
    .map((t) => String(t))
    .filter(Boolean)
  const toolChecklist = Array.from(new Set([...KNOWN_TOOLS, ...enabledTools]))
    .filter((tool) => toolAllowedByGlobalFeatures(tool, features))
    .sort()

  return (
    <Stack spacing={2} sx={{ maxWidth: 560 }}>
      <Typography variant="h3">Capabilities / Enabled tools</Typography>
      <Typography variant="body1" color="text.secondary">
        Read-only checklist from the industry profile. Changing industry type resets the
        enabled tool set.
      </Typography>
      {profileQuery.isPending ? (
        <CircularProgress size={28} />
      ) : !profileQuery.data ? (
        <Alert severity="info">Assign an industry profile to see enabled tools.</Alert>
      ) : (
        <Stack spacing={0.5}>
          {toolChecklist.map((tool) => {
            const on = enabledTools.includes(tool)
            return (
              <FormControlLabel
                key={tool}
                control={<Checkbox checked={on} disabled />}
                label={tool.replaceAll('_', ' ')}
              />
            )
          })}
        </Stack>
      )}
    </Stack>
  )
}
