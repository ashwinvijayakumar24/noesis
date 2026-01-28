import CitationSuggestionSidebar from '../CitationSuggestionSidebar'

interface CitationsPanelProps {
  token: string
  draftId: string
  projectId: string
}

export default function CitationsPanel({ token, draftId, projectId }: CitationsPanelProps) {
  return (
    <div className="h-full">
      <CitationSuggestionSidebar
        token={token}
        draftId={draftId}
        projectId={projectId}
      />
    </div>
  )
}
