import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { motion } from 'framer-motion'
import {
  SparklesIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline'
import { Button } from '../components/ui/Button'
import EmailCaptureModal from '../components/EmailCaptureModal'
import toast from 'react-hot-toast'

// Demo data - sample draft analysis results
const DEMO_DATA = {
  project: {
    title: "Demo: Attention Mechanisms in Neural Networks",
    description: "Sample project showing draft analysis capabilities"
  },
  draft: {
    title: "Attention is All You Need: A Critical Review",
    version: 1,
    word_count: 4500
  },
  analysis: {
    claims: [
      {
        id: 1,
        claim_text: "The Transformer architecture achieves state-of-the-art performance on machine translation tasks",
        claim_type: "empirical",
        claim_subtype: "comparative",
        claim_level: "main",
        importance_score: 0.9,
        citation_strength: "strong",
        existing_citations: ["Vaswani et al. (2017)", "Devlin et al. (2019)"],
        unsupported: false,
        section_location: "Introduction"
      },
      {
        id: 2,
        claim_text: "Self-attention mechanisms eliminate the need for recurrent layers entirely",
        claim_type: "theoretical",
        claim_subtype: "causal",
        claim_level: "thesis",
        importance_score: 1.0,
        citation_strength: "strong",
        existing_citations: ["Vaswani et al. (2017)"],
        unsupported: false,
        section_location: "Background"
      },
      {
        id: 3,
        claim_text: "Attention mechanisms have been shown to improve performance across various NLP tasks",
        claim_type: "empirical",
        claim_subtype: "factual",
        claim_level: "supporting",
        importance_score: 0.7,
        citation_strength: "moderate",
        existing_citations: ["Bahdanau et al. (2015)"],
        unsupported: false,
        section_location: "Related Work"
      },
      {
        id: 4,
        claim_text: "The computational complexity of self-attention is O(n²) where n is sequence length",
        claim_type: "theoretical",
        claim_subtype: "factual",
        claim_level: "supporting",
        importance_score: 0.6,
        citation_strength: "missing",
        existing_citations: [],
        unsupported: true,
        section_location: "Analysis"
      },
      {
        id: 5,
        claim_text: "Our analysis reveals that attention heads learn interpretable patterns",
        claim_type: "empirical",
        claim_subtype: "causal",
        claim_level: "main",
        importance_score: 0.85,
        citation_strength: "weak",
        existing_citations: ["Clark et al. (2019)"],
        unsupported: true,
        section_location: "Results"
      }
    ],
    feedback: [
      {
        id: 1,
        feedback_type: "evidence",
        severity: "critical",
        section_reference: "Analysis",
        line_reference: "Paragraph 3, lines 45-47",
        specific_issue: "Unsupported claim about computational complexity without citation",
        feedback_text: "The claim about O(n²) complexity lacks citation support. While this is a well-known property of self-attention, academic writing requires proper attribution.",
        suggestions: [
          "Add citation to Vaswani et al. (2017) where this complexity is discussed",
          "Include the exact equation showing why the complexity is quadratic",
          "Consider citing additional sources that analyze transformer complexity"
        ],
        example_fix: "For instance: 'The self-attention mechanism has O(n²) computational complexity (Vaswani et al., 2017), where n is the sequence length.'",
        reasoning: "Reviewers expect mathematical claims to be properly cited, even for well-known results"
      },
      {
        id: 2,
        feedback_type: "argumentation",
        severity: "major",
        section_reference: "Results",
        line_reference: "Section 4, paragraph 2",
        specific_issue: "Weak evidence for interpretability claim",
        feedback_text: "The claim about attention heads learning interpretable patterns is supported by only one citation. For a main claim (importance: 0.85), stronger evidence is needed.",
        suggestions: [
          "Add 2-3 additional citations supporting interpretability (e.g., Vig & Belinkov 2019, Voita et al. 2019)",
          "Provide specific examples of interpretable patterns discovered",
          "Include quantitative metrics for interpretability",
          "Acknowledge limitations or counterarguments"
        ],
        example_fix: "Recent work has demonstrated that attention heads learn linguistically interpretable patterns (Clark et al. 2019; Vig & Belinkov 2019), including syntactic roles and coreference relationships.",
        reasoning: "Main claims need robust evidence. Single-citation support is insufficient for high-importance assertions"
      },
      {
        id: 3,
        feedback_type: "coverage",
        severity: "minor",
        section_reference: "Related Work",
        line_reference: "Section 2",
        specific_issue: "Missing recent work on efficient attention mechanisms",
        feedback_text: "The related work section omits recent advances in efficient attention (Linformer, Performer, Big Bird). This creates a gap in literature coverage.",
        suggestions: [
          "Add a subsection on efficient attention mechanisms",
          "Cite Linformer (Wang et al. 2020), Performer (Choromanski et al. 2021), Big Bird (Zaheer et al. 2020)",
          "Discuss how these approaches address the O(n²) complexity limitation",
          "Position your work relative to these efficiency improvements"
        ],
        example_fix: "Recent work has addressed the quadratic complexity of standard attention through linear approximations (Wang et al. 2020; Choromanski et al. 2021) and sparse attention patterns (Zaheer et al. 2020).",
        reasoning: "Comprehensive literature review is expected. Missing recent work suggests the authors are not aware of cutting-edge developments"
      }
    ],
    coverage_gaps: [
      {
        id: 1,
        gap_type: "missing_seminal",
        description: "Missing citation to Bahdanau et al. (2015) neural machine translation with attention",
        priority: "high",
        suggested_papers: [
          {
            title: "Neural Machine Translation by Jointly Learning to Align and Translate",
            authors: ["Bahdanau", "Cho", "Bengio"],
            year: "2015",
            relevance_score: 0.92
          }
        ]
      },
      {
        id: 2,
        gap_type: "methodology_gap",
        description: "Limited discussion of attention visualization techniques",
        priority: "medium",
        suggested_papers: [
          {
            title: "Analyzing Multi-Head Self-Attention",
            authors: ["Voita", "Talbot", "Moiseev", "Sennrich", "Titov"],
            year: "2019",
            relevance_score: 0.88
          }
        ]
      }
    ]
  },
  stats: {
    total_claims: 5,
    unsupported_claims: 2,
    coverage_gaps: 2,
    critical_feedback: 1,
    major_feedback: 1,
    minor_feedback: 1
  }
}

export default function Demo() {
  const navigate = useNavigate()
  const [showEmailModal, setShowEmailModal] = useState(false)
  const [analysisComplete, setAnalysisComplete] = useState(false)

  useEffect(() => {
    document.title = 'Demo - Noesis Draft Analysis'
    // Simulate analysis completion after 2 seconds
    const timer = setTimeout(() => {
      setAnalysisComplete(true)
      // Show email modal 5 seconds after analysis completes
      setTimeout(() => setShowEmailModal(true), 5000)
    }, 2000)
    return () => clearTimeout(timer)
  }, [])

  const handleSignup = () => {
    navigate('/signup')
  }

  const handleEmailSubmit = async (email: string) => {
    try {
      // TODO: Integrate with backend API to store email and send to Mailchimp/Loops
      // For now, redirect to signup with pre-filled email
      navigate(`/signup?email=${encodeURIComponent(email)}`)
      toast.success('Redirecting to signup...')
    } catch (error) {
      toast.error('Something went wrong. Please try again.')
      throw error
    }
  }

  return (
    <div className="min-h-screen bg-bg-void text-text-primary">
      {/* Demo Banner */}
      <div className="bg-accent-primary/10 border-b border-accent-primary/20 py-2">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <SparklesIcon className="h-4 w-4 text-accent-primary" />
              <span className="font-semibold text-accent-primary">Demo Mode</span>
              <span className="text-text-secondary">- This is sample data. Sign up to analyze your own drafts.</span>
            </div>
            <Button onClick={handleSignup} variant="primary" size="sm">
              Sign Up Free
            </Button>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="bg-bg-surface/95 backdrop-blur-md border-b border-border-default">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-14">
            <div>
              <NoesisLogo size="sm" />
            </div>
            <button
              onClick={() => navigate('/')}
              className="text-sm text-text-secondary hover:text-text-primary"
            >
              ← Back to Home
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 sm:px-8 py-8">
        {!analysisComplete ? (
          /* Loading State */
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center min-h-[60vh]"
          >
            <div className="text-center space-y-4">
              <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
              <h2 className="text-2xl font-semibold">Analyzing Draft...</h2>
              <p className="text-text-secondary">Extracting claims, checking citations, generating feedback</p>
            </div>
          </motion.div>
        ) : (
          /* Analysis Results */
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8"
          >
            {/* Header */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-text-muted">
                <span>{DEMO_DATA.project.title}</span>
                <span>/</span>
                <span>{DEMO_DATA.draft.title}</span>
              </div>
              <h1 className="text-4xl font-bold">{DEMO_DATA.draft.title}</h1>
              <p className="text-text-secondary">{DEMO_DATA.draft.word_count} words · Version {DEMO_DATA.draft.version}</p>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-bg-surface border border-border-default rounded-lg p-6">
                <div className="text-3xl font-bold text-accent-primary">{DEMO_DATA.stats.total_claims}</div>
                <div className="text-sm text-text-secondary mt-1">Claims Extracted</div>
              </div>
              <div className="bg-bg-surface border border-border-default rounded-lg p-6">
                <div className="text-3xl font-bold text-red-500">{DEMO_DATA.stats.unsupported_claims}</div>
                <div className="text-sm text-text-secondary mt-1">Unsupported Claims</div>
              </div>
              <div className="bg-bg-surface border border-border-default rounded-lg p-6">
                <div className="text-3xl font-bold text-yellow-500">{DEMO_DATA.stats.coverage_gaps}</div>
                <div className="text-sm text-text-secondary mt-1">Coverage Gaps</div>
              </div>
              <div className="bg-bg-surface border border-border-default rounded-lg p-6">
                <div className="text-3xl font-bold text-orange-500">{DEMO_DATA.stats.critical_feedback + DEMO_DATA.stats.major_feedback}</div>
                <div className="text-sm text-text-secondary mt-1">Priority Issues</div>
              </div>
            </div>

            {/* Claims Section */}
            <div className="bg-bg-surface border border-border-default rounded-lg p-6">
              <h2 className="text-2xl font-semibold mb-6 flex items-center gap-2">
                <DocumentTextIcon className="h-6 w-6 text-accent-primary" />
                Extracted Claims
              </h2>
              <div className="space-y-4">
                {DEMO_DATA.analysis.claims.map((claim) => (
                  <div
                    key={claim.id}
                    className={`p-4 rounded-lg border ${
                      claim.unsupported
                        ? 'border-red-500/30 bg-red-500/5'
                        : 'border-border-default bg-bg-void/50'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {claim.unsupported ? (
                        <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                      ) : (
                        <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 space-y-2">
                        <p className="text-text-primary">{claim.claim_text}</p>
                        <div className="flex flex-wrap items-center gap-3 text-sm">
                          <span className="px-2 py-1 bg-bg-surface rounded text-text-secondary">
                            {claim.claim_level}
                          </span>
                          <span className="px-2 py-1 bg-bg-surface rounded text-text-secondary">
                            {claim.claim_type}
                          </span>
                          <span className={`px-2 py-1 rounded font-medium ${
                            claim.citation_strength === 'strong' ? 'bg-green-500/20 text-green-400' :
                            claim.citation_strength === 'moderate' ? 'bg-yellow-500/20 text-yellow-400' :
                            claim.citation_strength === 'weak' ? 'bg-orange-500/20 text-orange-400' :
                            'bg-red-500/20 text-red-400'
                          }`}>
                            {claim.citation_strength}
                          </span>
                          {claim.existing_citations.length > 0 && (
                            <span className="text-text-muted">
                              Citations: {claim.existing_citations.join(', ')}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Feedback Section */}
            <div className="bg-bg-surface border border-border-default rounded-lg p-6">
              <h2 className="text-2xl font-semibold mb-6 flex items-center gap-2">
                <ExclamationTriangleIcon className="h-6 w-6 text-orange-500" />
                Reviewer Feedback
              </h2>
              <div className="space-y-6">
                {DEMO_DATA.analysis.feedback.map((feedback) => (
                  <div
                    key={feedback.id}
                    className={`p-6 rounded-lg border ${
                      feedback.severity === 'critical' ? 'border-red-500/30 bg-red-500/5' :
                      feedback.severity === 'major' ? 'border-orange-500/30 bg-orange-500/5' :
                      'border-yellow-500/30 bg-yellow-500/5'
                    }`}
                  >
                    <div className="space-y-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`px-2 py-1 rounded text-xs font-bold uppercase ${
                              feedback.severity === 'critical' ? 'bg-red-500 text-white' :
                              feedback.severity === 'major' ? 'bg-orange-500 text-white' :
                              'bg-yellow-500 text-white'
                            }`}>
                              {feedback.severity}
                            </span>
                            <span className="text-sm text-text-muted">{feedback.line_reference}</span>
                          </div>
                          <h3 className="font-semibold text-lg">{feedback.specific_issue}</h3>
                        </div>
                      </div>

                      <p className="text-text-secondary">{feedback.feedback_text}</p>

                      <div>
                        <h4 className="font-medium text-sm text-text-primary mb-2">Suggested Improvements:</h4>
                        <ul className="list-disc list-inside space-y-1 text-sm text-text-secondary">
                          {feedback.suggestions.map((suggestion, idx) => (
                            <li key={idx}>{suggestion}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="pt-3 border-t border-border-default">
                        <p className="text-sm text-text-muted italic">{feedback.example_fix}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* CTA Section */}
            <div className="bg-gradient-to-br from-accent-primary/10 to-accent-secondary/10 border border-accent-primary/20 rounded-lg p-8 text-center space-y-4">
              <h3 className="text-2xl font-bold">Want to Analyze Your Own Draft?</h3>
              <p className="text-text-secondary max-w-2xl mx-auto">
                This is just a sample analysis. Sign up for free to upload your own papers and drafts,
                and get AI-powered reviewer feedback before submission.
              </p>
              <div className="flex items-center justify-center gap-4 pt-4">
                <Button onClick={handleSignup} variant="primary" size="lg" className="flex items-center gap-2">
                  Sign Up Free
                  <ArrowRightIcon className="h-5 w-5" />
                </Button>
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-3 text-text-secondary hover:text-text-primary"
                >
                  Learn More
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Email Capture Modal */}
      <EmailCaptureModal
        isOpen={showEmailModal}
        onClose={() => setShowEmailModal(false)}
        onSubmit={handleEmailSubmit}
      />
    </div>
  )
}
