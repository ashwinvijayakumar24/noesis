import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { lazy, Suspense } from 'react'
import ProtectedRoute from './components/ProtectedRoute'
import ErrorBoundary from './components/ErrorBoundary'
import UpgradeModal from './components/UpgradeModal'
import { FREEZE_MODE } from './config/site'

// Lazy load page components for code splitting
const Landing = lazy(() => import('./pages/Landing'))
const Demo = lazy(() => import('./pages/Demo'))
const Contact = lazy(() => import('./pages/Contact'))
const Login = lazy(() => import('./pages/Login'))
const SignUp = lazy(() => import('./pages/SignUp'))
const ConfirmEmail = lazy(() => import('./pages/ConfirmEmail'))
const AuthCallback = lazy(() => import('./pages/AuthCallback'))
const PrivacyPolicy = lazy(() => import('./pages/PrivacyPolicy'))
const Pricing = lazy(() => import('./pages/Pricing'))
const AnalyticsDashboard = lazy(() => import('./pages/AnalyticsDashboard'))
const Projects = lazy(() => import('./pages/Projects'))
const ProjectDetail = lazy(() => import('./pages/ProjectDetail'))
const DraftAnalysis = lazy(() => import('./pages/DraftAnalysis'))
const DocumentAnalysis = lazy(() => import('./pages/DocumentAnalysis'))

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
          {/* Public marketing routes — always live */}
          <Route path="/" element={<Landing />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/contact" element={<Contact />} />
          {/* Pricing shows self-serve consumer tiers — hidden in B2B freeze mode. */}
          <Route
            path="/pricing"
            element={FREEZE_MODE ? <Navigate to="/contact" replace /> : <Pricing />}
          />

          {FREEZE_MODE ? (
            /* Freeze mode: backend is offline — funnel every backend-dependent
               route to the Contact page instead of hitting dead APIs. */
            <>
              <Route path="/login" element={<Navigate to="/contact" replace />} />
              <Route path="/signup" element={<Navigate to="/contact" replace />} />
              <Route path="/auth/confirm" element={<Navigate to="/contact" replace />} />
              <Route path="/auth/callback" element={<Navigate to="/contact" replace />} />
              <Route path="/projects/*" element={<Navigate to="/contact" replace />} />
              <Route path="/admin/*" element={<Navigate to="/contact" replace />} />
            </>
          ) : (
            <>
              {/* Auth routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<SignUp />} />
              <Route path="/auth/confirm" element={<ConfirmEmail />} />
              <Route path="/auth/callback" element={<AuthCallback />} />

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
                path="/projects/:projectId/documents/:documentId"
                element={
                  <ProtectedRoute>
                    <DocumentAnalysis />
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
            </>
          )}

        {/* Fallback redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
