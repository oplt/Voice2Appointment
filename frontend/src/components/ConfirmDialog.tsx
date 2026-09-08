import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogTitle from '@mui/material/DialogTitle'
import type { ReactNode } from 'react'

type ConfirmDialogProps = {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  confirmColor?: 'primary' | 'error' | 'warning'
  loading?: boolean
  onConfirm: () => void
  onClose: () => void
}

/**
 * Modal confirm. MUI Dialog restores focus to the opener on close
 * (disableRestoreFocus left false).
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmColor = 'primary',
  loading = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const titleId = 'confirm-dialog-title'
  const descriptionId = 'confirm-dialog-description'

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onClose}
      fullWidth
      maxWidth="xs"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      disableRestoreFocus={false}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      {description ? (
        <DialogContent>
          <DialogContentText id={descriptionId} component="div">
            {description}
          </DialogContentText>
        </DialogContent>
      ) : null}
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={loading} variant="text">
          {cancelLabel}
        </Button>
        <Button
          onClick={onConfirm}
          disabled={loading}
          loading={loading}
          variant="contained"
          color={confirmColor}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
