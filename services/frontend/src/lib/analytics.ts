// Analytics stub: pluggable for PostHog, Segment, etc.
class Analytics {
  private authToken: string | null = null

  setAuthToken(token: string | null) {
    this.authToken = token
  }

  identify(userId: string, traits?: Record<string, unknown>) {
    if (import.meta.env.DEV) {
      console.debug('[analytics] identify', userId, traits)
    }
  }

  track(event: string, properties?: Record<string, unknown>) {
    if (import.meta.env.DEV) {
      console.debug('[analytics] track', event, properties, { authenticated: Boolean(this.authToken) })
    }
  }

  page(name?: string, properties?: Record<string, unknown>) {
    if (import.meta.env.DEV) {
      console.debug('[analytics] page', name, properties)
    }
  }
}

export const analytics = new Analytics()

type TrackEvent = {
  (event: string, properties?: Record<string, unknown>): void
  signIn: () => void
  signUp: () => void
  onboardingCompleted: () => void
  projectCreated: (projectId: string) => void
  projectDeleted: (projectId: string) => void
  documentUploaded: (projectId: string, documentId: string) => void
  draftUploaded: (projectId: string, draftId: string) => void
}

const track = ((event: string, properties?: Record<string, unknown>) => {
  analytics.track(event, properties)
}) as TrackEvent

track.signIn = () => analytics.track('sign_in')
track.signUp = () => analytics.track('sign_up')
track.onboardingCompleted = () => analytics.track('onboarding_completed')
track.projectCreated = (projectId: string) => analytics.track('project_created', { projectId })
track.projectDeleted = (projectId: string) => analytics.track('project_deleted', { projectId })
track.documentUploaded = (projectId: string, documentId: string) => (
  analytics.track('document_uploaded', { projectId, documentId })
)
track.draftUploaded = (projectId: string, draftId: string) => (
  analytics.track('draft_uploaded', { projectId, draftId })
)

export const trackEvent = track
