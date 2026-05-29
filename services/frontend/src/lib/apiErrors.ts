export interface ApiErrorDetail {
  code?: string
  title?: string
  message?: string
  details?: unknown
  next_action?: string
  retryable?: boolean
  error?: string
  quota_type?: string
  limit?: number
  current?: number
  validation_errors?: unknown
  suggestions?: unknown
}

export function getApiErrorDetail(error: unknown): ApiErrorDetail | null {
  const maybeError = error as { detail?: unknown; data?: { detail?: unknown }; message?: string } | null
  const rawDetail = maybeError?.detail ?? maybeError?.data?.detail

  if (rawDetail && typeof rawDetail === 'object') {
    return rawDetail as ApiErrorDetail
  }

  if (typeof rawDetail === 'string') {
    return { message: rawDetail }
  }

  if (maybeError?.message) {
    return { message: maybeError.message }
  }

  return null
}

export function getApiErrorDetailsList(detail: ApiErrorDetail | null): string[] {
  if (!detail) return []

  const details = detail.details ?? detail.validation_errors ?? detail.suggestions
  if (Array.isArray(details)) {
    return details.map((item) => {
      if (typeof item === 'string') return item
      if (item && typeof item === 'object') return JSON.stringify(item)
      return String(item)
    })
  }

  if (typeof details === 'string') return [details]
  if (details && typeof details === 'object') return [JSON.stringify(details)]

  return []
}
