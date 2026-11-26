import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/contexts/AuthContext'
import { BlindModeProvider } from '@/contexts/BlindModeContext'
import { ToastProvider } from '@/components/ui/Toast'
import { AppShell } from '@/components/layout/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import CandidatesPage from '@/pages/CandidatesPage'
import JobsPage from '@/pages/JobsPage'
import JobDetailPage from '@/pages/JobDetailPage'
import UploadPage from '@/pages/UploadPage'
import ReviewPage from '@/pages/ReviewPage'
import CandidateDetailPage from '@/pages/CandidateDetailPage'
import CompareCandidatesPage from '@/pages/CompareCandidatesPage'
import PrivacyPage from '@/pages/PrivacyPage'
import InterviewsPage from '@/pages/InterviewsPage'

function App() {
  return (
    <AuthProvider>
      <BlindModeProvider>
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
                path="/candidates"
                element={
                  <ProtectedRoute>
                    <AppShell>
                      <CandidatesPage />
                    </AppShell>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/jobs"
                element={
                  <ProtectedRoute>
                    <AppShell>
                      <JobsPage />
                    </AppShell>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/jobs/:id"
                element={
                  <ProtectedRoute>
                    <AppShell>
                      <JobDetailPage />
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
              <Route
                path="/compare"
                element={
                  <ProtectedRoute>
                    <AppShell>
                      <CompareCandidatesPage />
                    </AppShell>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/interviews"
                element={
                  <ProtectedRoute>
                    <AppShell>
                      <InterviewsPage />
                    </AppShell>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/privacy"
                element={
                  <ProtectedRoute allowedRoles={['admin']}>
                    <AppShell>
                      <PrivacyPage />
                    </AppShell>
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </BlindModeProvider>
    </AuthProvider>
  )
}

export default App
