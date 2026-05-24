/**
 * API client for Noesis backend
 * All requests include the authentication token from Supabase
 */

import { normalizeApiDetail } from './apiErrors'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  data?: any
  detail?: any

  constructor(
    message: string,
    status: number,
    data?: any
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.detail = normalizeApiDetail(data)
  }
}

async function fetchWithAuth(url: string, options: RequestInit = {}, token?: string) {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const detail = normalizeApiDetail(errorData)

    // Handle different error detail formats
    let errorMessage = `Request failed with status ${response.status}`
    if (detail?.message) {
      errorMessage = detail.message
    } else if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        // FastAPI validation errors are arrays
        errorMessage = errorData.detail.map((err: any) =>
          `${err.loc?.join('.') || 'field'}: ${err.msg}`
        ).join(', ')
      } else if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail
      } else if (typeof errorData.detail === 'object') {
        errorMessage = JSON.stringify(errorData.detail)
      }
    }

    throw new ApiError(
      errorMessage,
      response.status,
      errorData
    )
  }

  return response.json()
}

export const api = {
  // Health check
  health: () => fetch(`${API_URL}/health`).then(r => r.json()),

  // Projects
  projects: {
    list: (token: string) => fetchWithAuth('/projects', {}, token),
    create: (token: string, data: { title: string; description?: string }) => {
      // Build query parameters - FastAPI expects these in the URL for simple params
      const params = new URLSearchParams({ title: data.title })
      if (data.description && data.description.trim() !== '') {
        params.append('description', data.description)
      }
      return fetchWithAuth(`/projects?${params.toString()}`, {
        method: 'POST',
      }, token)
    },
    get: (token: string, id: string) => fetchWithAuth(`/projects/${id}`, {}, token),
    update: (token: string, id: string, data: { title?: string; description?: string | null }) => {
      const params = new URLSearchParams()
      if (data.title !== undefined) params.append('title', data.title)
      if (data.description !== undefined) params.append('description', data.description || '')
      return fetchWithAuth(`/projects/${id}?${params.toString()}`, {
        method: 'PUT',
      }, token)
    },
    delete: (token: string, id: string) =>
      fetchWithAuth(`/projects/${id}`, { method: 'DELETE' }, token),
    getBundle: (token: string, id: string) =>
      fetchWithAuth(`/projects/${id}/bundle`, {}, token),
    analyzeInsights: (token: string, id: string) =>
      fetchWithAuth(`/projects/${id}/insights/analyze`, { method: 'POST' }, token),
    getInsights: (token: string, id: string) =>
      fetchWithAuth(`/projects/${id}/insights`, {}, token),
    getBibResolutionStatus: (token: string, projectId: string) =>
      fetchWithAuth(`/projects/${projectId}/bib-resolution-status`, {}, token),
  },

  // Quota
  quota: {
    getSummary: (token: string) =>
      fetchWithAuth('/auth/quota-summary', {}, token),
  },

  // Documents
  documents: {
    list: (token: string, projectId?: string) => {
      const params = projectId ? `?project_id=${projectId}` : ''
      return fetchWithAuth(`/documents${params}`, {}, token)
    },
    get: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}`, {}, token),
    upload: async (token: string, file: File, data: { project_id: string; title?: string; description?: string }) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('project_id', data.project_id)
      if (data.title) formData.append('title', data.title)
      if (data.description) formData.append('description', data.description)

      const response = await fetch(`${API_URL}/documents/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const detail = normalizeApiDetail(errorData)
        throw new ApiError(
          detail?.message || errorData.detail || 'Upload failed',
          response.status,
          errorData
        )
      }

      return response.json()
    },
    delete: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}`, { method: 'DELETE' }, token),
    retry: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}/retry`, { method: 'POST' }, token),
    markFailed: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}/mark-failed`, { method: 'POST' }, token),
    analyze: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}/analyze`, { method: 'POST' }, token),
    resolve: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}/resolve`, { method: 'POST' }, token),
    update: (token: string, documentId: string, title: string) =>
      fetchWithAuth(`/documents/${documentId}?title=${encodeURIComponent(title)}`, { method: 'PUT' }, token),
    updateTags: (token: string, documentId: string, tags: string[]) =>
      fetchWithAuth(`/documents/${documentId}/tags`, { method: 'PATCH', body: JSON.stringify({ tags }) }, token),
    getAnalysis: (token: string, documentId: string) =>
      fetchWithAuth(`/documents/${documentId}/analysis`, {}, token),
    importBibtex: async (token: string, projectId: string, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`${API_URL}/projects/${projectId}/import-bibtex`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const detail = normalizeApiDetail(errorData)
        throw new ApiError(detail?.message || errorData.detail || 'BibTeX import failed', response.status, errorData)
      }
      return response.json()
    },
  },

  // Zotero integration endpoints
  zotero: {
    validateKey: (token: string, apiKey: string) =>
      fetchWithAuth('/api/zotero/validate-key', {
        method: 'POST',
        body: JSON.stringify({ api_key: apiKey }),
      }, token),
    getLibraries: (token: string, apiKey: string) =>
      fetchWithAuth('/api/zotero/libraries', {
        method: 'POST',
        body: JSON.stringify({ api_key: apiKey }),
      }, token),
    importCollection: (
      token: string,
      apiKey: string,
      zoteroUserId: number,
      projectId: string,
      collectionKey?: string,
      maxItems = 200,
    ) =>
      fetchWithAuth('/api/zotero/import', {
        method: 'POST',
        body: JSON.stringify({
          api_key: apiKey,
          zotero_user_id: zoteroUserId,
          project_id: projectId,
          collection_key: collectionKey || null,
          max_items: maxItems,
        }),
      }, token),
  },

  // RAG endpoints
  rag: {
    ingest: (token: string, documentId: string) =>
      fetchWithAuth(`/rag/ingest/${documentId}`, { method: 'POST' }, token),
    ingestSync: (token: string, documentId: string) =>
      fetchWithAuth(`/rag/ingest-sync/${documentId}`, { method: 'POST' }, token),
    status: (token: string, documentId: string) =>
      fetchWithAuth(`/rag/status/${documentId}`, {}, token),
    retrieve: (token: string, projectId: string, query: string, limit = 5) => {
      const params = new URLSearchParams({
        project_id: projectId,
        query,
        limit: limit.toString(),
      })
      return fetchWithAuth(`/rag/retrieve?${params}`, { method: 'POST' }, token)
    },
    query: (token: string, projectId: string, query: string, model = 'gpt-4o', maxChunks = 5) => {
      const params = new URLSearchParams({
        project_id: projectId,
        query,
        model,
        max_chunks: maxChunks.toString(),
      })
      return fetchWithAuth(`/rag/query?${params}`, { method: 'POST' }, token)
    },
  },

  search: {
    global: (token: string, query: string) => {
      const params = new URLSearchParams({ q: query })
      return fetchWithAuth(`/search?${params}`, {}, token)
    },
    recent: (token: string, limit = 5) => {
      const params = new URLSearchParams({ limit: limit.toString() })
      return fetchWithAuth(`/search/recent?${params}`, {}, token)
    },
  },

  // Tags
  tags: {
    getSuggestions: (token: string) =>
      fetchWithAuth('/tags/suggestions', {}, token),
    getAllProjectTags: (token: string) =>
      fetchWithAuth('/tags/projects', {}, token),
    getProjectTags: (token: string, projectId: string) =>
      fetchWithAuth(`/tags/projects/${projectId}`, {}, token),
    addTag: (token: string, projectId: string, tagName: string) =>
      fetchWithAuth(`/tags/projects/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag_name: tagName }),
      }, token),
    removeTag: (token: string, projectId: string, tagId: string) =>
      fetchWithAuth(`/tags/projects/${projectId}/tags/${tagId}`, {
        method: 'DELETE',
      }, token),
  },

  // Drafts
  drafts: {
    list: (token: string, projectId: string) =>
      fetchWithAuth(`/drafts?project_id=${projectId}`, {}, token),
    update: (token: string, draftId: string, title: string) =>
      fetchWithAuth(`/drafts/${draftId}?title=${encodeURIComponent(title)}`, { method: 'PUT' }, token),
    upload: async (
      token: string,
      file: File,
      data: {
        project_id: string
        title?: string
        paper_type?: string
        citation_style?: string
      }
    ) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('project_id', data.project_id)
      if (data.title) formData.append('title', data.title)
      if (data.paper_type) formData.append('paper_type', data.paper_type)
      if (data.citation_style) formData.append('citation_style', data.citation_style)

      const response = await fetch(`${API_URL}/drafts/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const detail = normalizeApiDetail(errorData)
        throw new ApiError(
          detail?.message || errorData.detail || 'Draft upload failed',
          response.status,
          errorData
        )
      }

      return response.json()
    },
    get: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}`, {}, token),
    getSignedUrl: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/signed-url`, {}, token),
    delete: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}`, { method: 'DELETE' }, token),
    analyze: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/analyze`, { method: 'POST' }, token),
    getAnalysis: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/analysis`, {}, token),
    getClaims: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/claims`, {}, token),
    getGaps: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/gaps`, {}, token),
    getFeedback: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/feedback`, {}, token),
    export: (token: string, draftId: string, format: string) =>
      fetchWithAuth(`/drafts/${draftId}/export?format=${format}`, {}, token),

    // Section-based endpoints (Phase 3)
    getSectionSummary: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/section-summary`, {}, token),
    getFeedbackBySection: (token: string, draftId: string, sectionType: string, status: string = 'new') =>
      fetchWithAuth(`/drafts/${draftId}/feedback-by-section?section_type=${sectionType}&status=${status}`, {}, token),
    updateFeedbackStatus: (token: string, draftId: string, feedbackId: string, feedbackType: string, status: string) =>
      fetchWithAuth(`/drafts/${draftId}/feedback/${feedbackId}/status?feedback_type=${feedbackType}&status=${status}`, {
        method: 'PATCH',
      }, token),
    assignSections: (token: string, draftId: string) =>
      fetchWithAuth(`/drafts/${draftId}/assign-sections`, { method: 'POST' }, token),
    getAllFeedback: (token: string, draftId: string, status: string = 'new', actionableOnly: boolean = true) =>
      fetchWithAuth(`/drafts/${draftId}/all-feedback?status=${status}&actionable_only=${actionableOnly}`, {}, token),
    findGapPapers: (token: string, draftId: string, gapId: string) =>
      fetchWithAuth(`/drafts/${draftId}/gaps/${gapId}/find-papers`, { method: 'POST' }, token),

    // Dispute/helpful reaction on a feedback item
    reactToFeedback: (token: string, draftId: string, feedbackId: string, action: 'helpful' | 'dispute') =>
      fetchWithAuth(`/drafts/${draftId}/feedback/${feedbackId}/react`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      }, token),
  },

  // Lab Invites
  labInvites: {
    generate: (token: string, projectId: string, labName?: string) =>
      fetchWithAuth('/lab-invite/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, lab_name: labName }),
      }, token),

    getInviteDetails: (code: string) =>
      fetchWithAuth(`/lab-invite/${code}`, {}, ''),

    join: (token: string, code: string) =>
      fetchWithAuth(`/lab-invite/${code}/join`, { method: 'POST' }, token),
  },

  // Citations
  citations: {
    // Generate citation suggestions for a claim
    generateSuggestions: (token: string, data: {
      claim_text: string
      project_id: string
      draft_id: string
      existing_citations?: string[]
      max_suggestions?: number
    }) =>
      fetchWithAuth('/citations/suggestions/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }, token),

    // Get all suggestions for a draft
    getDraftSuggestions: (token: string, draftId: string, status?: string) => {
      const params = status ? `?status=${status}` : ''
      return fetchWithAuth(`/citations/suggestions/draft/${draftId}${params}`, {}, token)
    },

    // Respond to a citation suggestion
    respondToSuggestion: (token: string, suggestionId: string, data: {
      status: string
      user_feedback?: string
    }) =>
      fetchWithAuth(`/citations/suggestions/${suggestionId}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggestion_id: suggestionId, ...data }),
      }, token),

    // Format citation in multiple styles
    formatCitation: (token: string, data: {
      title: string
      authors: string[]
      year: string
      journal?: string
      volume?: string
      issue?: string
      pages?: string
      doi?: string
      url?: string
      styles?: string[]
    }) =>
      fetchWithAuth('/citations/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }, token),

    // Create a new citation
    create: (token: string, data: {
      project_id: string
      document_id?: string
      title: string
      authors: string[]
      year?: number
      journal_name?: string
      doi?: string
      arxiv_id?: string
      url?: string
    }) =>
      fetchWithAuth('/citations/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }, token),

    // Get all citations for a project
    getProjectCitations: (token: string, projectId: string) =>
      fetchWithAuth(`/citations/project/${projectId}`, {}, token),

    // Analyze citations in a draft
    analyzeDraft: (token: string, draftId: string) =>
      fetchWithAuth(`/citations/analyze/draft/${draftId}`, { method: 'POST' }, token),

    // Validate citation format
    validate: (token: string, citation_string: string, expected_format: string = 'apa') =>
      fetchWithAuth(`/citations/validate?citation_string=${encodeURIComponent(citation_string)}&expected_format=${expected_format}`, { method: 'POST' }, token),
  },

  // Literature Review Compass
  compass: {
    getGuidance: (token: string, projectId: string) =>
      fetchWithAuth(`/compass/projects/${projectId}/guidance`, {}, token),
  },

  // Paper Discovery (Discover tab)
  discover: {
    list: (token: string, projectId: string, offset: number = 0) =>
      fetchWithAuth(
        `/paper-recommendations/projects/${projectId}?limit=5&offset=${offset}`,
        {},
        token,
      ),

    findForProject: (token: string, projectId: string) =>
      fetchWithAuth(`/paper-recommendations/projects/${projectId}/generate`, { method: 'POST' }, token),

    search: (token: string, projectId: string, query: string) =>
      fetchWithAuth(`/paper-recommendations/projects/${projectId}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      }, token),

    saveToLiterature: (token: string, projectId: string, recommendationId: string) =>
      fetchWithAuth(
        `/paper-recommendations/projects/${projectId}/save-discovered/${recommendationId}`,
        { method: 'POST' },
        token,
      ),

    dismiss: (token: string, recommendationId: string) =>
      fetchWithAuth(`/paper-recommendations/${recommendationId}`, { method: 'DELETE' }, token),

    getQuotaStatus: (token: string, projectId: string) =>
      fetchWithAuth(`/paper-recommendations/projects/${projectId}/quota-status`, {}, token),
  },
}
