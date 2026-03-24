import { useState } from 'react'
import { BookOpenIcon, TrashIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'

interface ImportedRefCardProps {
  document: {
    id: string
    title: string
    status: string
    created_at: string
    file_type?: string
    metadata?: {
      import_source?: string
      authors?: string[]
      year?: string
      journal?: string
      abstract?: string
      doi?: string
    }
  }
  projectId: string
  onDelete: (id: string, title: string) => void
}

export default function ImportedRefCard({ document, onDelete }: ImportedRefCardProps) {
  const [abstractExpanded, setAbstractExpanded] = useState(false)

  const meta = document.metadata ?? {}
  const authors = meta.authors ?? []
  const year = meta.year ?? ''
  const journal = meta.journal ?? ''
  const abstract = meta.abstract ?? ''
  const doi = meta.doi ?? ''
  const importSource = meta.import_source === 'zotero' ? 'Zotero' : 'BibTeX'
  const hasAbstract = abstract.trim().length > 0

  const authorLine = authors.length === 0
    ? ''
    : authors.length <= 2
      ? authors.join(', ')
      : `${authors[0]}, ${authors[1]} et al.`

  const metaLine = [authorLine, year, journal].filter(Boolean).join(' · ')

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete(document.id, document.title)
  }

  return (
    <div className="group bg-bg-surface rounded-lg border border-l-2 border-border-default border-l-border-subtle p-6 transition-all duration-150">
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="shrink-0">
          <div className="h-16 w-16 bg-bg-hover rounded-xl flex items-center justify-center border border-border-default">
            <BookOpenIcon className="h-9 w-9 text-text-tertiary" />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1 min-w-0">
              {/* Badges row */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-mono text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full border border-border-default">
                  {importSource}
                </span>
                <span className="text-xs text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full border border-border-default">
                  Metadata only
                </span>
                {hasAbstract && (
                  <span className="text-xs text-text-muted">
                    · Abstract indexed
                  </span>
                )}
              </div>

              {/* Title */}
              <h4 className="font-sans font-semibold text-base text-text-primary line-clamp-2 mb-1">
                {document.title}
              </h4>

              {/* Authors / year / journal */}
              {metaLine && (
                <p className="text-sm text-text-muted font-mono line-clamp-1">
                  {metaLine}
                </p>
              )}
            </div>

            {/* Delete button */}
            <button
              onClick={handleDelete}
              className="p-2 text-text-muted hover:text-error hover:bg-error/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100 shrink-0"
              title="Delete reference"
            >
              <TrashIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Abstract snippet */}
          {hasAbstract && (
            <div className="mt-3 pt-3 border-t border-border-default">
              <p className={`text-sm text-text-secondary leading-relaxed ${abstractExpanded ? '' : 'line-clamp-3'}`}>
                {abstract}
              </p>
              {abstract.length > 200 && (
                <button
                  onClick={() => setAbstractExpanded(v => !v)}
                  className="mt-1 text-xs text-text-muted hover:text-text-primary transition-colors"
                >
                  {abstractExpanded ? 'Show less' : 'Show more'}
                </button>
              )}
            </div>
          )}

          {/* DOI link */}
          {doi && (
            <div className="mt-3">
              <a
                href={`https://doi.org/${doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, '')}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-accent-primary transition-colors duration-150"
              >
                <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
                <span className="font-mono">{doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, '')}</span>
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
