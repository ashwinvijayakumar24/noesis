import { ApiError } from './api'

export type ApiDetail = {
  code?: string
  title?: string
  message?: string
  details?: string[] | Record<string, unknown>
  next_action?: 'retry' | 'upgrade' | 'fix_file' | 'refresh' | 'sign_in' | 'contact_support'
  retryable?: boolean
  [key: string]: unknown
}

export function normalizeApiDetail(payload: any): ApiDetail | undefined {
  const detail = payload?.detail
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) {
    return undefined
  }

  return detail as ApiDetail
}

export function getApiErrorDetail(error: unknown): ApiDetail | undefined {
  if (!(error instanceof ApiError)) {
    return undefined
  }

  return normalizeApiDetail(error.data)
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const detail = getApiErrorDetail(error)
  if (detail?.message) {
    return detail.message
  }

  if (error instanceof ApiError) {
    return error.message || fallback
  }

  if (error instanceof Error) {
    return error.message || fallback
  }

  return fallback
}

export function getApiErrorDetailsList(detail?: ApiDetail): string[] {
  if (!detail?.details) {
    return []
  }

  if (Array.isArray(detail.details)) {
    return detail.details.filter(Boolean).map(String)
  }

  return Object.entries(detail.details).map(([key, value]) => {
    if (Array.isArray(value)) {
      return `${key}: ${value.join(', ')}`
    }
    return `${key}: ${String(value)}`
  })
}
