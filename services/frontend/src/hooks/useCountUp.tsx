import { useEffect, useRef, useState } from 'react'
import { useInView } from 'framer-motion'

interface UseCountUpOptions {
  start?: number
  end: number
  duration?: number
  decimals?: number
  suffix?: string
  prefix?: string
  separator?: string
  startOnView?: boolean
}

/**
 * useCountUp - Animated number counter hook
 *
 * Features:
 * - Smooth easing animation
 * - Triggers on scroll into view
 * - Customizable duration, decimals, prefix/suffix
 * - Number formatting with separators
 *
 * @example
 * const { value, ref } = useCountUp({ end: 1000, duration: 2, suffix: '+' })
 * return <div ref={ref}>{value}</div>
 */
export function useCountUp({
  start = 0,
  end,
  duration = 2,
  decimals = 0,
  suffix = '',
  prefix = '',
  separator = ',',
  startOnView = true
}: UseCountUpOptions) {
  const [count, setCount] = useState(start)
  const countRef = useRef<HTMLDivElement>(null)
  const isInView = useInView(countRef, { once: true, margin: '-100px' })
  const hasStarted = useRef(false)

  useEffect(() => {
    // Only start counting if in view (or if startOnView is false)
    if ((startOnView && !isInView) || hasStarted.current) {
      return
    }

    hasStarted.current = true
    const startTime = Date.now()
    const difference = end - start

    const easeOutQuart = (t: number): number => {
      return 1 - Math.pow(1 - t, 4)
    }

    const updateCount = () => {
      const now = Date.now()
      const elapsed = now - startTime
      const progress = Math.min(elapsed / (duration * 1000), 1)

      const easedProgress = easeOutQuart(progress)
      const current = start + difference * easedProgress

      setCount(current)

      if (progress < 1) {
        requestAnimationFrame(updateCount)
      } else {
        setCount(end)
      }
    }

    requestAnimationFrame(updateCount)
  }, [start, end, duration, isInView, startOnView])

  // Format number with separators and decimals
  const formatNumber = (num: number): string => {
    const fixed = num.toFixed(decimals)
    const parts = fixed.split('.')
    const integer = parts[0]
    const decimal = parts[1]

    // Add thousand separators
    const formatted = integer.replace(/\B(?=(\d{3})+(?!\d))/g, separator)

    return decimal ? `${formatted}.${decimal}` : formatted
  }

  const value = `${prefix}${formatNumber(count)}${suffix}`

  return {
    value,
    ref: countRef,
    rawValue: count
  }
}

/**
 * CountUp component - Ready-to-use counter component
 *
 * @example
 * <CountUp end={1000} duration={2} suffix="+" className="text-4xl font-bold" />
 */
export function CountUp({
  end,
  start = 0,
  duration = 2,
  decimals = 0,
  suffix = '',
  prefix = '',
  separator = ',',
  className = '',
  startOnView = true
}: UseCountUpOptions & { className?: string }) {
  const { value, ref } = useCountUp({
    start,
    end,
    duration,
    decimals,
    suffix,
    prefix,
    separator,
    startOnView
  })

  return (
    <div ref={ref} className={className}>
      {value}
    </div>
  )
}
