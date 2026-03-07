import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChatBubbleLeftIcon,
  XMarkIcon,
  HandThumbUpIcon,
  HandThumbDownIcon,
  FaceSmileIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'
import { Button } from './ui/Button'

interface FeedbackButtonProps {
  featureType: 'draft_analysis' | 'rag_chat' | 'paper_discovery' | 'citation_suggestion' | 'other'
  contextId?: string
  className?: string
}

const FEEDBACK_CATEGORIES = [
  { id: 'helpful', label: 'Helpful', icon: HandThumbUpIcon, color: 'text-teal-primary' },
  { id: 'not_helpful', label: 'Not Helpful', icon: HandThumbDownIcon, color: 'text-ruby-primary' },
  { id: 'confusing', label: 'Confusing', icon: FaceSmileIcon, color: 'text-amber-primary' },
  { id: 'missing_features', label: 'Missing Features', icon: ChatBubbleLeftIcon, color: 'text-indigo-primary' }
]

export default function FeedbackButton({ featureType, contextId, className = '' }: FeedbackButtonProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [rating, setRating] = useState<number | null>(null)
  const [feedbackText, setFeedbackText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!rating && !selectedCategory && !feedbackText.trim()) {
      return
    }

    setIsSubmitting(true)

    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          feature_type: featureType,
          context_id: contextId,
          rating,
          feedback_category: selectedCategory,
          feedback_text: feedbackText.trim() || null
        })
      })

      if (!response.ok) {
        throw new Error('Failed to submit feedback')
      }

      setIsSubmitted(true)

      // Close modal after showing success
      setTimeout(() => {
        handleClose()
      }, 2000)
    } catch (error) {
      console.error('Feedback submission error:', error)
      alert('Failed to submit feedback. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClose = () => {
    setIsOpen(false)
    setTimeout(() => {
      setSelectedCategory(null)
      setRating(null)
      setFeedbackText('')
      setIsSubmitted(false)
    }, 300)
  }

  return (
    <>
      {/* Feedback Button */}
      <button
        onClick={() => setIsOpen(true)}
        className={`inline-flex items-center gap-2 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary bg-bg-void hover:bg-bg-surface border border-border-default rounded-md transition-colors ${className}`}
        title="Send Feedback"
      >
        <ChatBubbleLeftIcon className="h-4 w-4" />
        <span>Feedback</span>
      </button>

      {/* Feedback Modal */}
      <AnimatePresence>
        {isOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/70 backdrop-blur-sm"
              onClick={handleClose}
            />

            {/* Modal */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative bg-bg-surface border border-border-default rounded-lg shadow-2xl max-w-md w-full"
            >
              {!isSubmitted ? (
                <>
                  {/* Header */}
                  <div className="flex items-center justify-between p-6 border-b border-border-default">
                    <div>
                      <h3 className="text-lg font-semibold text-text-primary">Send Feedback</h3>
                      <p className="text-sm text-text-secondary mt-1">Help us improve Noesis</p>
                    </div>
                    <button
                      onClick={handleClose}
                      className="text-text-muted hover:text-text-primary transition-colors"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>

                  {/* Form */}
                  <form onSubmit={handleSubmit} className="p-6 space-y-6">
                    {/* Rating */}
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-3">
                        How would you rate this feature?
                      </label>
                      <div className="flex gap-2">
                        {[1, 2, 3, 4, 5].map((value) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => setRating(value)}
                            className={`flex-1 py-2 text-sm font-medium rounded-lg border transition-all ${
                              rating === value
                                ? 'bg-accent-primary text-white border-accent-primary'
                                : 'bg-bg-void text-text-secondary border-border-default hover:border-accent-primary'
                            }`}
                          >
                            {value}
                          </button>
                        ))}
                      </div>
                      <div className="flex justify-between mt-1 px-1">
                        <span className="text-xs text-text-muted">Poor</span>
                        <span className="text-xs text-text-muted">Excellent</span>
                      </div>
                    </div>

                    {/* Category */}
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-3">
                        What best describes your feedback?
                      </label>
                      <div className="grid grid-cols-2 gap-2">
                        {FEEDBACK_CATEGORIES.map((category) => (
                          <button
                            key={category.id}
                            type="button"
                            onClick={() => setSelectedCategory(category.id)}
                            className={`flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border transition-all ${
                              selectedCategory === category.id
                                ? 'bg-accent-primary/10 text-accent-primary border-accent-primary'
                                : 'bg-bg-void text-text-secondary border-border-default hover:border-accent-primary'
                            }`}
                          >
                            <category.icon className={`h-4 w-4 ${selectedCategory === category.id ? 'text-accent-primary' : category.color}`} />
                            <span>{category.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Text Feedback */}
                    <div>
                      <label htmlFor="feedbackText" className="block text-sm font-medium text-text-secondary mb-2">
                        Additional Comments (Optional)
                      </label>
                      <textarea
                        id="feedbackText"
                        value={feedbackText}
                        onChange={(e) => setFeedbackText(e.target.value)}
                        placeholder="Tell us more about your experience..."
                        rows={4}
                        className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent resize-none"
                      />
                    </div>

                    {/* Submit Button */}
                    <Button
                      type="submit"
                      variant="primary"
                      size="lg"
                      className="w-full"
                      disabled={isSubmitting || (!rating && !selectedCategory && !feedbackText.trim())}
                    >
                      {isSubmitting ? 'Submitting...' : 'Submit Feedback'}
                    </Button>
                  </form>
                </>
              ) : (
                /* Success State */
                <div className="p-8 text-center space-y-4">
                  <div className="inline-flex items-center justify-center w-16 h-16 bg-teal-light rounded-full">
                    <CheckCircleIcon className="h-8 w-8 text-teal-primary" />
                  </div>
                  <h3 className="text-xl font-semibold text-text-primary">Thank You!</h3>
                  <p className="text-text-secondary">
                    Your feedback helps us make Noesis better for researchers like you.
                  </p>
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}
