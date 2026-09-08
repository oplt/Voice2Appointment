import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import EventOutlinedIcon from '@mui/icons-material/EventOutlined'
import ExtensionOutlinedIcon from '@mui/icons-material/ExtensionOutlined'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import MeetingRoomOutlinedIcon from '@mui/icons-material/MeetingRoomOutlined'
import PeopleOutlinedIcon from '@mui/icons-material/PeopleOutlined'
import PhoneInTalkOutlinedIcon from '@mui/icons-material/PhoneInTalkOutlined'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import SmartToyOutlinedIcon from '@mui/icons-material/SmartToyOutlined'
import SpaceDashboardOutlinedIcon from '@mui/icons-material/SpaceDashboardOutlined'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import ListSubheader from '@mui/material/ListSubheader'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

import { designTokens } from '../../theme/tokens'
import { OrgAccountMenu } from './OrgAccountMenu'
import {
  NAV_COLLAPSED_WIDTH,
  NAV_EXPANDED_WIDTH,
  NAV_SECTIONS,
  pathMatchesItem,
  type NavItem,
} from './navConfig'

const ICONS: Record<string, ReactNode> = {
  dashboard: <SpaceDashboardOutlinedIcon fontSize="small" />,
  bookings: <EventOutlinedIcon fontSize="small" />,
  calls: <PhoneInTalkOutlinedIcon fontSize="small" />,
  catalog: <Inventory2OutlinedIcon fontSize="small" />,
  resources: <MeetingRoomOutlinedIcon fontSize="small" />,
  customers: <PeopleOutlinedIcon fontSize="small" />,
  analytics: <AnalyticsOutlinedIcon fontSize="small" />,
  agent: <SmartToyOutlinedIcon fontSize="small" />,
  integrations: <ExtensionOutlinedIcon fontSize="small" />,
  settings: <SettingsOutlinedIcon fontSize="small" />,
}

type AppSidebarProps = {
  collapsed: boolean
  onToggleCollapsed?: () => void
  onNavigate?: () => void
  showCollapseControl?: boolean
}

function NavLinkButton({
  item,
  collapsed,
  selected,
  onNavigate,
}: {
  item: NavItem
  collapsed: boolean
  selected: boolean
  onNavigate?: () => void
}) {
  const icon = ICONS[item.id] ?? <EventOutlinedIcon fontSize="small" />
  const button = (
    <ListItemButton
      component={RouterLink}
      to={item.to}
      selected={selected}
      onClick={onNavigate}
      aria-current={selected ? 'page' : undefined}
      sx={{
        borderRadius: 1,
        mb: 0.25,
        minHeight: 44,
        justifyContent: collapsed ? 'center' : 'flex-start',
        px: collapsed ? 1 : 1.5,
      }}
    >
      <ListItemIcon
        sx={{
          minWidth: collapsed ? 0 : 36,
          color: selected ? 'primary.main' : 'text.secondary',
          justifyContent: 'center',
        }}
      >
        {icon}
      </ListItemIcon>
      {!collapsed ? (
        <ListItemText
          primary={item.label}
          sx={{ '& .MuiListItemText-primary': { fontSize: 14, fontWeight: 500 } }}
        />
      ) : null}
    </ListItemButton>
  )

  if (collapsed) {
    return (
      <ListItem disablePadding sx={{ display: 'block' }}>
        <Tooltip title={item.label} placement="right">
          {button}
        </Tooltip>
      </ListItem>
    )
  }
  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      {button}
    </ListItem>
  )
}

export function AppSidebar({
  collapsed,
  onToggleCollapsed,
  onNavigate,
  showCollapseControl = true,
}: AppSidebarProps) {
  const location = useLocation()
  const width = collapsed ? NAV_COLLAPSED_WIDTH : NAV_EXPANDED_WIDTH

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width,
        transition: `width ${designTokens.motion.duration} ${designTokens.motion.easing}`,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          px: collapsed ? 1 : 2,
          py: 1.5,
          minHeight: 64,
          gap: 1,
        }}
      >
        {!collapsed ? (
          <Typography
            variant="h3"
            component={RouterLink}
            to="/dashboard"
            onClick={onNavigate}
            sx={{
              color: 'text.primary',
              textDecoration: 'none',
              fontSize: 16,
              fontWeight: 500,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            Voice2Appointment
          </Typography>
        ) : (
          <Typography
            component={RouterLink}
            to="/dashboard"
            onClick={onNavigate}
            aria-label="Voice2Appointment home"
            sx={{
              color: 'text.primary',
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            V2
          </Typography>
        )}
        {showCollapseControl && onToggleCollapsed ? (
          <IconButton
            size="small"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            sx={{ display: { xs: 'none', md: 'inline-flex' } }}
          >
            {collapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
          </IconButton>
        ) : null}
      </Box>
      <Divider />

      <Box sx={{ flex: 1, overflowY: 'auto', px: 1, py: 1 }}>
        {NAV_SECTIONS.map((section) => (
          <List
            key={section.id}
            dense
            subheader={
              collapsed ? undefined : (
                <ListSubheader
                  component="li"
                  disableSticky
                  sx={{
                    bgcolor: 'transparent',
                    lineHeight: 2,
                    px: 1.5,
                    fontSize: 11,
                    fontWeight: 500,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    color: 'text.secondary',
                  }}
                >
                  {section.label}
                </ListSubheader>
              )
            }
            sx={{ mb: 1 }}
          >
            {section.items.map((item) => (
              <NavLinkButton
                key={item.id}
                item={item}
                collapsed={collapsed}
                selected={pathMatchesItem(location.pathname, item)}
                onNavigate={onNavigate}
              />
            ))}
          </List>
        ))}
      </Box>

      <Divider />
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          px: collapsed ? 1 : 1.5,
          py: 1.5,
          gap: 0.5,
          minHeight: 64,
        }}
      >
        <OrgAccountMenu collapsed={collapsed} />
      </Box>
    </Box>
  )
}
