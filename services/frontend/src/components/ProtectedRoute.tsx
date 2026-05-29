import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

interface ProtectedRouteProps {
  children: ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  void children
  // App access is temporarily paused while backend issues are being fixed.
  return <Navigate to="/" replace />
}
