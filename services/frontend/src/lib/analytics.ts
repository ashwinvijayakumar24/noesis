/**
 * Analytics tracking utility
 *
 * Tracks user actions for product analytics.
 * Sends events to Supabase database and stores locally as backup.
 */

interface AnalyticsEvent {
  event: string
  timestamp: number
  properties?: Record<string, any>
  userId?: string
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

class Analytics {
  private events: AnalyticsEvent[] = []
  private userId: string | null = null
  private sessionId: string
  private maxStoredEvents = 1000
  private authToken: string | null = null

  constructor() {
    // Generate or retrieve session ID
    this.sessionId = this.getOrCreateSessionId()
  }

  /**
   * Set authentication token for API requests
   */
  setAuthToken(token: string | null) {
    this.authToken = token
  }

  /**
   * Get or create a session ID
   */
  private getOrCreateSessionId(): string {
    const existingSessionId = sessionStorage.getItem('noesis_session_id')
    if (existingSessionId) {
      return existingSessionId
    }

    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    sessionStorage.setItem('noesis_session_id', newSessionId)
    return newSessionId
  }

  /**
   * Initialize analytics with user ID
   */
  identify(userId: string) {
    this.userId = userId
    this.track('user_identified', { userId })
  }

  /**
   * Send event to backend API
   */
  private async sendToBackend(event: string, properties?: Record<string, any>) {
    // Only send if we have an auth token
    if (!this.authToken) {
      if (import.meta.env.DEV) {
        console.log('[Analytics] Skipping backend send - no auth token')
      }
      return
    }

    try {
      const response = await fetch(`${API_URL}/analytics-tracking/track`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.authToken}`,
        },
        body: JSON.stringify({
          event_name: event,
          event_properties: properties,
          session_id: this.sessionId,
        }),
      })

      if (!response.ok && import.meta.env.DEV) {
        console.warn('[Analytics] Failed to send event to backend:', response.status)
      }
    } catch (error) {
      // Silently fail - analytics should never break user experience
      if (import.meta.env.DEV) {
        console.warn('[Analytics] Error sending event to backend:', error)
      }
    }
  }

  /**
   * Track an event
   */
  track(event: string, properties?: Record<string, any>) {
    const analyticsEvent: AnalyticsEvent = {
      event,
      timestamp: Date.now(),
      properties,
      userId: this.userId || undefined,
    }

    this.events.push(analyticsEvent)

    // Keep only the most recent events to avoid memory issues
    if (this.events.length > this.maxStoredEvents) {
      this.events = this.events.slice(-this.maxStoredEvents)
    }

    // Log to console in development
    if (import.meta.env.DEV) {
      console.log('[Analytics]', event, properties)
    }

    // Store in localStorage for persistence (backup)
    this.saveToLocalStorage()

    // Send to backend API (Supabase)
    this.sendToBackend(event, properties)
  }

  /**
   * Track page view
   */
  page(pageName: string, properties?: Record<string, any>) {
    this.track('page_view', {
      page: pageName,
      ...properties,
    })
  }

  /**
   * Get all tracked events
   */
  getEvents(): AnalyticsEvent[] {
    return [...this.events]
  }

  /**
   * Clear all events
   */
  clearEvents() {
    this.events = []
    localStorage.removeItem('noesis_analytics_events')
  }

  /**
   * Save events to localStorage
   */
  private saveToLocalStorage() {
    try {
      localStorage.setItem('noesis_analytics_events', JSON.stringify(this.events))
    } catch (error) {
      console.error('Failed to save analytics to localStorage:', error)
    }
  }

  /**
   * Load events from localStorage
   */
  loadFromLocalStorage() {
    try {
      const stored = localStorage.getItem('noesis_analytics_events')
      if (stored) {
        this.events = JSON.parse(stored)
      }
    } catch (error) {
      console.error('Failed to load analytics from localStorage:', error)
    }
  }

  /**
   * Get analytics summary
   */
  getSummary() {
    const eventCounts: Record<string, number> = {}

    for (const event of this.events) {
      eventCounts[event.event] = (eventCounts[event.event] || 0) + 1
    }

    return {
      totalEvents: this.events.length,
      uniqueEvents: Object.keys(eventCounts).length,
      eventCounts,
      firstEvent: this.events[0]?.timestamp,
      lastEvent: this.events[this.events.length - 1]?.timestamp,
    }
  }
}

// Export singleton instance
export const analytics = new Analytics()

// Load existing events on initialization
analytics.loadFromLocalStorage()

/**
 * Predefined event tracking functions for common actions
 */
export const trackEvent = {
  // Authentication
  signUp: () => analytics.track('sign_up'),
  signIn: () => analytics.track('sign_in'),
  signOut: () => analytics.track('sign_out'),

  // Projects
  projectCreated: (projectId: string) => analytics.track('project_created', { projectId }),
  projectDeleted: (projectId: string) => analytics.track('project_deleted', { projectId }),
  projectUpdated: (projectId: string) => analytics.track('project_updated', { projectId }),
  projectOpened: (projectId: string) => analytics.track('project_opened', { projectId }),

  // Documents
  documentUploaded: (projectId: string, documentId: string) =>
    analytics.track('document_uploaded', { projectId, documentId }),
  documentDeleted: (projectId: string, documentId: string) =>
    analytics.track('document_deleted', { projectId, documentId }),
  documentOpened: (projectId: string, documentId: string) =>
    analytics.track('document_opened', { projectId, documentId }),

  // Drafts
  draftUploaded: (projectId: string, draftId: string) =>
    analytics.track('draft_uploaded', { projectId, draftId }),
  draftDeleted: (projectId: string, draftId: string) =>
    analytics.track('draft_deleted', { projectId, draftId }),
  draftOpened: (projectId: string, draftId: string) =>
    analytics.track('draft_opened', { projectId, draftId }),

  // Chat
  chatMessageSent: (projectId: string, messageLength: number) =>
    analytics.track('chat_message_sent', { projectId, messageLength }),
  chatHistoryCleared: (projectId: string) =>
    analytics.track('chat_history_cleared', { projectId }),

  // Insights
  literatureReviewGenerated: (projectId: string) =>
    analytics.track('literature_review_generated', { projectId }),
  researchQuestionsGenerated: (projectId: string) =>
    analytics.track('research_questions_generated', { projectId }),
  methodologyRecommendationsGenerated: (projectId: string) =>
    analytics.track('methodology_recommendations_generated', { projectId }),
  paperRecommendationsGenerated: (projectId: string) =>
    analytics.track('paper_recommendations_generated', { projectId }),

  // Analytics
  citationNetworkViewed: (projectId: string) =>
    analytics.track('citation_network_viewed', { projectId }),

  // Search
  globalSearchOpened: () => analytics.track('global_search_opened'),
  globalSearchPerformed: (query: string, resultCount: number) =>
    analytics.track('global_search_performed', { query, resultCount }),

  // Onboarding
  onboardingCompleted: () => analytics.track('onboarding_completed'),
  onboardingSkipped: () => analytics.track('onboarding_skipped'),

  // Tags
  tagAdded: (projectId: string, tagName: string) =>
    analytics.track('tag_added', { projectId, tagName }),
  tagRemoved: (projectId: string, tagName: string) =>
    analytics.track('tag_removed', { projectId, tagName }),

  // RAG Settings
  ragSettingsUpdated: (projectId: string, settings: any) =>
    analytics.track('rag_settings_updated', { projectId, settings }),
}
