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
    <div className={`space-y-3 ${className}`}>
      {/* Progress bar */}
      <div className="relative">
        <div className="overflow-hidden h-3 flex rounded-full bg-bg-void border border-border-base">
          <div
            style={{ width: `${Math.min(progress, 100)}%` }}
            className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-gradient-to-r from-neon-pink to-accent-teal transition-all duration-500 ease-out"
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono font-bold text-neon-pink">{Math.round(progress)}%</span>
        <div className="flex items-center gap-4 text-text-secondary">
          {showElapsedTime && (
            <span className="flex items-center gap-1.5 font-medium">
              <ClockIcon className="h-4 w-4" />
              {formatTime(elapsedTime)}
            </span>
          )}
          {estimatedTimeRemaining !== undefined && (
            <span className="flex items-center gap-1.5 font-medium">
              <ClockIcon className="h-4 w-4" />
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
              <CheckCircleIcon className="h-6 w-6 text-success" />
            ) : step.active ? (
              <div className="h-6 w-6 rounded-full border-2 border-neon-pink flex items-center justify-center">
                <div className="h-2.5 w-2.5 rounded-full bg-neon-pink animate-pulse" />
              </div>
            ) : (
              <div className="h-6 w-6 rounded-full border-2 border-border-base" />
            )}
          </div>

          {/* Step content */}
          <div className="flex-1">
            <p className={`text-sm font-medium ${
              step.completed ? 'text-text-muted line-through' :
              step.active ? 'text-text-primary font-semibold' :
              'text-text-secondary'
            }`}>
              {step.label}
            </p>
            {step.description && step.active && (
              <p className="text-xs text-text-secondary mt-1">{step.description}</p>
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
    <div className={`bg-bg-surface rounded-2xl border border-border-base p-8 ${className}`}>
      {/* Status message */}
      {status && (
        <div className="mb-6">
          <h3 className="text-xl font-display font-bold text-text-primary mb-1">
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
          className="text-border-base"
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
          className="text-neon-pink transition-all duration-500 ease-out"
          strokeLinecap="round"
        />
      </svg>
      {/* Percentage text */}
      <span className="absolute text-lg font-display font-bold text-neon-pink">
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
      <div className="relative w-16 h-16">
        <div className="absolute top-0 left-0 w-full h-full">
          <div className="h-16 w-16 rounded-full border-4 border-border-base border-t-neon-pink animate-spin" />
        </div>
      </div>
      {message && (
        <p className="mt-4 text-sm font-medium text-text-primary">{message}</p>
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
