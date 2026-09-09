import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useState, type FormEvent } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import {
  capturePaymentByToken,
  formatAmountMinor,
  getPaymentByToken,
  type PublicPayment,
} from '../api/payments'
import { ApiError } from '../api/client'

type PageState =
  | { kind: 'loading' }
  | { kind: 'invalid' }
  | { kind: 'expired'; payment?: PublicPayment }
  | { kind: 'ready'; payment: PublicPayment }
  | { kind: 'paid'; payment: PublicPayment }
  | { kind: 'failed'; payment: PublicPayment; message: string }

/**
 * Public customer payment page. Never treats ?status=success as payment proof —
 * Stripe webhook / provider capture remains authoritative; this page polls by token.
 */
export function SecurePaymentPage() {
  const { purpose: purposeParam } = useParams<{ purpose: string }>()
  const [searchParams] = useSearchParams()
  const token = (searchParams.get('t') || '').trim()
  const returnHint = (searchParams.get('status') || '').trim().toLowerCase()

  const [state, setState] = useState<PageState>({ kind: 'loading' })
  const [manualToken, setManualToken] = useState(token)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function load(activeToken: string) {
      if (!activeToken) {
        if (!cancelled) setState({ kind: 'invalid' })
        return
      }
      if (!cancelled) setState({ kind: 'loading' })
      try {
        const payment = await getPaymentByToken(activeToken)
        if (cancelled) return
        if (payment.link_expired && payment.status === 'pending') {
          setState({ kind: 'expired', payment })
          return
        }
        if (payment.status === 'captured') {
          setState({ kind: 'paid', payment })
          return
        }
        if (payment.status === 'failed' || payment.status === 'cancelled') {
          setState({
            kind: 'failed',
            payment,
            message: `This payment is ${payment.status}.`,
          })
          return
        }
        if (payment.status === 'expired') {
          setState({ kind: 'expired', payment })
          return
        }
        setState({ kind: 'ready', payment })
        // After Stripe return, poll until webhook capture lands.
        if (returnHint === 'return' || returnHint === 'success') {
          timer = window.setTimeout(() => {
            void load(activeToken)
          }, 2500)
        }
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setState({ kind: 'invalid' })
          return
        }
        setState({ kind: 'invalid' })
      }
    }

    void load(token)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [token, returnHint])

  const onStripeRedirect = (payment: PublicPayment) => {
    if (!payment.checkout_url) {
      setError('Checkout is not available for this payment.')
      return
    }
    window.location.assign(payment.checkout_url)
  }

  const onManualCapture = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (state.kind !== 'ready') return
    const activeToken = (manualToken || token).trim()
    if (!activeToken) {
      setError('Payment token is required')
      return
    }
    setBusy(true)
    try {
      const payment = await capturePaymentByToken(state.payment.id, activeToken)
      setState({ kind: 'paid', payment })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Capture failed')
      try {
        const refreshed = await getPaymentByToken(activeToken)
        if (refreshed.status === 'captured') {
          setState({ kind: 'paid', payment: refreshed })
        } else if (refreshed.link_expired || refreshed.status === 'expired') {
          setState({ kind: 'expired', payment: refreshed })
        } else if (refreshed.status === 'failed') {
          setState({
            kind: 'failed',
            payment: refreshed,
            message: 'Payment failed.',
          })
        }
      } catch {
        /* keep error */
      }
    } finally {
      setBusy(false)
    }
  }

  const purpose = (purposeParam || 'payment').replace(/_/g, ' ')

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        px: 2,
        py: 4,
      }}
    >
      <Stack spacing={2.5} sx={{ width: '100%', maxWidth: 440 }}>
        <Stack spacing={1}>
          <Typography variant="h1" sx={{ fontSize: '2rem' }}>
            Secure {purpose}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Complete your payment securely. Status comes from the payment provider, not the
            browser return URL.
          </Typography>
        </Stack>

        {state.kind === 'loading' ? (
          <Stack spacing={2} sx={{ py: 4, alignItems: 'center' }}>
            <CircularProgress size={32} />
            <Typography variant="body2">Loading payment…</Typography>
          </Stack>
        ) : null}

        {state.kind === 'invalid' ? (
          <Alert severity="error">This payment link is invalid or incomplete.</Alert>
        ) : null}

        {state.kind === 'expired' ? (
          <Alert severity="warning">This payment link has expired. Request a new link.</Alert>
        ) : null}

        {state.kind === 'failed' ? (
          <Alert severity="error">{state.message}</Alert>
        ) : null}

        {state.kind === 'paid' ? (
          <Alert severity="success">
            Payment received for{' '}
            {formatAmountMinor(state.payment.amount_minor, state.payment.currency)}.
          </Alert>
        ) : null}

        {state.kind === 'ready' ? (
          <Stack spacing={2} component="form" onSubmit={onManualCapture}>
            <Alert severity="info">
              Amount due:{' '}
              <strong>
                {formatAmountMinor(state.payment.amount_minor, state.payment.currency)}
              </strong>
            </Alert>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {returnHint === 'return' || returnHint === 'success' ? (
              <Alert severity="info">
                Checking payment status with the provider. This may take a moment…
              </Alert>
            ) : null}
            {state.payment.provider === 'stripe' && state.payment.checkout_url ? (
              <Button
                variant="contained"
                fullWidth
                onClick={() => onStripeRedirect(state.payment)}
              >
                Continue to Stripe
              </Button>
            ) : null}
            {(state.payment.provider === 'manual' ||
              state.payment.provider === 'twilio_sms_link' ||
              !state.payment.checkout_url) && (
              <>
                {!token ? (
                  <TextField
                    label="Payment token"
                    value={manualToken}
                    onChange={(e) => setManualToken(e.target.value)}
                    fullWidth
                    required
                  />
                ) : null}
                <Button type="submit" variant="contained" loading={busy} fullWidth>
                  Confirm payment
                </Button>
              </>
            )}
          </Stack>
        ) : null}
      </Stack>
    </Box>
  )
}
