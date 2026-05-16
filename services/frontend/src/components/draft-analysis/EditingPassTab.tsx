import EditorDecisionCard from './EditorDecisionCard'

interface EditingIssue {
  text?: string
  issue?: string
  suggestion?: string
  section?: string
  location?: string
  note?: string
  severity?: string
}

interface EditingFeedback {
  grammar_issues: EditingIssue[]
  citation_issues: EditingIssue[]
  formatting_issues: EditingIssue[]
  structural_notes: EditingIssue[]
}

interface EditorDecision {
  proceed_to_review: boolean
  fatal_flaws: string[]
  scope_appropriate: boolean
  writing_quality: 'publishable' | 'needs_revision' | 'major_revision'
  notes: string
}

interface EditingPassTabProps {
  editingFeedback: EditingFeedback
  editorDecision?: EditorDecision | null
  paperType?: string
  citationStyle?: string
}

const PAPER_TYPE_LABELS: Record<string, string> = {
  journal_article: 'Journal article',
  conference_paper: 'Conference paper',
  thesis: 'Thesis',
  dissertation: 'Dissertation',
  preprint: 'Preprint',
}

const CITATION_STYLE_LABELS: Record<string, string> = {
  apa: 'APA',
  mla: 'MLA',
  chicago: 'Chicago',
  ieee: 'IEEE',
  vancouver: 'Vancouver',
  other: 'Other / mixed',
}

export default function EditingPassTab({
  editingFeedback,
  editorDecision,
  paperType,
  citationStyle,
}: EditingPassTabProps) {
  const sections = [
    {
      key: 'grammar',
      title: 'Grammar & spelling',
      count: editingFeedback.grammar_issues.length,
      description: 'Mechanical issues that affect readability and polish.',
      items: editingFeedback.grammar_issues,
    },
    {
      key: 'citation',
      title: 'Citation style',
      count: editingFeedback.citation_issues.length,
      description: 'Formatting issues against the selected citation style.',
      items: editingFeedback.citation_issues,
    },
    {
      key: 'formatting',
      title: 'Formatting',
      count: editingFeedback.formatting_issues.length,
      description: 'Heading, list, caption, and layout inconsistencies.',
      items: editingFeedback.formatting_issues,
    },
    {
      key: 'structure',
      title: 'Structure',
      count: editingFeedback.structural_notes.length,
      description: 'High-level notes tied to the paper type and section flow.',
      items: editingFeedback.structural_notes,
    },
  ]

  const totalIssues = sections.reduce((sum, s) => sum + s.count, 0)

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {editorDecision && <EditorDecisionCard decision={editorDecision} />}

      <div className="rounded-lg border border-border-default bg-bg-surface p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Stage 1 editing review</h3>
            <p className="mt-1 text-sm text-text-secondary leading-relaxed">
              This pass focuses on grammar, citation compliance, formatting, and paper-type structure before intellectual peer review.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
              {PAPER_TYPE_LABELS[paperType || 'journal_article'] || 'Journal article'}
            </span>
            <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
              {CITATION_STYLE_LABELS[citationStyle || 'apa'] || 'APA'}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {sections.map((section) => (
          <div key={section.key} className="rounded-lg border border-border-default bg-bg-surface p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">{section.title}</p>
            <p className="mt-2 text-2xl font-semibold text-text-primary">{section.count}</p>
            <p className="mt-2 text-xs text-text-secondary leading-relaxed">{section.description}</p>
          </div>
        ))}
      </div>

      {totalIssues === 0 ? (
        <div className="rounded-lg border border-border-default bg-bg-surface p-6 text-center">
          <p className="text-sm font-semibold text-text-primary">No Stage 1 issues flagged</p>
          <p className="mt-1 text-sm text-text-secondary">
            The draft looks mechanically clean based on the current editing pass.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sections.map((section) => (
            <div key={section.key} className="rounded-lg border border-border-default bg-bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-text-primary">{section.title}</h4>
                  <p className="mt-1 text-xs text-text-secondary">{section.description}</p>
                </div>
                <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs font-semibold text-text-secondary">
                  {section.count}
                </span>
              </div>

              {section.items.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {section.items.map((item, index) => (
                    <div key={`${section.key}-${index}`} className="rounded-lg border border-border-default bg-bg-elevated p-3">
                      {(item.section || item.location) && (
                        <p className="mb-1 text-xs font-semibold text-text-muted">
                          {item.section || item.location}
                        </p>
                      )}
                      {(item.text || item.note) && (
                        <p className="text-sm text-text-primary leading-relaxed">
                          {item.text || item.note}
                        </p>
                      )}
                      {item.issue && (
                        <p className="mt-2 text-xs text-text-secondary">
                          <span className="font-semibold text-text-primary">Issue:</span> {item.issue}
                        </p>
                      )}
                      {item.suggestion && (
                        <p className="mt-1 text-xs text-text-secondary">
                          <span className="font-semibold text-text-primary">Suggested fix:</span> {item.suggestion}
                        </p>
                      )}
                      {item.severity && (
                        <span className="mt-2 inline-flex rounded-lg border border-border-default bg-bg-void px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                          {item.severity}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-text-muted">No issues flagged in this category.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
