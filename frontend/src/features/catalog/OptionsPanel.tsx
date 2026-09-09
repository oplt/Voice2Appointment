import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  createCatalogOption,
  deleteCatalogOption,
  listCatalogOptions,
  patchCatalogOption,
  type CatalogOption,
} from '../../api/catalog'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

type OptionsPanelProps = {
  itemId: number
}

export function OptionsPanel({ itemId }: OptionsPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [optionName, setOptionName] = useState('')

  const optionsQuery = useQuery({
    queryKey: queryKeys.catalog.options(itemId),
    queryFn: () => listCatalogOptions(itemId),
  })
  const options = optionsQuery.data ?? []

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.catalog.options(itemId) })
  }

  const createMutation = useMutation({
    mutationFn: () => createCatalogOption(itemId, { name: optionName.trim(), active: true }),
    onSuccess: () => {
      notify('Option added', 'success')
      setOptionName('')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to add option', 'error')
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (opt: CatalogOption) =>
      patchCatalogOption(itemId, opt.id, { active: !opt.active }),
    onSuccess: () => invalidate(),
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to update option', 'error')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (opt: CatalogOption) => deleteCatalogOption(itemId, opt.id),
    onSuccess: () => {
      notify('Option removed', 'success')
      invalidate()
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Failed to remove option', 'error')
    },
  })

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          label="Option name"
          value={optionName}
          onChange={(e) => setOptionName(e.target.value)}
          fullWidth
        />
        <Button
          variant="contained"
          disabled={!optionName.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate()}
          sx={{ whiteSpace: 'nowrap' }}
        >
          Add option
        </Button>
      </Stack>
      {optionsQuery.isPending ? (
        <CircularProgress size={20} />
      ) : options.length === 0 ? (
        <Typography color="text.secondary">No options yet.</Typography>
      ) : (
        <Stack spacing={1}>
          {options.map((opt) => (
            <Stack key={opt.id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography sx={{ flex: 1 }}>{opt.name}</Typography>
              <Chip
                size="small"
                label={opt.active ? 'Active' : 'Inactive'}
                variant="outlined"
              />
              <Button
                size="small"
                onClick={() => toggleMutation.mutate(opt)}
                disabled={toggleMutation.isPending}
              >
                {opt.active ? 'Disable' : 'Enable'}
              </Button>
              <IconButton
                aria-label={`Delete ${opt.name}`}
                size="small"
                onClick={() => deleteMutation.mutate(opt)}
                disabled={deleteMutation.isPending}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  )
}
