import { apiRequest } from './client'

export type PublicPayment = {
  id: number
  organization_id: number
  reservation_id: number | null
  amount_minor: number
  currency: string
  purpose: string
  provider: string
  status: string
  checkout_url: string | null
  link_expired: boolean
  expires_at: string | null
}

export function getPaymentByToken(token: string): Promise<PublicPayment> {
  const params = new URLSearchParams({ token })
  return apiRequest<PublicPayment>(`/api/v1/payments/by-token?${params.toString()}`, {
    method: 'GET',
  })
}

export function capturePaymentByToken(
  paymentId: number,
  token: string,
): Promise<PublicPayment> {
  return apiRequest<PublicPayment>(`/api/v1/payments/${paymentId}/capture`, {
    method: 'POST',
    body: { token },
  })
}

export function formatAmountMinor(amountMinor: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amountMinor / 100)
  } catch {
    return `${(amountMinor / 100).toFixed(2)} ${currency.toUpperCase()}`
  }
}
