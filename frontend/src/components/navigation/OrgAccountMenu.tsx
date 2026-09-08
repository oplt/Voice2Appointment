import AccountCircleOutlinedIcon from '@mui/icons-material/AccountCircleOutlined'
import BusinessOutlinedIcon from '@mui/icons-material/BusinessOutlined'
import LogoutIcon from '@mui/icons-material/Logout'
import SwapHorizOutlinedIcon from '@mui/icons-material/SwapHorizOutlined'
import Avatar from '@mui/material/Avatar'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/AuthProvider'
import { useSnackbar } from '../SnackbarProvider'

type OrgAccountMenuProps = {
  collapsed?: boolean
}

/** Tenant/organization profile menu — org switch, account, logout. */
export function OrgAccountMenu({ collapsed = false }: OrgAccountMenuProps) {
  const { user, logout } = useAuth()
  const { notify } = useSnackbar()
  const navigate = useNavigate()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const menuId = useId()
  const open = Boolean(anchorEl)

  const orgLabel = user?.username ? `${user.username}'s org` : 'Organization'
  const initial = (user?.username || user?.email || '?').slice(0, 1).toUpperCase()

  const handleLogout = async () => {
    setAnchorEl(null)
    await logout()
    notify('Signed out', 'info')
    navigate('/')
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
        <MenuItem disabled>
          <ListItemIcon>
            <SwapHorizOutlinedIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Switch organization" secondary="Coming soon" />
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
