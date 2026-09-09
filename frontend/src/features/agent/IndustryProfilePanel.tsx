import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { ApiError } from '../../api/client'
import {
  getIndustryProfile,
  putIndustryProfile,
  type IndustryType,
} from '../../api/knowledge'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

const INDUSTRY_TYPES: IndustryType[] = ['clinic', 'restaurant', 'salon', 'general']

export function IndustryProfilePanel() {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [industryType, setIndustryType] = useState<IndustryType>('general')

  const profileQuery = useQuery({
    queryKey: queryKeys.industryProfile.current,
    queryFn: getIndustryProfile,
  })

  useEffect(() => {
    const profile = profileQuery.data
    if (
      profile?.industry_type &&
      INDUSTRY_TYPES.includes(profile.industry_type as IndustryType)
    ) {
      setIndustryType(profile.industry_type as IndustryType)
    }
  }, [profileQuery.data])

  const profileSave = useMutation({
    mutationFn: () => putIndustryProfile({ industry_type: industryType }),
    onSuccess: () => {
      notify('Industry profile saved', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.industryProfile.all })
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error')
    },
  })

  return (
    <Stack spacing={2} sx={{ maxWidth: 480 }}>
      <Typography variant="h3">Industry profile</Typography>
      {profileQuery.isPending ? (
        <CircularProgress size={28} />
      ) : profileQuery.error ? (
        <Alert severity="error">
          {profileQuery.error instanceof ApiError
            ? profileQuery.error.message
            : 'Failed to load industry profile'}
        </Alert>
      ) : (
        <>
          {!profileQuery.data ? (
            <Alert severity="info">No profile assigned yet — pick an industry type below.</Alert>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Scheduling mode: {profileQuery.data.scheduling_mode}
            </Typography>
          )}
          <TextField
            select
            label="Industry type"
            value={industryType}
            onChange={(e) => setIndustryType(e.target.value as IndustryType)}
            fullWidth
          >
            {INDUSTRY_TYPES.map((type) => (
              <MenuItem key={type} value={type}>
                {type}
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant="contained"
            sx={{ alignSelf: 'flex-start' }}
            disabled={profileSave.isPending}
            onClick={() => profileSave.mutate()}
          >
            Save industry type
          </Button>
        </>
      )}
    </Stack>
  )
}
