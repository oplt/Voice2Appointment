import BusinessOutlinedIcon from '@mui/icons-material/BusinessOutlined'
import NotificationsOutlinedIcon from '@mui/icons-material/NotificationsOutlined'
import PersonOutlinedIcon from '@mui/icons-material/PersonOutlined'
import PolicyOutlinedIcon from '@mui/icons-material/PolicyOutlined'
import ReceiptLongOutlinedIcon from '@mui/icons-material/ReceiptLongOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Skeleton from '@mui/material/Skeleton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { getMe, updateMe } from '../../api/users'
import { PageHeader } from '../../components/PageHeader'
import { useSnackbar } from '../../components/SnackbarProvider'
import type { UserProfile } from '../../types'
import { ProductPrefsPanels } from './ProductPrefsPanels'
import { SetupChecklist } from './SetupChecklist'

type AccountForm = {
  username: string
  email: string
}

export function SettingsPanels() {
  const { notify } = useSnackbar()
  const location = useLocation()
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [account, setAccount] = useState<AccountForm>({ username: '', email: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (new URLSearchParams(location.search).has('google')) {
      navigate(`/integrations${location.search}`, { replace: true })
    }
  }, [location.search, navigate])

  const applyProfile = (next: UserProfile) => {
    setAccount({ username: next.username, email: next.email })
  }

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getMe()
      .then(applyProfile)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load settings')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Settings"
        subtitle="Account, organization, notifications, privacy, and billing."
      />

      {error ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={load}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}

      {loading ? (
        <Stack spacing={2}>
          <Skeleton variant="rounded" height={48} />
          <Skeleton variant="rounded" height={200} />
        </Stack>
      ) : (
        <>
          <Tabs
            value={tab}
            onChange={(_, value: number) => setTab(value)}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="Settings sections"
          >
            <Tab icon={<PersonOutlinedIcon />} iconPosition="start" label="Account" />
            <Tab icon={<BusinessOutlinedIcon />} iconPosition="start" label="Organization" />
            <Tab icon={<NotificationsOutlinedIcon />} iconPosition="start" label="Notifications" />
            <Tab icon={<PolicyOutlinedIcon />} iconPosition="start" label="Privacy" />
            <Tab icon={<ReceiptLongOutlinedIcon />} iconPosition="start" label="Billing" />
          </Tabs>

          {tab === 0 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              <TextField
                label="Username"
                value={account.username}
                onChange={(e) => setAccount((a) => ({ ...a, username: e.target.value }))}
                fullWidth
                autoComplete="username"
              />
              <TextField
                label="Email"
                type="email"
                value={account.email}
                onChange={(e) => setAccount((a) => ({ ...a, email: e.target.value }))}
                fullWidth
                autoComplete="email"
              />
              <Button
                variant="contained"
                disabled={saving}
                loading={saving}
                sx={{ alignSelf: 'flex-start' }}
                onClick={() => {
                  setSaving(true)
                  updateMe({
                    username: account.username.trim(),
                    email: account.email.trim(),
                  })
                    .then((next) => {
                      applyProfile(next)
                      notify('Account updated', 'success')
                    })
                    .catch((err: unknown) => {
                      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
                    })
                    .finally(() => setSaving(false))
                }}
              >
                Save account
              </Button>
            </Stack>
          ) : null}

          {tab === 1 ? (
            <Stack spacing={3}>
              <Alert severity="info">
                Catalog, prices, business hours, and resources live under Business in the sidebar
                — not here.{' '}
                <Button component={RouterLink} to="/catalog" size="small">
                  Open catalog
                </Button>
                <Button component={RouterLink} to="/resources" size="small">
                  Open resources
                </Button>
                <Button component={RouterLink} to="/integrations" size="small">
                  Open integrations
                </Button>
              </Alert>
              <SetupChecklist />
            </Stack>
          ) : null}

          {tab === 2 ? (
            <ProductPrefsPanels sections={['notifications']} saveLabel="Save notifications" />
          ) : null}

          {tab === 3 ? (
            <ProductPrefsPanels sections={['privacy']} saveLabel="Save privacy settings" />
          ) : null}

          {tab === 4 ? (
            <Stack spacing={2} sx={{ maxWidth: 480 }}>
              <Typography variant="h3">Billing</Typography>
              <Typography variant="body1" color="text.secondary">
                Plan and invoices will appear here. Billing APIs are not wired yet.
              </Typography>
              <Alert severity="info">Contact support to change plan or payment method.</Alert>
            </Stack>
          ) : null}
        </>
      )}
    </Stack>
  )
}
