import AccountCircleOutlinedIcon from '@mui/icons-material/AccountCircleOutlined'
import BusinessOutlinedIcon from '@mui/icons-material/BusinessOutlined'
import CheckOutlinedIcon from '@mui/icons-material/CheckOutlined'
import ExtensionOutlinedIcon from '@mui/icons-material/ExtensionOutlined'
import LogoutIcon from '@mui/icons-material/Logout'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import SwapHorizOutlinedIcon from '@mui/icons-material/SwapHorizOutlined'
import Avatar from '@mui/material/Avatar'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/client'
import {
  activateOrganization,
  listOrganizations,
  type OrganizationSummary,
} from '../../api/tenancy'
import { useAuth } from '../../auth/AuthProvider'
import { useSnackbar } from '../SnackbarProvider'

type OrgAccountMenuProps = {
  collapsed?: boolean
}

/** Tenant/organization profile menu — org switch, account, logout. */
export function OrgAccountMenu({ collapsed = false }: OrgAccountMenuProps) {
  const { user, logout, retryBootstrap } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [orgs, setOrgs] = useState<OrganizationSummary[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [switchingId, setSwitchingId] = useState<number | null>(null)
  const [showSwitcher, setShowSwitcher] = useState(false)
  const menuId = useId()
  const open = Boolean(anchorEl)

  const activeOrg = orgs.find((org) => org.active)
  const orgLabel = activeOrg?.name || (user?.username ? `${user.username}'s org` : 'Organization')
  const initial = (user?.username || user?.email || '?').slice(0, 1).toUpperCase()

  useEffect(() => {
    if (!open) {
      setShowSwitcher(false)
      return
    }
    let cancelled = false
    setLoadingOrgs(true)
    listOrganizations()
      .then((rows) => {
        if (!cancelled) setOrgs(rows)
      })
      .catch(() => {
        if (!cancelled) setOrgs([])
      })
      .finally(() => {
        if (!cancelled) setLoadingOrgs(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const handleLogout = async () => {
    setAnchorEl(null)
    await logout()
    notify('Signed out', 'info')
    navigate('/')
  }

  const handleActivate = async (organizationId: number) => {
    if (switchingId != null) return
    const current = orgs.find((org) => org.active)
    if (current?.id === organizationId) {
      setShowSwitcher(false)
      return
    }
    setSwitchingId(organizationId)
    try {
      await activateOrganization(organizationId)
      notify('Organization switched', 'success')
      setAnchorEl(null)
      retryBootstrap()
      navigate(0)
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : 'Unable to switch organization'
      notify(message, 'error')
    } finally {
      setSwitchingId(null)
    }
  }

  const trigger = (
    <IconButton
      onClick={(event) => setAnchorEl(event.currentTarget)}
      aria-controls={open ? menuId : undefined}
      aria-haspopup="true"
      aria-expanded={open ? 'true' : undefined}
      aria-label="Organization and account menu"
      size="small"
      sx={{ p: 0.5 }}
    >
      <Avatar
        sx={{
          width: collapsed ? 36 : 32,
          height: collapsed ? 36 : 32,
          bgcolor: 'primary.main',
          fontSize: 14,
          fontWeight: 500,
        }}
      >
        {initial}
      </Avatar>
    </IconButton>
  )

  return (
    <>
      {collapsed ? (
        <Tooltip title={orgLabel} placement="right">
          {trigger}
        </Tooltip>
      ) : (
        trigger
      )}
      {!collapsed ? (
        <Typography
          variant="body2"
          noWrap
          sx={{ ml: 1, flex: 1, minWidth: 0, cursor: 'pointer' }}
          onClick={(event) => setAnchorEl(event.currentTarget as HTMLElement)}
        >
          {orgLabel}
        </Typography>
      ) : null}

      <Menu
        id={menuId}
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'top', horizontal: collapsed ? 'right' : 'left' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        slotProps={{ paper: { sx: { minWidth: 220 } } }}
      >
        <MenuItem disabled>
          <ListItemIcon>
            <BusinessOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={orgLabel}
            secondary={user?.email}
            slotProps={{
              primary: { noWrap: true },
              secondary: { noWrap: true },
            }}
          />
        </MenuItem>
        <Divider />
        {!showSwitcher ? (
          <MenuItem
            onClick={() => setShowSwitcher(true)}
            disabled={loadingOrgs || orgs.length <= 1}
          >
            <ListItemIcon>
              {loadingOrgs ? (
                <CircularProgress size={16} />
              ) : (
                <SwapHorizOutlinedIcon fontSize="small" />
              )}
            </ListItemIcon>
            <ListItemText
              primary="Switch organization"
              secondary={
                orgs.length <= 1 && !loadingOrgs ? 'Only one organization' : undefined
              }
            />
          </MenuItem>
        ) : (
          orgs.map((org) => (
            <MenuItem
              key={org.id}
              onClick={() => void handleActivate(org.id)}
              disabled={switchingId != null}
            >
              <ListItemIcon>
                {switchingId === org.id ? (
                  <CircularProgress size={16} />
                ) : org.active ? (
                  <CheckOutlinedIcon fontSize="small" color="primary" />
                ) : (
                  <BusinessOutlinedIcon fontSize="small" />
                )}
              </ListItemIcon>
              <ListItemText primary={org.name} secondary={org.role} />
            </MenuItem>
          ))
        )}
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            navigate('/integrations')
          }}
        >
          <ListItemIcon>
            <ExtensionOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Integrations" />
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            navigate('/settings')
          }}
        >
          <ListItemIcon>
            <SettingsOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Settings" />
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            navigate('/settings')
          }}
        >
          <ListItemIcon>
            <AccountCircleOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Account" />
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => void handleLogout()}>
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Log out" />
        </MenuItem>
      </Menu>
    </>
  )
}
