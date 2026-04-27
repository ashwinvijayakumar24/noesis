/**
 * Skeleton Loading Components
 *
 * Provides skeleton screens for better perceived performance during data loading.
 * These components create placeholder UI that matches the shape of the actual content.
 */

import React from 'react'

interface SkeletonProps {
  className?: string
  variant?: 'text' | 'circular' | 'rectangular'
  width?: string | number
  height?: string | number
  animation?: 'pulse' | 'wave' | 'none'
}

/**
 * Base Skeleton component for creating loading placeholders
 */
export function Skeleton({
  className = '',
  variant = 'rectangular',
  width,
  height,
  animation = 'pulse'
}: SkeletonProps) {
  const baseClasses = 'bg-gray-200 dark:bg-gray-700'

  const variantClasses = {
    text: 'rounded',
    circular: 'rounded-full',
    rectangular: 'rounded-md'
  }

  const animationClasses = {
    pulse: 'animate-pulse',
    wave: 'animate-shimmer',
    none: ''
  }

  const styles: React.CSSProperties = {
    width: width || '100%',
    height: height || (variant === 'text' ? '1rem' : '100%')
  }

  return (
    <div
      className={`${baseClasses} ${variantClasses[variant]} ${animationClasses[animation]} ${className}`}
      style={styles}
    />
  )
}

/**
 * Skeleton for document/draft cards
 */
export function SkeletonCard() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-4">
      {/* Title */}
      <Skeleton variant="text" height="1.5rem" width="80%" />

      {/* Metadata line */}
      <div className="flex items-center space-x-4">
        <Skeleton variant="text" height="0.875rem" width="100px" />
        <Skeleton variant="text" height="0.875rem" width="80px" />
      </div>

      {/* Description */}
      <div className="space-y-2">
        <Skeleton variant="text" height="0.875rem" width="100%" />
        <Skeleton variant="text" height="0.875rem" width="90%" />
        <Skeleton variant="text" height="0.875rem" width="70%" />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-4">
        <Skeleton variant="rectangular" height="2rem" width="100px" />
        <Skeleton variant="circular" height="2rem" width="2rem" />
      </div>
    </div>
  )
}

/**
 * Skeleton for list items (documents, drafts, etc.)
 */
export function SkeletonListItem() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="flex-1 space-y-2">
          <Skeleton variant="text" height="1.25rem" width="70%" />
          <Skeleton variant="text" height="0.875rem" width="50%" />
        </div>
        <Skeleton variant="rectangular" height="1.5rem" width="80px" />
      </div>
      <div className="flex items-center space-x-4">
        <Skeleton variant="text" height="0.75rem" width="80px" />
        <Skeleton variant="text" height="0.75rem" width="60px" />
      </div>
    </div>
  )
}

/**
 * Skeleton for project cards
 */
export function SkeletonProjectCard() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-4 hover:shadow-lg transition-shadow">
      {/* Project title */}
      <Skeleton variant="text" height="1.5rem" width="60%" />

      {/* Description */}
      <div className="space-y-2">
        <Skeleton variant="text" height="0.875rem" width="100%" />
        <Skeleton variant="text" height="0.875rem" width="85%" />
      </div>

      {/* Stats */}
      <div className="flex items-center space-x-6 pt-2">
        <div className="flex items-center space-x-2">
          <Skeleton variant="circular" height="1rem" width="1rem" />
          <Skeleton variant="text" height="0.875rem" width="60px" />
        </div>
        <div className="flex items-center space-x-2">
          <Skeleton variant="circular" height="1rem" width="1rem" />
          <Skeleton variant="text" height="0.875rem" width="60px" />
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
        <Skeleton variant="text" height="0.75rem" width="120px" />
        <Skeleton variant="rectangular" height="2rem" width="90px" />
      </div>
    </div>
  )
}

/**
 * Skeleton for table rows
 */
export function SkeletonTableRow({ columns = 4 }: { columns?: number }) {
  return (
    <tr className="border-b border-gray-200 dark:border-gray-700">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-6 py-4">
          <Skeleton variant="text" height="1rem" width={i === 0 ? '80%' : '60%'} />
        </td>
      ))}
    </tr>
  )
}

/**
 * Skeleton for analysis insights
 */
export function SkeletonInsight() {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5 space-y-3">
      {/* Header with icon */}
      <div className="flex items-center space-x-3">
        <Skeleton variant="circular" height="2rem" width="2rem" />
        <Skeleton variant="text" height="1.25rem" width="40%" />
      </div>

      {/* Content */}
      <div className="space-y-2 pl-11">
        <Skeleton variant="text" height="0.875rem" width="100%" />
        <Skeleton variant="text" height="0.875rem" width="95%" />
        <Skeleton variant="text" height="0.875rem" width="80%" />
      </div>

      {/* Tags or actions */}
      <div className="flex items-center space-x-2 pl-11 pt-2">
        <Skeleton variant="rectangular" height="1.5rem" width="70px" />
        <Skeleton variant="rectangular" height="1.5rem" width="80px" />
      </div>
    </div>
  )
}

/**
 * Skeleton grid for cards (projects, documents, etc.)
 */
export function SkeletonGrid({
  count = 6,
  CardComponent = SkeletonCard
}: {
  count?: number
  CardComponent?: React.ComponentType
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <CardComponent key={i} />
      ))}
    </div>
  )
}

/**
 * Skeleton list for items
 */
export function SkeletonList({
  count = 5,
  ItemComponent = SkeletonListItem
}: {
  count?: number
  ItemComponent?: React.ComponentType
}) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <ItemComponent key={i} />
      ))}
    </div>
  )
}

/**
 * Full page skeleton with header and content
 */
export function SkeletonPage() {
  return (
    <div className="space-y-6 p-6">
      {/* Page header */}
      <div className="space-y-4">
        <Skeleton variant="text" height="2rem" width="300px" />
        <Skeleton variant="text" height="1rem" width="500px" />
      </div>

      {/* Action bar */}
      <div className="flex items-center justify-between py-4">
        <Skeleton variant="rectangular" height="2.5rem" width="200px" />
        <Skeleton variant="rectangular" height="2.5rem" width="120px" />
      </div>

      {/* Content grid */}
      <SkeletonGrid count={6} />
    </div>
  )
}
