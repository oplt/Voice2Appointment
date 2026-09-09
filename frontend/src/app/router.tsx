import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { ProtectedRoute } from '../auth/ProtectedRoute'
import { AppLayout } from '../components/AppLayout'
import { RouteErrorBoundary, RouteLoadingFallback } from '../components/RouteBoundary'
import { HomePage } from '../pages/HomePage'

const DashboardPage = lazy(() =>
  import('../pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const CalendarPage = lazy(() =>
  import('../pages/CalendarPage').then((m) => ({ default: m.CalendarPage })),
)
const AppointmentsPage = lazy(() =>
  import('../pages/AppointmentsPage').then((m) => ({ default: m.AppointmentsPage })),
)
const ReservationsPage = lazy(() =>
  import('../pages/ReservationsPage').then((m) => ({ default: m.ReservationsPage })),
)
const CallsPage = lazy(() => import('../pages/CallsPage').then((m) => ({ default: m.CallsPage })))
const AnalyticsPage = lazy(() =>
  import('../pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const SettingsPage = lazy(() =>
  import('../pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const CatalogPage = lazy(() =>
  import('../pages/CatalogPage').then((m) => ({ default: m.CatalogPage })),
)
const PricingPage = lazy(() =>
  import('../pages/PricingPage').then((m) => ({ default: m.PricingPage })),
)
const ResourcesPage = lazy(() =>
  import('../pages/ResourcesPage').then((m) => ({ default: m.ResourcesPage })),
)
const CustomersPage = lazy(() =>
  import('../pages/CustomersPage').then((m) => ({ default: m.CustomersPage })),
)
const AgentPage = lazy(() => import('../pages/AgentPage').then((m) => ({ default: m.AgentPage })))
const IntegrationsPage = lazy(() =>
  import('../pages/IntegrationsPage').then((m) => ({ default: m.IntegrationsPage })),
)
const ForgotPasswordPage = lazy(() =>
  import('../pages/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage })),
)
const ResetPasswordPage = lazy(() =>
  import('../pages/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage })),
)
const SecurePaymentPage = lazy(() =>
  import('../pages/SecurePaymentPage').then((m) => ({ default: m.SecurePaymentPage })),
)
const InviteAcceptPage = lazy(() =>
  import('../pages/InviteAcceptPage').then((m) => ({ default: m.InviteAcceptPage })),
)
const NotFoundPage = lazy(() =>
  import('../pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

/** Route-level lazy loading preserved; Phase 9 owns nav IA. */
export function AppRouter() {
  const location = useLocation()
  return (
    <RouteErrorBoundary key={location.pathname}>
      <Suspense fallback={<RouteLoadingFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<Navigate to="/?mode=signIn" replace />} />
          <Route path="/register" element={<Navigate to="/?mode=signUp" replace />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/secure/:purpose" element={<SecurePaymentPage />} />

          <Route element={<ProtectedRoute />}>
            <Route path="/invite" element={<InviteAcceptPage />} />
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/appointments" element={<AppointmentsPage />} />
              <Route path="/reservations" element={<ReservationsPage />} />
              <Route path="/calls" element={<CallsPage />} />
              <Route path="/catalog" element={<CatalogPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/resources" element={<ResourcesPage />} />
              <Route path="/customers" element={<CustomersPage />} />
              <Route path="/agent" element={<AgentPage />} />
              <Route path="/integrations" element={<IntegrationsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>

          <Route path="/home" element={<Navigate to="/" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </RouteErrorBoundary>
  )
}
