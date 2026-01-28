import { useState } from 'react'
import { XMarkIcon, ArrowRightIcon, CheckIcon } from '@heroicons/react/24/outline'

interface OnboardingStep {
  title: string
  description: string
  action?: string
  icon: React.ReactElement
}

interface OnboardingTourProps {
  onComplete: () => void
  steps: OnboardingStep[]
}

export default function OnboardingTour({ onComplete, steps }: OnboardingTourProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [isVisible, setIsVisible] = useState(true)

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    } else {
      handleComplete()
    }
  }

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleComplete = () => {
    setIsVisible(false)
    onComplete()
  }

  const handleSkip = () => {
    setIsVisible(false)
    onComplete()
  }

  if (!isVisible) return null

  const step = steps[currentStep]
  const isLastStep = currentStep === steps.length - 1

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface rounded-2xl border-2 border-pink-600/30 shadow-2xl max-w-2xl w-full overflow-hidden">
        {/* Header */}
        <div className="bg-linear-to-r from-pink-600/20 to-rose-600/20 border-b border-border-base p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-pink-600/20 rounded-lg">
                {step.icon}
              </div>
              <div>
                <h2 className="text-2xl font-serif font-bold text-text-primary">{step.title}</h2>
                <p className="text-sm text-text-tertiary mt-1">
                  Step {currentStep + 1} of {steps.length}
                </p>
              </div>
            </div>
            <button
              onClick={handleSkip}
              className="p-2 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded-lg transition"
              title="Skip tour"
            >
              <XMarkIcon className="h-6 w-6" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-8">
          <p className="text-text-secondary text-lg leading-relaxed mb-6">
            {step.description}
          </p>

          {step.action && (
            <div className="bg-surface-hover border border-border-base rounded-lg p-4 mb-6">
              <p className="text-sm text-text-tertiary mb-2">Next step:</p>
              <p className="text-text-primary font-medium">{step.action}</p>
            </div>
          )}

          {/* Progress Bar */}
          <div className="mb-6">
            <div className="flex gap-2">
              {steps.map((_, index) => (
                <div
                  key={index}
                  className={`h-1.5 flex-1 rounded-full transition ${
                    index <= currentStep
                      ? 'bg-linear-to-r from-pink-600 to-rose-600'
                      : 'bg-border-base'
                  }`}
                />
              ))}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button
              onClick={handlePrevious}
              disabled={currentStep === 0}
              className="px-4 py-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Previous
            </button>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSkip}
                className="px-4 py-2 text-text-tertiary hover:text-text-primary transition"
              >
                Skip tour
              </button>
              <button
                onClick={handleNext}
                className="flex items-center gap-2 px-6 py-2.5 bg-linear-to-r from-pink-600 to-rose-600 text-white font-medium rounded-lg hover:from-pink-700 hover:to-rose-700 transition"
              >
                {isLastStep ? (
                  <>
                    <CheckIcon className="h-5 w-5" />
                    Get Started
                  </>
                ) : (
                  <>
                    Next
                    <ArrowRightIcon className="h-5 w-5" />
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
