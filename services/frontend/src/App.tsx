import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { lazy, Suspense } from 'react'
import ProtectedRoute from './components/ProtectedRoute'
import ErrorBoundary from './components/ErrorBoundary'
import UpgradeModal from './components/UpgradeModal'

// Lazy load page components for code splitting
const Landing = lazy(() => import('./pages/Landing'))
const PrivacyPolicy = lazy(() => import('./pages/PrivacyPolicy'))
const Pricing = lazy(() => import('./pages/Pricing'))
const AnalyticsDashboard = lazy(() => import('./pages/AnalyticsDashboard'))
const Projects = lazy(() => import('./pages/Projects'))
const ProjectDetail = lazy(() => import('./pages/ProjectDetail'))
const DraftAnalysis = lazy(() => import('./pages/DraftAnalysis'))
const Billing = lazy(() => import('./pages/Billing'))

// Loading fallback component
function PageLoader() {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-pink-600 border-r-transparent"></div>
        <p className="mt-4 text-gray-400">Loading...</p>
      </div>
    </div>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#242832',
              color: '#e6e8eb',
              border: '1px solid #363d4e',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
            },
            success: {
              iconTheme: {
                primary: '#10B981',
                secondary: '#242832',
              },
            },
            error: {
              iconTheme: {
                primary: '#EF4444',
                secondary: '#242832',
              },
              duration: 5000,
            },
          }}
        />
        {/* Global upgrade modal — triggered by quota 429 errors anywhere in the app */}
      <UpgradeModal />

      <Suspense fallback={<PageLoader />}>
          <Routes>
          {/* Public routes */}
          <Route path="/" element={<Landing />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/demo" element={<Navigate to="/" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/signup" element={<Navigate to="/" replace />} />
          <Route path="/auth/confirm" element={<Navigate to="/" replace />} />
          <Route path="/auth/callback" element={<Navigate to="/" replace />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />

        {/* Protected routes */}
        <Route
          path="/projects"
          element={
            <ProtectedRoute>
              <Projects />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects/:projectId"
          element={
            <ProtectedRoute>
              <ProjectDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/projects/:projectId/drafts/:draftId"
          element={
            <ProtectedRoute>
              <DraftAnalysis />
            </ProtectedRoute>
          }
        />
        <Route
          path="/billing"
          element={
            <ProtectedRoute>
              <Billing />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/analytics"
          element={
            <ProtectedRoute>
              <AnalyticsDashboard />
            </ProtectedRoute>
          }
        />

        {/* Fallback redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
