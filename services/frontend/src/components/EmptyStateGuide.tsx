import { DocumentTextIcon, BeakerIcon, LightBulbIcon, DocumentArrowUpIcon } from '@heroicons/react/24/outline'

interface EmptyStateGuideProps {
  onUploadClick: () => void
}

export default function EmptyStateGuide({ onUploadClick }: EmptyStateGuideProps) {
  const benefits = [
    {
      icon: <DocumentTextIcon className="h-6 w-6 text-accent-primary" />,
      title: 'Get citation suggestions',
      description: 'AI-powered suggestions for supporting your draft claims'
    },
    {
      icon: <LightBulbIcon className="h-6 w-6 text-accent-primary" />,
      title: 'Identify research gaps',
      description: 'Discover missing themes and literature in your field'
    },
    {
      icon: <BeakerIcon className="h-6 w-6 text-accent-primary" />,
      title: 'Find relevant methodologies',
      description: 'Extract methods, datasets, and evaluation metrics'
    }
  ]

  return (
    <div className="max-w-4xl mx-auto py-12">
      {/* Main Card */}
      <div className="bg-surface rounded-xl border-2 border-dashed border-border-base p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-accent-primary/10 rounded-full mb-4">
            <DocumentArrowUpIcon className="h-8 w-8 text-accent-primary" />
          </div>
          <h2 className="text-3xl font-serif font-bold text-text-primary mb-3">
            Get Started
          </h2>
          <p className="text-lg text-text-secondary max-w-2xl mx-auto">
            Upload research papers to build your knowledge base and unlock powerful analysis features
          </p>
        </div>

        {/* Step Indicator */}
        <div className="mb-8">
          <div className="flex items-center justify-center gap-2 mb-6">
            <div className="flex items-center justify-center w-8 h-8 bg-accent-primary text-white rounded-full font-semibold text-sm">
              1
            </div>
            <span className="text-text-secondary font-medium">Upload Research Papers</span>
          </div>
        </div>

        {/* Benefits Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {benefits.map((benefit, index) => (
            <div
              key={index}
              className="bg-bg-base border border-border-base rounded-lg p-6 hover:border-accent-primary/30 transition-colors"
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  {benefit.icon}
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary mb-2">
                    {benefit.title}
                  </h3>
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {benefit.description}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Why Start with Papers */}
        <div className="bg-surface-hover border border-border-subtle rounded-lg p-6 mb-8">
          <h4 className="font-semibold text-text-primary mb-3 flex items-center gap-2">
            <svg className="h-5 w-5 text-accent-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Why start with papers?
          </h4>
          <ul className="space-y-2 text-sm text-text-secondary">
            <li className="flex items-start gap-2">
              <svg className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Citation suggestions require papers in your library</span>
            </li>
            <li className="flex items-start gap-2">
              <svg className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Cross-paper insights need multiple documents</span>
            </li>
            <li className="flex items-start gap-2">
              <svg className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Coverage gap detection compares against your literature</span>
            </li>
          </ul>
        </div>

        {/* CTA Button */}
        <div className="text-center">
          <button
            onClick={onUploadClick}
            className="inline-flex items-center gap-2 px-8 py-4 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors shadow-lg hover:shadow-xl"
          >
            <DocumentArrowUpIcon className="h-5 w-5" />
            Upload Your First Paper
          </button>
          <p className="mt-4 text-sm text-text-muted">
            PDF files only, max 50MB
          </p>
        </div>

        {/* Recommended Flow */}
        <div className="mt-8 pt-8 border-t border-border-subtle">
          <p className="text-xs text-text-muted text-center mb-4">
            Recommended workflow
          </p>
          <div className="flex items-center justify-center gap-2 text-sm text-text-tertiary">
            <span className="px-3 py-1 bg-surface-hover rounded-full font-medium">Upload Papers</span>
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="px-3 py-1 bg-surface-hover rounded-full font-medium">Generate Insights</span>
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="px-3 py-1 bg-surface-hover rounded-full font-medium">Upload Draft</span>
          </div>
        </div>
      </div>
    </div>
  )
}
