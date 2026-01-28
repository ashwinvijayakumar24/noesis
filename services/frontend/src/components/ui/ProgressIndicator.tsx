/**
 * Progress Indicator Component
 *
 * Provides visual feedback for long-running operations like document/draft analysis.
 * Shows progress bar, current step, estimated time, and status messages.
 */

import { CheckCircleIcon, ClockIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface ProgressStep {
  label: string
  description?: string
  completed: boolean
  active: boolean
}

interface ProgressIndicatorProps {
  /**
   * Current progress percentage (0-100)
   */
  progress: number

  /**
   * Current operation status message
   */
  status?: string

  /**
   * Estimated time remaining in seconds
   */
  estimatedTimeRemaining?: number

  /**
   * List of steps in the process
   */
  steps?: ProgressStep[]

  /**
   * Show elapsed time
   */
  showElapsedTime?: boolean

  /**
   * Custom class name
   */
  className?: string
}

/**
 * Format seconds to human-readable time
 */
function formatTime(seconds: number): string {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  return `${minutes}m ${remainingSeconds}s`
}

/**
 * Progress bar with percentage and optional time estimate
 */
export function ProgressBar({
  progress,
  estimatedTimeRemaining,
  showElapsedTime = false,
  className = ''
}: ProgressIndicatorProps) {
  const [elapsedTime, setElapsedTime] = useState(0)

  useEffect(() => {
    if (!showElapsedTime) return

    const startTime = Date.now()
    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [showElapsedTime])

  return (
    <div className={`space-y-2 ${className}`}>
      {/* Progress bar */}
      <div className="relative">
        <div className="overflow-hidden h-2 text-xs flex rounded-full bg-gray-700">
          <div
            style={{ width: `${Math.min(progress, 100)}%` }}
            className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-gradient-to-r from-accent-primary to-accent-hover transition-all duration-500 ease-out"
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-xs text-text-tertiary">
        <span className="font-mono">{Math.round(progress)}%</span>
        <div className="flex items-center gap-4">
          {showElapsedTime && (
            <span className="flex items-center gap-1">
              <ClockIcon className="h-3 w-3" />
              {formatTime(elapsedTime)}
            </span>
          )}
          {estimatedTimeRemaining !== undefined && (
            <span className="flex items-center gap-1">
              <ClockIcon className="h-3 w-3" />
              ~{formatTime(estimatedTimeRemaining)} remaining
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Step-by-step progress indicator
 */
export function StepProgress({
  steps = [],
  className = ''
}: {
  steps: ProgressStep[]
  className?: string
}) {
  return (
    <div className={`space-y-3 ${className}`}>
      {steps.map((step, index) => (
        <div key={index} className="flex items-start gap-3">
          {/* Step indicator */}
          <div className="flex-shrink-0 mt-0.5">
            {step.completed ? (
              <CheckCircleIcon className="h-5 w-5 text-green-500" />
            ) : step.active ? (
              <div className="h-5 w-5 rounded-full border-2 border-accent-primary flex items-center justify-center">
                <div className="h-2 w-2 rounded-full bg-accent-primary animate-pulse" />
              </div>
            ) : (
              <div className="h-5 w-5 rounded-full border-2 border-gray-600" />
            )}
          </div>

          {/* Step content */}
          <div className="flex-1">
            <p className={`text-sm font-medium ${
              step.completed ? 'text-text-secondary line-through' :
              step.active ? 'text-text-primary' :
              'text-text-tertiary'
            }`}>
              {step.label}
            </p>
            {step.description && step.active && (
              <p className="text-xs text-text-tertiary mt-1">{step.description}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Complete progress indicator with bar and steps
 */
export function ProgressIndicator({
  progress,
  status,
  estimatedTimeRemaining,
  steps,
  showElapsedTime = true,
  className = ''
}: ProgressIndicatorProps) {
  return (
    <div className={`bg-surface rounded-lg border border-border-base p-6 ${className}`}>
      {/* Status message */}
      {status && (
        <div className="mb-4">
          <h3 className="text-lg font-serif font-semibold text-text-primary mb-1">
            {status}
          </h3>
        </div>
      )}

      {/* Progress bar */}
      <ProgressBar
        progress={progress}
        estimatedTimeRemaining={estimatedTimeRemaining}
        showElapsedTime={showElapsedTime}
        className="mb-6"
      />

      {/* Steps */}
      {steps && steps.length > 0 && (
        <StepProgress steps={steps} />
      )}
    </div>
  )
}

/**
 * Circular progress indicator (for compact spaces)
 */
export function CircularProgress({
  progress,
  size = 80,
  strokeWidth = 6,
  className = ''
}: {
  progress: number
  size?: number
  strokeWidth?: number
  className?: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (progress / 100) * circumference

  return (
    <div className={`relative inline-flex items-center justify-center ${className}`}>
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          fill="none"
          className="text-gray-700"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="text-accent-primary transition-all duration-500 ease-out"
          strokeLinecap="round"
        />
      </svg>
      {/* Percentage text */}
      <span className="absolute text-sm font-semibold text-text-primary font-mono">
        {Math.round(progress)}%
      </span>
    </div>
  )
}

/**
 * Indeterminate progress spinner (for unknown duration)
 */
export function IndeterminateProgress({
  message = 'Processing...',
  className = ''
}: {
  message?: string
  className?: string
}) {
  return (
    <div className={`flex flex-col items-center justify-center ${className}`}>
      <div className="relative w-12 h-12">
        <div className="absolute top-0 left-0 w-full h-full">
          <div className="h-12 w-12 rounded-full border-4 border-gray-700 border-t-accent-primary animate-spin" />
        </div>
      </div>
      {message && (
        <p className="mt-4 text-sm text-text-secondary">{message}</p>
      )}
    </div>
  )
}

/**
 * Hook for simulating progress based on estimated time
 */
export function useEstimatedProgress(estimatedDuration: number) {
  const [progress, setProgress] = useState(0)
  const [elapsedTime, setElapsedTime] = useState(0)

  useEffect(() => {
    const startTime = Date.now()
    const interval = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000
      setElapsedTime(elapsed)

      // Asymptotic progress: fast at first, slows down near completion
      // Never reaches 100% until actual completion
      const estimatedProgress = Math.min(
        95,
        (elapsed / estimatedDuration) * 100 * (1 - Math.exp(-elapsed / estimatedDuration))
      )

      setProgress(estimatedProgress)
    }, 100)

    return () => clearInterval(interval)
  }, [estimatedDuration])

  const complete = () => setProgress(100)
  const reset = () => {
    setProgress(0)
    setElapsedTime(0)
  }

  return {
    progress,
    elapsedTime,
    estimatedTimeRemaining: Math.max(0, estimatedDuration - elapsedTime),
    complete,
    reset
  }
}
