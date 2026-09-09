import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined'
import MenuIcon from '@mui/icons-material/Menu'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { Link as RouterLink, Outlet, useLocation } from 'react-router-dom'

import { designTokens } from '../theme/tokens'
import { SkipLink } from './SkipLink'
import { ThemeModeToggle } from './ThemeModeToggle'
import { AppSidebar } from './navigation/AppSidebar'
import {
  NAV_COLLAPSED_WIDTH,
  NAV_COLLAPSE_STORAGE_KEY,
  NAV_EXPANDED_WIDTH,
  findActiveNavItem,
} from './navigation/navConfig'

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(NAV_COLLAPSE_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const active = findActiveNavItem(location.pathname)
  const desktopWidth = collapsed ? NAV_COLLAPSED_WIDTH : NAV_EXPANDED_WIDTH

  useEffect(() => {
    setCollapsed(readCollapsed())
  }, [])

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      const next = !current
      try {
        window.localStorage.setItem(NAV_COLLAPSE_STORAGE_KEY, next ? '1' : '0')
      } catch {
        /* ignore quota / private mode */
      }
      return next
    })
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <SkipLink />
      <AppBar
        position="fixed"
        component="header"
        sx={{
          width: { md: `calc(100% - ${desktopWidth}px)` },
          ml: { md: `${desktopWidth}px` },
          backgroundColor: designTokens.colors.frostedGlass,
          transition: `width ${designTokens.motion.duration} ${designTokens.motion.easing}, margin ${designTokens.motion.duration} ${designTokens.motion.easing}`,
        }}
      >
        <Toolbar sx={{ gap: 0.5 }}>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => setMobileOpen(true)}
            sx={{ mr: 1, display: { md: 'none' } }}
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            aria-controls="app-mobile-nav"
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h5" component="p" sx={{ flexGrow: 1, m: 0 }}>
            {active?.label ?? 'App'}
          </Typography>
          <ThemeModeToggle />
          <Tooltip title="Calendar">
            <IconButton
              color="inherit"
              component={RouterLink}
              to="/calendar"
              aria-label="Open calendar"
              size="small"
            >
              <CalendarMonthOutlinedIcon />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: desktopWidth }, flexShrink: { md: 0 } }} aria-label="Primary">
        <Drawer
          id="app-mobile-nav"
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: NAV_EXPANDED_WIDTH },
          }}
        >
          <AppSidebar
            collapsed={false}
            showCollapseControl={false}
            onNavigate={() => setMobileOpen(false)}
          />
        </Drawer>
        <Drawer
          variant="permanent"
          open
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              width: desktopWidth,
              boxSizing: 'border-box',
              borderRight: `1px solid ${designTokens.colors.cloudGray}`,
              overflowX: 'hidden',
              transition: `width ${designTokens.motion.duration} ${designTokens.motion.easing}`,
            },
          }}
        >
          <AppSidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
        </Drawer>
      </Box>

      <Box
        component="main"
        id="main-content"
        tabIndex={-1}
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${desktopWidth}px)` },
          p: { xs: 2, md: 3 },
          mt: 8,
          maxWidth: designTokens.layout.maxWidth,
          transition: `width ${designTokens.motion.duration} ${designTokens.motion.easing}`,
          outline: 'none',
        }}
      >
        <Outlet />
      </Box>
    </Box>
  )
}
