import Stack from '@mui/material/Stack'
import { useSearchParams } from 'react-router-dom'

import { PageHeader } from '../components/PageHeader'
import { AcceptInvitationPanel } from '../features/settings/organization/AcceptInvitationPanel'

export function InviteAcceptPage() {
  const [params] = useSearchParams()
  const token = (params.get('token') || params.get('t') || '').trim()

  return (
    <Stack spacing={3} sx={{ maxWidth: 560, mx: 'auto', py: 4, px: 2 }}>
      <PageHeader
        title="Join organization"
        subtitle="Accept a team invitation with the token from your invite email or admin."
      />
      <AcceptInvitationPanel initialToken={token} redirectOnSuccess />
    </Stack>
  )
}
