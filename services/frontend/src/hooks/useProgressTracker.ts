import { useState, useEffect, useCallback } from 'react'

interface ProgressData {
  addressedItems: string[]
  lastUpdated: string
}

/**
 * Hook for tracking addressed action items with localStorage persistence.
 * Data is stored per-draft to allow tracking progress across sessions.
 */
export function useProgressTracker(draftId: string | undefined) {
  const [addressedItems, setAddressedItems] = useState<string[]>([])
  const [isLoaded, setIsLoaded] = useState(false)

  // Storage key for this draft
  const storageKey = `noesis_draft_progress_${draftId}`

  // Load from localStorage on mount
  useEffect(() => {
    if (!draftId) {
      setIsLoaded(true)
      return
    }

    try {
      const stored = localStorage.getItem(storageKey)
      if (stored) {
        const data: ProgressData = JSON.parse(stored)
        setAddressedItems(data.addressedItems || [])
      }
    } catch (error) {
      console.error('[useProgressTracker] Error loading from localStorage:', error)
    }
    setIsLoaded(true)
  }, [draftId, storageKey])

  // Save to localStorage when addressedItems changes
  useEffect(() => {
    if (!draftId || !isLoaded) return

    try {
      const data: ProgressData = {
        addressedItems,
        lastUpdated: new Date().toISOString()
      }
      localStorage.setItem(storageKey, JSON.stringify(data))
    } catch (error) {
      console.error('[useProgressTracker] Error saving to localStorage:', error)
    }
  }, [addressedItems, draftId, storageKey, isLoaded])

  // Toggle an item's addressed state
  const toggleAddressed = useCallback((itemId: string) => {
    setAddressedItems(prev => {
      if (prev.includes(itemId)) {
        return prev.filter(id => id !== itemId)
      }
      return [...prev, itemId]
    })
  }, [])

  // Check if an item is addressed
  const isAddressed = useCallback((itemId: string) => {
    return addressedItems.includes(itemId)
  }, [addressedItems])

  // Mark multiple items as addressed
  const markAddressed = useCallback((itemIds: string[]) => {
    setAddressedItems(prev => {
      const newItems = itemIds.filter(id => !prev.includes(id))
      return [...prev, ...newItems]
    })
  }, [])

  // Mark multiple items as not addressed
  const markNotAddressed = useCallback((itemIds: string[]) => {
    setAddressedItems(prev => prev.filter(id => !itemIds.includes(id)))
  }, [])

  // Clear all progress
  const clearProgress = useCallback(() => {
    setAddressedItems([])
    if (draftId) {
      localStorage.removeItem(storageKey)
    }
  }, [draftId, storageKey])

  // Get count stats
  const getStats = useCallback((totalItems: number) => {
    const addressedCount = addressedItems.length
    const remainingCount = Math.max(0, totalItems - addressedCount)
    const progressPercent = totalItems > 0
      ? Math.round((addressedCount / totalItems) * 100)
      : 100

    return {
      addressedCount,
      remainingCount,
      progressPercent
    }
  }, [addressedItems])

  return {
    addressedItems,
    isLoaded,
    toggleAddressed,
    isAddressed,
    markAddressed,
    markNotAddressed,
    clearProgress,
    getStats
  }
}
