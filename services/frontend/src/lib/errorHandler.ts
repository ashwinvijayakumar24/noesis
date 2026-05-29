import toast from 'react-hot-toast'
import { getApiErrorDetail } from './apiErrors'

function getErrorMessage(error: unknown, action?: string): string {
  const detail = getApiErrorDetail(error)
  if (detail?.message) return detail.message
  if (detail?.title) return detail.title

  const message = error instanceof Error ? error.message : null
  if (message) return message

  return action ? `Failed while ${action}` : 'Something went wrong'
}

export function handleError(error: unknown, action?: string): void {
  console.error(action ? `Error ${action}:` : 'Error:', error)
  toast.error(getErrorMessage(error, action))
}

export function handleQuotaError(error: unknown): boolean {
  const detail = getApiErrorDetail(error)
  const isQuotaError = (
    detail?.code === 'quota_exceeded' ||
    detail?.error === 'quota_exceeded' ||
    detail?.next_action === 'upgrade' ||
    (error instanceof Error && /quota|limit/i.test(error.message))
  )

  if (!isQuotaError) return false

  toast.error(detail?.message || detail?.title || 'Usage limit reached. Upgrade to continue.')
  return true
}

export function validateFileSize(file: File, maxSizeMb: number): boolean {
  const maxBytes = maxSizeMb * 1024 * 1024
  if (file.size <= maxBytes) return true

  toast.error(`${file.name} is larger than ${maxSizeMb}MB`)
  return false
}

export function validateFileType(file: File, allowedExtensions: string[]): boolean {
  const extension = file.name.split('.').pop()?.toLowerCase()
  const normalized = allowedExtensions.map((item) => item.toLowerCase().replace(/^\./, ''))

  if (extension && normalized.includes(extension)) return true

  toast.error(`Unsupported file type. Use ${normalized.map((item) => `.${item}`).join(', ')}.`)
  return false
}
