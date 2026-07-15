import { getApiErrorDetail } from './apiErrors'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type RequestBody = Record<string, unknown> | FormData | undefined
type ApiRequestInit = Omit<RequestInit, 'body'> & {
  token?: string
  body?: RequestBody
}

export class ApiError extends Error {
  status: number
  detail: unknown
  data: unknown

  constructor(message: string, status: number, detail: unknown, data?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.data = data
  }
}

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T = any>(
  path: string,
  options: ApiRequestInit = {},
): Promise<T> {
  const headers: HeadersInit = {
    ...authHeaders(options.token),
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...options.headers,
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body instanceof FormData || options.body === undefined
      ? options.body
      : JSON.stringify(options.body),
  })

  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : data
    const parsed = getApiErrorDetail({ detail })
    throw new ApiError(
      parsed?.message || parsed?.title || response.statusText || 'Request failed',
      response.status,
      detail,
      data,
    )
  }

  return data as T
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) search.set(key, String(value))
  })
  const suffix = search.toString()
  return suffix ? `?${suffix}` : ''
}

function uploadForm(file: File, fields: Record<string, unknown>): FormData {
  const form = new FormData()
  form.append('file', file)
  Object.entries(fields).forEach(([key, value]) => {
    if (value !== undefined && value !== null) form.append(key, String(value))
  })
  return form
}

export const api = {
  projects: {
    list: (token: string) => request('/projects/', { token }),
    create: async (token: string, body: Record<string, unknown>) => {
      const response = await request('/projects/', { method: 'POST', token, body })
      return response.project ?? response
    },
    update: (token: string, projectId: string, body: Record<string, unknown>) => (
      request(`/projects/${projectId}`, { method: 'PUT', token, body })
    ),
    delete: (token: string, projectId: string) => request(`/projects/${projectId}`, { method: 'DELETE', token }),
    getBundle: (token: string, projectId: string) => request(`/projects/${projectId}/bundle`, { token }),
    getInsights: (token: string, projectId: string) => request(`/projects/${projectId}/insights`, { token }),
    analyzeInsights: (token: string, projectId: string) => (
      request(`/projects/${projectId}/insights/analyze`, { method: 'POST', token })
    ),
    getBibResolutionStatus: (token: string, projectId: string) => (
      request(`/projects/${projectId}/bib-resolution-status`, { token })
    ),
  },
  documents: {
    upload: (token: string, file: File, fields: Record<string, unknown>) => (
      request('/documents/upload', { method: 'POST', token, body: uploadForm(file, fields) })
    ),
    importBibtex: (token: string, projectId: string, file: File) => (
      request(`/projects/${projectId}/import-bibtex`, { method: 'POST', token, body: uploadForm(file, {}) })
    ),
    get: (token: string, documentId: string) => request(`/documents/${documentId}`, { token }),
    update: (token: string, documentId: string, title: string) => (
      request(`/documents/${documentId}`, { method: 'PUT', token, body: { title } })
    ),
    updateTags: (token: string, documentId: string, tags: string[]) => (
      request(`/documents/${documentId}/tags`, { method: 'PATCH', token, body: { tags } })
    ),
    delete: (token: string, documentId: string) => request(`/documents/${documentId}`, { method: 'DELETE', token }),
    analyze: (token: string, documentId: string) => request(`/documents/${documentId}/analyze`, { method: 'POST', token }),
    retry: (token: string, documentId: string) => request(`/documents/${documentId}/retry`, { method: 'POST', token }),
    getAnalysis: (token: string, documentId: string) => request(`/documents/${documentId}/analysis`, { token }),
  },
  drafts: {
    upload: (token: string, file: File, fields: Record<string, unknown>) => (
      request('/drafts/upload', { method: 'POST', token, body: uploadForm(file, fields) })
    ),
    list: async (token: string, projectId: string) => {
      const response = await request(`/drafts/projects/${projectId}/drafts`, { token })
      return Array.isArray(response) ? { drafts: response } : response
    },
    get: (token: string, draftId: string) => request(`/drafts/${draftId}`, { token }),
    update: (token: string, draftId: string, title: string) => (
      request(`/drafts/${draftId}`, { method: 'PUT', token, body: { title } })
    ),
    delete: (token: string, draftId: string) => request(`/drafts/${draftId}`, { method: 'DELETE', token }),
    analyze: (token: string, draftId: string) => request(`/drafts/${draftId}/analyze`, { method: 'POST', token }),
    getAnalysis: (token: string, draftId: string) => request(`/drafts/${draftId}/analysis`, { token }),
    getClaims: (token: string, draftId: string) => request(`/drafts/${draftId}/claims`, { token }),
    getGaps: (token: string, draftId: string) => request(`/drafts/${draftId}/gaps`, { token }),
    getFeedback: (token: string, draftId: string) => request(`/drafts/${draftId}/feedback`, { token }),
    getAllFeedback: (token: string, draftId: string, status = 'new', actionableOnly = true) => (
      request(`/drafts/${draftId}/all-feedback${query({ status, actionable_only: actionableOnly })}`, { token })
    ),
    updateFeedbackStatus: (
      token: string,
      draftId: string,
      feedbackId: string,
      feedbackType: string,
      status: string,
    ) => (
      request(`/drafts/${draftId}/feedback/${feedbackId}/status${query({ feedback_type: feedbackType, status })}`, {
        method: 'PATCH',
        token,
      })
    ),
    reactToFeedback: (token: string, draftId: string, feedbackId: string, action: string) => (
      request(`/drafts/${draftId}/feedback/${feedbackId}/react`, { method: 'POST', token, body: { action } })
    ),
  },
  discover: {
    getQuotaStatus: (token: string, projectId: string) => (
      request(`/paper-recommendations/projects/${projectId}/quota-status`, { token })
    ),
    list: (token: string, projectId: string, offset = 0, limit = 5) => (
      request(`/paper-recommendations/projects/${projectId}${query({ status: 'new', offset, limit })}`, { token })
    ),
    findForProject: (token: string, projectId: string) => (
      request(`/paper-recommendations/projects/${projectId}/generate`, { method: 'POST', token })
    ),
    search: (token: string, projectId: string, q: string) => (
      request(`/paper-recommendations/projects/${projectId}/search`, { method: 'POST', token, body: { query: q } })
    ),
    saveToLiterature: (token: string, projectId: string, recommendationId: string) => (
      request(`/paper-recommendations/projects/${projectId}/save-discovered/${recommendationId}`, { method: 'POST', token })
    ),
    dismiss: (token: string, recommendationId: string) => (
      request(`/paper-recommendations/${recommendationId}/status${query({ status: 'dismissed' })}`, { method: 'PATCH', token })
    ),
  },
  citations: {
    generateSuggestions: (token: string, body: Record<string, unknown>) => (
      request('/citations/suggestions/generate', { method: 'POST', token, body })
    ),
    getDraftSuggestions: (token: string, draftId: string, status?: string) => (
      request(`/citations/suggestions/draft/${draftId}${query({ status })}`, { token })
    ),
    respondToSuggestion: (token: string, suggestionId: string, body: Record<string, unknown>) => (
      request(`/citations/suggestions/${suggestionId}/respond`, { method: 'POST', token, body })
    ),
  },
  tags: {
    getSuggestions: (token: string) => request('/tags/suggestions', { token }),
    getAllProjectTags: (token: string) => request('/tags/projects', { token }),
    getProjectTags: (token: string, projectId: string) => request(`/tags/projects/${projectId}`, { token }),
    addTag: (token: string, projectId: string, tagName: string) => (
      request(`/tags/projects/${projectId}`, { method: 'POST', token, body: { tag_name: tagName } })
    ),
    removeTag: (token: string, projectId: string, tagId: string) => (
      request(`/tags/projects/${projectId}/tags/${tagId}`, { method: 'DELETE', token })
    ),
  },
  quota: {
    getSummary: (token: string) => request('/auth/quota-summary', { token }),
  },
  search: {
    global: (token: string, q: string) => request(`/search/${query({ q })}`, { token }),
    recent: (token: string) => request('/search/recent', { token }),
  },
  zotero: {
    validateKey: (token: string, apiKey: string) => request('/api/zotero/validate-key', { method: 'POST', token, body: { api_key: apiKey } }),
    getLibraries: (token: string, apiKey: string) => request('/api/zotero/libraries', { method: 'POST', token, body: { api_key: apiKey } }),
    importCollection: (
      token: string,
      apiKey: string,
      zoteroUserId: number,
      projectId: string,
      collectionKey?: string,
    ) => (
      request('/api/zotero/import', {
        method: 'POST',
        token,
        body: {
          api_key: apiKey,
          zotero_user_id: zoteroUserId,
          project_id: projectId,
          collection_key: collectionKey,
        },
      })
    ),
  },
  compass: {
    getGuidance: (token: string, projectId: string) => request(`/compass/projects/${projectId}/guidance`, { token }),
  },
  labInvites: {
    join: (token: string, code: string) => request(`/api/lab-invite/${code}/join`, { method: 'POST', token }),
  },
  subscriptions: {
    getPlans: () => request('/api/subscriptions/plans'),
    createCheckout: (token: string, body: Record<string, unknown>) => (
      request('/api/subscriptions/checkout', { method: 'POST', token, body })
    ),
    cancel: (token: string, body: Record<string, unknown>) => (
      request('/api/subscriptions/cancel', { method: 'POST', token, body })
    ),
    getUsage: (token: string) => request('/api/subscriptions/usage', { token }),
    getPortalSession: (token: string) => request('/api/subscriptions/portal-session', { method: 'POST', token }),
  },
}
