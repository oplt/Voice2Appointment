import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined'
import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined'
import EventOutlinedIcon from '@mui/icons-material/EventOutlined'
import LogoutIcon from '@mui/icons-material/Logout'
import MenuIcon from '@mui/icons-material/Menu'
import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import SpaceDashboardOutlinedIcon from '@mui/icons-material/SpaceDashboardOutlined'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import { Link as RouterLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'
import { useSnackbar } from './SnackbarProvider'
import { designTokens } from '../theme/tokens'

const DRAWER_WIDTH = 260

const navItems = [
  { label: 'Dashboard', to: '/dashboard', icon: <SpaceDashboardOutlinedIcon /> },
  { label: 'Calendar', to: '/calendar', icon: <CalendarMonthOutlinedIcon /> },
  { label: 'Appointments', to: '/appointments', icon: <EventOutlinedIcon /> },
  { label: 'Calls', to: '/calls', icon: <PhoneInTalkOutlinedIcon /> },
  { label: 'Analytics', to: '/analytics', icon: <AnalyticsOutlinedIcon /> },
  { label: 'Settings', to: '/settings', icon: <SettingsOutlinedIcon /> },
] as const

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { notify } = useSnackbar()

  const handleLogout = async () => {
    await logout()
    notify('Signed out', 'info')
    navigate('/')
  }

  const drawer = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar>
        <Typography variant="h3" component={RouterLink} to="/dashboard" sx={{ color: 'text.primary', textDecoration: 'none' }}>
          Voice2Appointment
        </Typography>
      </Toolbar>
      <Divider />
      <List sx={{ flex: 1, px: 1 }}>
        {navItems.map((item) => {
          const selected =
            location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
          return (
            <ListItemButton
              key={item.to}
              component={RouterLink}
              to={item.to}
              selected={selected}
              onClick={() => setMobileOpen(false)}
              sx={{ borderRadius: 1, mb: 0.5 }}
            >
              <ListItemIcon sx={{ minWidth: 40, color: selected ? 'primary.main' : 'text.secondary' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          )
        })}
      </List>
      <Divider />
      <List sx={{ px: 1, pb: 1 }}>
        <ListItemButton onClick={handleLogout} sx={{ borderRadius: 1 }}>
          <ListItemIcon sx={{ minWidth: 40 }}>
            <LogoutIcon />
          </ListItemIcon>
          <ListItemText primary="Logout" secondary={user?.email} />
        </ListItemButton>
      </List>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
          backgroundColor: designTokens.colors.frostedGlass,
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => setMobileOpen(true)}
            sx={{ mr: 1, display: { md: 'none' } }}
            aria-label="Open navigation"
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h5" sx={{ flexGrow: 1 }}>
            {navItems.find((item) => location.pathname.startsWith(item.to))?.label ?? 'App'}
          </Typography>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          open
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
              boxSizing: 'border-box',
              borderRight: `1px solid ${designTokens.colors.cloudGray}`,
            },
          }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          p: { xs: 2, md: 3 },
          mt: 8,
          maxWidth: designTokens.layout.maxWidth,
        }}
      >
        <Outlet />
      </Box>
    </Box>
  )
}
