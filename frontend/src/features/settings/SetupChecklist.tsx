import ChecklistOutlinedIcon from '@mui/icons-material/ChecklistOutlined'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { getSetupReadiness } from '../../api/users'
import type { SetupReadiness } from '../../types'

export function SetupChecklist() {
  const [data, setData] = useState<SetupReadiness | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getSetupReadiness()
      .then(setData)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load readiness')
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return <Typography color="text.secondary">Checking setup…</Typography>
  }
  if (error) {
    return (
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
    )
  }
  if (!data) return null

  return (
    <Stack spacing={2} sx={{ maxWidth: 640 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <ChecklistOutlinedIcon />
        <Typography variant="h3">Setup checklist</Typography>
        <Chip
          label={
            data.ready
              ? 'Ready'
              : `${data.completed_required}/${data.total_required} required`
          }
          color={data.ready ? 'success' : 'default'}
          variant="outlined"
        />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Derived from live configuration — no JSON editing required.
      </Typography>
      <List dense>
        {data.items.map((item) => (
          <ListItem
            key={item.key}
            secondaryAction={
              !item.ok ? (
                <Button component={RouterLink} to={item.fix_path} size="small">
                  Fix
                </Button>
              ) : null
            }
          >
            <ListItemText
              primary={`${item.ok ? '✓' : '○'} ${item.label}${item.required ? '' : ' (optional)'}`}
              secondary={item.detail}
            />
          </ListItem>
        ))}
      </List>
      <Alert severity="info">{data.test_call_hint}</Alert>
    </Stack>
  )
}
