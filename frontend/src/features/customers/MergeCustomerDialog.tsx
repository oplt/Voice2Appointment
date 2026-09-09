import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { ApiError } from '../../api/client'
import { mergeCustomers, type Customer } from '../../api/customers'
import { queryKeys } from '../../api/queryKeys'
import { useSnackbar } from '../../components/SnackbarProvider'

function label(customer: Customer): string {
  return customer.name || customer.email || customer.phone || `#${customer.id}`
}

type MergeCustomerDialogProps = {
  open: boolean
  source: Customer | null
  candidates: Customer[]
  onClose: () => void
  onMerged: (target: Customer) => void
}

export function MergeCustomerDialog({
  open,
  source,
  candidates,
  onClose,
  onMerged,
}: MergeCustomerDialogProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const [targetId, setTargetId] = useState<number | ''>('')
  const [confirmText, setConfirmText] = useState('')
  const confirmed = confirmText.trim().toUpperCase() === 'MERGE'

  const targets = useMemo(
    () => candidates.filter((c) => source != null && c.id !== source.id),
    [candidates, source],
  )

  const target = targets.find((c) => c.id === targetId) ?? null

  const mergeMutation = useMutation({
    mutationFn: () => {
      if (!source || targetId === '') throw new Error('Missing merge targets')
      return mergeCustomers(source.id, Number(targetId))
    },
    onSuccess: (row) => {
      notify('Customers merged', 'success')
      void queryClient.invalidateQueries({ queryKey: queryKeys.customers.all })
      void queryClient.invalidateQueries({ queryKey: queryKeys.reservations.all })
      setTargetId('')
      setConfirmText('')
      onMerged(row)
    },
    onError: (err: unknown) => {
      notify(err instanceof ApiError ? err.message : 'Merge failed', 'error')
    },
  })

  const handleClose = () => {
    if (mergeMutation.isPending) return
    setTargetId('')
    setConfirmText('')
    onClose()
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Merge customers</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {!source ? (
            <Alert severity="warning">Select a source customer first.</Alert>
          ) : (
            <>
              <Alert severity="warning">
                This permanently moves reservations and contact data from the source into the
                target, then removes the source record. This cannot be undone.
              </Alert>
              <Typography variant="body2">
                Source (will be removed): <strong>{label(source)}</strong> (#{source.id})
              </Typography>
              <TextField
                select
                label="Target customer (kept)"
                value={targetId}
                onChange={(e) => {
                  setTargetId(e.target.value === '' ? '' : Number(e.target.value))
                  setConfirmText('')
                }}
                fullWidth
                required
              >
                <MenuItem value="">Select target…</MenuItem>
                {targets.map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    {label(c)} (#{c.id})
                  </MenuItem>
                ))}
              </TextField>
              {target ? (
                <Typography variant="body2" color="text.secondary">
                  Target kept: {label(target)} (#{target.id})
                </Typography>
              ) : null}
              <TextField
                label="Type MERGE to confirm"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                fullWidth
                helperText="Confirms you understand the source customer will be deleted."
              />
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={mergeMutation.isPending}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={!source || targetId === '' || !confirmed || mergeMutation.isPending}
          onClick={() => mergeMutation.mutate()}
        >
          Merge permanently
        </Button>
      </DialogActions>
    </Dialog>
  )
}
