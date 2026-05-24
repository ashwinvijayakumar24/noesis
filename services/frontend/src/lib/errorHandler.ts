/**
 * Error handling utilities for providing user-friendly error messages
 */

import toast from 'react-hot-toast'
import { ApiError } from './api'
import { getApiErrorDetail, getApiErrorDetailsList } from './apiErrors'
import { useUpgradeModalStore } from '../stores/upgradeModalStore'

/**
 * Check if error is a quota-exceeded 429 and open the upgrade modal.
 * Returns true if handled, false if the caller should fall back to handleError.
 */
export function handleQuotaError(error: any): boolean {
  if (error instanceof ApiError && error.status === 429) {
    const detail = getApiErrorDetail(error)
    if (detail?.code === 'quota_exceeded' || detail?.error === 'quota_exceeded') {
      const quotaType = detail.quota_type as any
      const message = detail.message as string | undefined
      useUpgradeModalStore.getState().open(quotaType, message)
      return true
    }
  }
  return false
}

/**
 * Get a user-friendly error message based on the error type and status
 */
export function getUserFriendlyErrorMessage(error: any, context?: string): string {
  // Handle ApiError instances
  if (error instanceof ApiError) {
    const detail = getApiErrorDetail(error)
    if (detail?.message) {
      return detail.message
    }

    switch (error.status) {
      case 400:
        return context
          ? `Invalid ${context}. Please check your input and try again.`
          : 'Invalid request. Please check your input and try again.'

      case 401:
        return 'Your session has expired. Please sign in again.'

      case 403:
        return 'You don\'t have permission to perform this action.'

      case 404:
        return context
          ? `${context} not found. It may have been deleted.`
          : 'The requested resource was not found.'

      case 409:
        return 'This operation conflicts with existing data. Please refresh and try again.'

      case 413:
        return 'The file is too large. Please upload a smaller file.'

      case 422:
        return context
          ? `Unable to process ${context}. Please check the format and try again.`
          : 'Unable to process your request. Please check the data and try again.'

      case 429:
        return 'Too many requests. Please wait a moment and try again.'

      case 500:
        return 'Our server encountered an error. Please try again in a few moments.'

      case 502:
      case 503:
      case 504:
        return 'Our service is temporarily unavailable. Please try again in a few moments.'

      default:
        return error.message || 'An unexpected error occurred. Please try again.'
    }
  }

  // Handle network errors
  if (error.message?.toLowerCase().includes('network') ||
      error.message?.toLowerCase().includes('fetch')) {
    return 'Network error. Please check your internet connection and try again.'
  }

  // Handle timeout errors
  if (error.message?.toLowerCase().includes('timeout')) {
    return 'Request timed out. Please try again.'
  }

  // Generic fallback
  return error.message || 'An unexpected error occurred. Please try again.'
}

/**
 * Handle errors and show appropriate toast notifications
 */
export function handleError(error: any, context?: string, customMessage?: string) {
  console.error(`Error in ${context || 'operation'}:`, error)

  const detail = getApiErrorDetail(error)
  const message = customMessage || getUserFriendlyErrorMessage(error, context)
  const detailLines = getApiErrorDetailsList(detail)
  toast.error(message, {
    duration: 5000,
    position: 'top-right',
  })
  if (detail?.title && detail.title !== message) {
    console.info(`[ERROR-DETAIL] ${detail.title}: ${detailLines.join(' | ')}`)
  }
}

/**
 * Handle errors with retry functionality
 * Note: Currently just shows error message. Future enhancement: add retry button.
 */
export function handleErrorWithRetry(
  error: any,
  context: string,
  retryFn: () => void | Promise<void>,
  customMessage?: string
) {
  console.error(`Error in ${context}:`, error)

  const message = customMessage || getUserFriendlyErrorMessage(error, context)

  toast.error(`${message}\n\nPlease try again.`, {
    duration: 7000,
    position: 'top-right',
  })

  // Retry function is available but not used in this simplified version
  // Could be enhanced in the future to provide a retry button
  void retryFn
  void context
}

/**
 * Validate file size before upload
 */
export function validateFileSize(file: File, maxSizeMB: number = 50): boolean {
  const maxSizeBytes = maxSizeMB * 1024 * 1024
  if (file.size > maxSizeBytes) {
    toast.error(`File size exceeds ${maxSizeMB}MB limit. Please upload a smaller file.`)
    return false
  }
  return true
}

/**
 * Validate file type
 */
export function validateFileType(file: File, allowedTypes: string[]): boolean {
  const fileExtension = file.name.split('.').pop()?.toLowerCase()
  if (!fileExtension || !allowedTypes.includes(fileExtension)) {
    toast.error(`Invalid file type. Allowed types: ${allowedTypes.join(', ')}`)
    return false
  }
  return true
}
