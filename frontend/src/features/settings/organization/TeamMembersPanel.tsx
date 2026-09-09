import AddIcon from '@mui/icons-material/Add'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import {
  createInvitation,
  listInvitations,
  listMembers,
  patchMemberRole,
  removeMember,
  type OrgInvitationCreated,
  type OrgMember,
  type OrgRole,
} from '../../../api/tenancy'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import { useSnackbar } from '../../../components/SnackbarProvider'
import { useAuth } from '../../../auth/AuthProvider'

const ROLES: OrgRole[] = ['owner', 'admin', 'manager', 'staff', 'viewer']

type TeamMembersPanelProps = {
  canManage: boolean
}

export function TeamMembersPanel({ canManage }: TeamMembersPanelProps) {
  const { user } = useAuth()
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<OrgRole>('staff')
  const [createdInvite, setCreatedInvite] = useState<OrgInvitationCreated | null>(null)
  const [removeTarget, setRemoveTarget] = useState<OrgMember | null>(null)

  const membersQuery = useQuery({
    queryKey: queryKeys.tenancy.members,
    queryFn: listMembers,
    enabled: canManage,
  })
  const invitationsQuery = useQuery({
    queryKey: queryKeys.tenancy.invitations,
    queryFn: listInvitations,
    enabled: canManage,
  })

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: OrgRole }) =>
      patchMemberRole(userId, role),
    onSuccess: () => {
      notify('Role updated', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenancy.members })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Role update failed', 'error')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (member: OrgMember) => removeMember(member.user_id),
    onSuccess: () => {
      notify('Member removed', 'success')
      setRemoveTarget(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenancy.members })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Remove failed', 'error')
    },
  })

  const inviteMutation = useMutation({
    mutationFn: () =>
      createInvitation({ email: inviteEmail.trim(), role: inviteRole }),
    onSuccess: (row) => {
      notify('Invitation created', 'success')
      setCreatedInvite(row)
      setInviteEmail('')
      setInviteRole('staff')
      void queryClient.invalidateQueries({ queryKey: queryKeys.tenancy.invitations })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Invite failed', 'error')
    },
  })

  if (!canManage) {
    return (
      <Stack spacing={1}>
        <Typography variant="h3">Team</Typography>
        <Alert severity="info">
          Only owners and admins can manage members and invitations.
        </Alert>
      </Stack>
    )
  }

  const members = membersQuery.data ?? []
  const invitations = invitationsQuery.data ?? []
  const pending = invitations.filter((inv) => !inv.accepted_at)

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
      >
        <Typography variant="h3">Team members</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => {
            setCreatedInvite(null)
            setInviteOpen(true)
          }}
        >
          Invite
        </Button>
      </Stack>

      {membersQuery.isPending ? (
        <CircularProgress size={28} />
      ) : membersQuery.error ? (
        <Alert severity="error">
          {membersQuery.error instanceof ApiError
            ? membersQuery.error.message
            : 'Failed to load members'}
        </Alert>
      ) : (
        <TableContainer>
          <Table size="small" aria-label="Team members">
            <TableHead>
              <TableRow>
                <TableCell>Member</TableCell>
                <TableCell>Role</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {members.map((member) => {
                const label =
                  member.email || member.username || `User #${member.user_id}`
                const isSelf = user?.id === member.user_id
                return (
                  <TableRow key={member.user_id} hover>
                    <TableCell>
                      {label}
                      {isSelf ? ' (you)' : ''}
                    </TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={member.role}
                        disabled={roleMutation.isPending}
                        onChange={(e) =>
                          roleMutation.mutate({
                            userId: member.user_id,
                            role: e.target.value as OrgRole,
                          })
                        }
                        sx={{ minWidth: 140 }}
                        slotProps={{
                          htmlInput: { 'aria-label': `Role for ${label}` },
                        }}
                      >
                        {ROLES.map((role) => (
                          <MenuItem key={role} value={role}>
                            {role}
                          </MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="error"
                        disabled={isSelf}
                        onClick={() => setRemoveTarget(member)}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Stack spacing={1.5}>
        <Typography variant="h3">Pending invitations</Typography>
        {invitationsQuery.isPending ? (
          <CircularProgress size={24} />
        ) : pending.length === 0 ? (
          <Typography color="text.secondary">No pending invitations.</Typography>
        ) : (
          <TableContainer>
            <Table size="small" aria-label="Pending invitations">
              <TableHead>
                <TableRow>
                  <TableCell>Email</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Expires</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {pending.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell>{inv.email}</TableCell>
                    <TableCell>{inv.role}</TableCell>
                    <TableCell>
                      {new Date(inv.expires_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>

      <Dialog
        open={inviteOpen}
        onClose={() => !inviteMutation.isPending && setInviteOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Invite teammate</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {createdInvite ? (
              <Alert severity="success">
                Invitation created for {createdInvite.email}. Share this one-time token
                securely:
                <Typography
                  component="code"
                  sx={{ display: 'block', mt: 1, wordBreak: 'break-all' }}
                >
                  {createdInvite.token}
                </Typography>
              </Alert>
            ) : (
              <>
                <TextField
                  label="Email"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  fullWidth
                  required
                />
                <TextField
                  select
                  label="Role"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as OrgRole)}
                  fullWidth
                >
                  {ROLES.map((role) => (
                    <MenuItem key={role} value={role}>
                      {role}
                    </MenuItem>
                  ))}
                </TextField>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInviteOpen(false)} disabled={inviteMutation.isPending}>
            {createdInvite ? 'Close' : 'Cancel'}
          </Button>
          {!createdInvite ? (
            <Button
              variant="contained"
              disabled={!inviteEmail.trim() || inviteMutation.isPending}
              onClick={() => inviteMutation.mutate()}
            >
              Create invitation
            </Button>
          ) : null}
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title="Remove member?"
        description={
          removeTarget
            ? `${removeTarget.email || removeTarget.username || `User #${removeTarget.user_id}`} will lose access to this organization.`
            : undefined
        }
        confirmLabel="Remove"
        confirmColor="error"
        loading={removeMutation.isPending}
        onClose={() => {
          if (!removeMutation.isPending) setRemoveTarget(null)
        }}
        onConfirm={() => {
          if (removeTarget) removeMutation.mutate(removeTarget)
        }}
      />
    </Stack>
  )
}
