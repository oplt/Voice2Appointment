import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import {
  createResourceAvailability,
  deleteResourceAvailability,
  patchResourceAvailability,
  type AvailabilityRule,
  type Resource,
} from '../../api/resources'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useSnackbar } from '../../components/SnackbarProvider'
import { useResourceAvailabilityQuery, WEEKDAYS } from './useResourcesQueries'

type WorkingHoursPanelProps = {
  resource: Resource
}

export function WorkingHoursPanel({ resource }: WorkingHoursPanelProps) {
  const { notify } = useSnackbar()
  const queryClient = useQueryClient()
  const availabilityQuery = useResourceAvailabilityQuery(resource.id, true)
  const rules = availabilityQuery.data ?? []

  const [ruleOpen, setRuleOpen] = useState(false)
  const [editRule, setEditRule] = useState<AvailabilityRule | null>(null)
  const [deleteRule, setDeleteRule] = useState<AvailabilityRule | null>(null)
  const [ruleWeekday, setRuleWeekday] = useState('0')
  const [ruleStart, setRuleStart] = useState('09:00')
  const [ruleEnd, setRuleEnd] = useState('17:00')

  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: queryKeys.resources.availability(resource.id),
    })
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const body = {
        weekday: Number(ruleWeekday),
        start_time: ruleStart,
        end_time: ruleEnd,
      }
      return editRule
        ? patchResourceAvailability(resource.id, editRule.id, body)
        : createResourceAvailability(resource.id, body)
    },
    onSuccess: () => {
      notify(editRule ? 'Working hours updated' : 'Working hours added', 'success')
      setRuleOpen(false)
      setEditRule(null)
      invalidate()
    },
    onError: (err: unknown) =>
      notify(err instanceof ApiError ? err.message : 'Save failed', 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!deleteRule) throw new Error('No rule')
      return deleteResourceAvailability(resource.id, deleteRule.id)
    },
    onSuccess: () => {
      notify('Working hours removed', 'success')
      setDeleteRule(null)
      invalidate()
    },
    onError: (err: unknown) =>
      notify(err instanceof ApiError ? err.message : 'Delete failed', 'error'),
  })

  return (
    <>
      <Stack spacing={1.5}>
        <Button
          variant="outlined"
          sx={{ alignSelf: 'flex-start' }}
          onClick={() => {
            setEditRule(null)
            setRuleWeekday('0')
            setRuleStart('09:00')
            setRuleEnd('17:00')
            setRuleOpen(true)
          }}
        >
          Add working hours
        </Button>
        {availabilityQuery.isPending ? (
          <CircularProgress size={20} />
        ) : rules.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No availability rules yet.
          </Typography>
        ) : (
          rules.map((rule) => (
            <Stack key={rule.id} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="body2" sx={{ flex: 1 }}>
                {WEEKDAYS[rule.weekday] ?? `Day ${rule.weekday}`}: {rule.start_time}–
                {rule.end_time}
              </Typography>
              <Button
                size="small"
                onClick={() => {
                  setEditRule(rule)
                  setRuleWeekday(String(rule.weekday))
                  setRuleStart(rule.start_time)
                  setRuleEnd(rule.end_time)
                  setRuleOpen(true)
                }}
              >
                Edit
              </Button>
              <Button size="small" color="error" onClick={() => setDeleteRule(rule)}>
                Delete
              </Button>
            </Stack>
          ))
        )}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
            gap: 0.5,
            border: '1px solid var(--border-subtle)',
            borderRadius: 1,
            p: 1,
          }}
        >
          {WEEKDAYS.map((d, i) => {
            const has = rules.some((r) => r.weekday === i)
            return (
              <Box
                key={d}
                sx={{
                  bgcolor: has ? 'rgba(62, 106, 225, 0.12)' : 'var(--surface-secondary)',
                  minHeight: 64,
                  borderRadius: 0.5,
                  p: 0.5,
                }}
              >
                <Typography variant="caption">{d.slice(0, 1)}</Typography>
              </Box>
            )
          })}
        </Box>
      </Stack>

      <Dialog
        open={ruleOpen}
        onClose={() => !saveMutation.isPending && setRuleOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{editRule ? 'Edit working hours' : 'Add working hours'}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              select
              label="Day"
              value={ruleWeekday}
              onChange={(e) => setRuleWeekday(e.target.value)}
              fullWidth
            >
              {WEEKDAYS.map((day, index) => (
                <MenuItem key={day} value={index}>
                  {day}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Starts"
              type="time"
              value={ruleStart}
              onChange={(e) => setRuleStart(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
              required
            />
            <TextField
              label="Ends"
              type="time"
              value={ruleEnd}
              onChange={(e) => setRuleEnd(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRuleOpen(false)} disabled={saveMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!ruleStart || !ruleEnd || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteRule != null}
        title="Delete working hours?"
        description="This availability rule will be removed."
        confirmLabel="Delete"
        confirmColor="error"
        loading={deleteMutation.isPending}
        onClose={() => !deleteMutation.isPending && setDeleteRule(null)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </>
  )
}
