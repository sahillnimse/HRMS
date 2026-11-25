import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { ToastProvider } from '@/components/ui/Toast'
import { AppShell } from '@/components/layout/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import UploadPage from '@/pages/UploadPage'
import ReviewPage from '@/pages/ReviewPage'
import CandidateDetailPage from '@/pages/CandidateDetailPage'

function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <DashboardPage />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/upload"
              element={
                <ProtectedRoute allowedRoles={['admin', 'recruiter']}>
                  <AppShell>
                    <UploadPage />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/review"
              element={
                <ProtectedRoute allowedRoles={['admin', 'recruiter']}>
                  <AppShell>
                    <ReviewPage />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/candidates/:id"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <CandidateDetailPage />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  )
}

export default App
