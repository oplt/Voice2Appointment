import CalendarMonthOutlinedIcon from '@mui/icons-material/CalendarMonthOutlined'
import EmailOutlinedIcon from '@mui/icons-material/EmailOutlined'
import PhoneOutlinedIcon from '@mui/icons-material/PhoneOutlined'
import Alert from '@mui/material/Alert'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import { useLocation } from 'react-router-dom'

import { PageHeader } from '../../components/PageHeader'
import { CalendarIntegrationPanel } from './CalendarIntegrationPanel'
import { TelephonyIntegrationPanel } from './TelephonyIntegrationPanel'

export function IntegrationsView() {
  const location = useLocation()
  const [tab, setTab] = useState(() =>
    new URLSearchParams(location.search).has('google') ? 1 : 0,
  )

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Integrations"
        subtitle="Phone, calendar, and email. Credentials stay backend-only."
      />
      <Tabs
        value={tab}
        onChange={(_, value: number) => setTab(value)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Integration sections"
      >
        <Tab icon={<PhoneOutlinedIcon />} iconPosition="start" label="Phone" />
        <Tab icon={<CalendarMonthOutlinedIcon />} iconPosition="start" label="Calendar" />
        <Tab icon={<EmailOutlinedIcon />} iconPosition="start" label="Email" />
      </Tabs>
      {tab === 0 ? <TelephonyIntegrationPanel /> : null}
      {tab === 1 ? <CalendarIntegrationPanel /> : null}
      {tab === 2 ? (
        <Stack spacing={2} sx={{ maxWidth: 480 }}>
          <Typography variant="h3">Email</Typography>
          <Typography variant="body1" color="text.secondary">
            Transactional email uses the platform SMTP/provider configuration.
          </Typography>
          <Alert severity="info">
            Per-organization email branding and custom SMTP arrive in a later phase.
          </Alert>
        </Stack>
      ) : null}
    </Stack>
  )
}
