import Alert from '@mui/material/Alert'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'

import { ApiError } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import {
  canManageOrganization,
  canWriteLocations,
  getActiveOrganization,
  listOrganizations,
} from '../../../api/tenancy'
import { AcceptInvitationPanel } from './AcceptInvitationPanel'
import { LocationsPanel } from './LocationsPanel'
import { TeamMembersPanel } from './TeamMembersPanel'

export function OrganizationPanel() {
  const orgsQuery = useQuery({
    queryKey: queryKeys.tenancy.organizations,
    queryFn: ({ signal }) => listOrganizations(signal),
  })
  const activeQuery = useQuery({
    queryKey: queryKeys.tenancy.active,
    queryFn: getActiveOrganization,
  })

  if (orgsQuery.isPending || activeQuery.isPending) {
    return <CircularProgress size={28} />
  }

  const orgError =
    orgsQuery.error instanceof ApiError
      ? orgsQuery.error.message
      : orgsQuery.error != null
        ? 'Failed to load organization'
        : null

  const active = orgsQuery.data?.find((org) => org.active)
  const role = active?.role ?? null
  const canManage = canManageOrganization(role)
  const canLocations = canWriteLocations(role)

  return (
    <Stack spacing={4}>
      <Stack spacing={1}>
        <Typography variant="h3">Organization</Typography>
        {orgError ? <Alert severity="error">{orgError}</Alert> : null}
        {activeQuery.data ? (
          <Typography variant="body1">
            {activeQuery.data.name}{' '}
            <Typography component="span" variant="body2" color="text.secondary">
              ({activeQuery.data.slug})
            </Typography>
          </Typography>
        ) : (
          <Alert severity="warning">No active organization.</Alert>
        )}
        {role ? (
          <Typography variant="body2" color="text.secondary">
            Your role: {role}
          </Typography>
        ) : null}
      </Stack>

      <LocationsPanel canWrite={canLocations} />
      <TeamMembersPanel canManage={canManage} />
      <AcceptInvitationPanel />
    </Stack>
  )
}
