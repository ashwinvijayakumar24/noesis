import {
  ArrowRightIcon,
  BookOpenIcon,
  CheckCircleIcon,
  DocumentArrowUpIcon,
  DocumentMagnifyingGlassIcon,
  Squares2X2Icon,
} from '@heroicons/react/24/outline'

interface EmptyStateGuideProps {
  onUploadClick: () => void
  onImportClick?: () => void
}

export default function EmptyStateGuide({ onUploadClick, onImportClick }: EmptyStateGuideProps) {
  const outcomes = [
    {
      icon: <DocumentMagnifyingGlassIcon className="h-4 w-4" />,
      title: 'Citation checks',
      description: 'Match draft claims to papers in this project.'
    },
    {
      icon: <Squares2X2Icon className="h-4 w-4" />,
      title: 'Coverage gaps',
      description: 'Find unsupported sections before review.'
    },
    {
      icon: <CheckCircleIcon className="h-4 w-4" />,
      title: 'Method signals',
      description: 'Surface methods, datasets, and evaluation patterns.'
    }
  ]

  return (
    <div className="mx-auto max-w-3xl py-10">
      <div className="overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-sm">
        <div className="border-b border-border-default bg-bg-elevated/35 px-5 py-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-text-tertiary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-primary" />
            Literature setup
          </div>
        </div>

        <div className="p-6 sm:p-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-xl">
              <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg border border-accent-primary/25 bg-accent-subtle text-accent-primary">
                <BookOpenIcon className="h-5 w-5" />
              </div>
              <h2 className="text-2xl font-sans font-semibold tracking-normal text-text-primary">
                Add literature to start
              </h2>
              <p className="mt-3 max-w-lg text-sm leading-6 text-text-secondary">
                Upload PDFs or import a BibTeX file so Noesis can ground draft feedback in this project's sources.
              </p>
            </div>

            <div className="flex shrink-0 flex-col gap-2 sm:flex-row lg:flex-col">
              <button
                onClick={onUploadClick}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent-primary px-4 text-sm font-semibold text-white transition-all duration-150 hover:bg-accent-hover active:translate-y-px"
              >
                <DocumentArrowUpIcon className="h-4 w-4" />
                Upload PDF
              </button>
              {onImportClick && (
                <button
                  onClick={onImportClick}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border-default bg-bg-elevated px-4 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary active:translate-y-px"
                >
                  <BookOpenIcon className="h-4 w-4" />
                  Import .bib
                </button>
              )}
            </div>
          </div>

          <div className="mt-8 grid gap-3 border-t border-border-default pt-5 md:grid-cols-3">
            {outcomes.map(outcome => (
              <div key={outcome.title} className="flex gap-3">
                <div className="mt-0.5 text-accent-primary">
                  {outcome.icon}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">{outcome.title}</h3>
                  <p className="mt-1 text-xs leading-5 text-text-tertiary">{outcome.description}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2 text-xs font-medium text-text-muted">
            <span>Recommended</span>
            <ArrowRightIcon className="h-3.5 w-3.5" />
            <span className="text-text-secondary">add 5-10 relevant papers before uploading a draft</span>
          </div>
        </div>
      </div>
    </div>
  )
}
