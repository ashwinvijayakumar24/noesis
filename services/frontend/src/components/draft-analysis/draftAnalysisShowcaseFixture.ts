import type { CategoryKey } from './ReviewerFeedbackList'

export type ShowcaseTabId = 'analysis' | 'feedback' | 'gaps'
export type ShowcaseStatus = 'new' | 'saved' | 'dismissed'

export interface ShowcaseClaim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  section_type: string
  importance_score: number
  confidence_score: number
  requires_citation: boolean
  existing_citations: string[]
  supporting_literature: Array<{
    display: string
    source: string
    similarity: number
  }>
  line_number: number
  text_snippet: string
  status: ShowcaseStatus
}

export interface ShowcaseGap {
  id: string
  gap_type: string
  description: string
  priority: 'high' | 'medium' | 'low'
  section_type: string
  suggested_papers: Array<{
    title: string
    authors: string[]
    year: string
    source: string
    external: boolean
  }>
  has_relevant_literature: boolean
  line_number: number
  text_snippet: string
  status: ShowcaseStatus
}

export interface ShowcaseFeedbackItem {
  id: string
  feedback_type: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  reviewer_persona: string
  section_type: string
  feedback_text: string
  suggestions: string[]
  section_reference: string
  line_number: number
  text_snippet: string
  status: ShowcaseStatus
}

export interface ShowcaseRevisionTask {
  id: string
  source_type: string
  task_type: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  section?: string
  anchor_text?: string
  problem: string
  why_it_matters?: string
  suggested_action: string
  source_ids?: string[]
  line_number?: number
  page_number?: number
  paragraph_index?: number
  suggested_sources?: Array<{
    display: string
    source: string
    similarity?: number
  }>
  text_snippet?: string
  status: ShowcaseStatus
}

export const SHOWCASE_TABS: Array<{ id: ShowcaseTabId; label: string }> = [
  { id: 'analysis', label: 'Review Queue' },
  { id: 'feedback', label: 'Claims & Evidence' },
  { id: 'gaps', label: 'Literature Positioning' },
]

export const SHOWCASE_DOCUMENT = {
  title: 'Example deployment study of a clinical risk prediction tool',
  subtitle: 'Synthetic sample manuscript for public demo and UI testing',
  fileUrl: '/demo/synthetic_deployment_review.txt',
  fileType: 'txt',
}

export const SHOWCASE_DRAFT_META = {
  versionLabel: 'Draft v4',
  privacyLabel: 'Private draft analysis',
  privacyNote: 'Presentation mode using scripted data and exact manuscript line anchors.',
  paperType: 'Journal article',
  citationStyle: 'AMA',
}

export const SHOWCASE_ACTION_ITEMS = [
  'Add primary evidence before claiming deployed models improve clinical outcomes.',
  'Clarify that the selected framework is useful for synthesis, but not fully validated against competing implementation frameworks.',
  'Strengthen the manuscript with prospective deployment evidence and broader non-ICU validation coverage.',
]

export const SHOWCASE_READINESS = {
  score: 72,
  verdict: 'Needs revision before submission',
}

export const SHOWCASE_COUNTS = {
  missingCitations: 3,
  weakArguments: 4,
  coverageGaps: 3,
  methodology: 2,
  reviewerQuestions: 2,
}

export const SHOWCASE_CLAIMS: ShowcaseClaim[] = [
  {
    id: 'claim-outcomes',
    claim_text: 'The manuscript argues that deployment may improve operational outcomes, but the strength of that claim depends on study design and implementation context.',
    claim_type: 'empirical',
    section_location: 'Abstract',
    section_type: 'abstract',
    importance_score: 0.9,
    confidence_score: 0.86,
    requires_citation: true,
    existing_citations: [],
    supporting_literature: [
      {
        display: 'Example Implementation Study A (2023)',
        source: 'manual_upload',
        similarity: 0.93,
      },
      {
        display: 'Example Clinical AI Review B (2018)',
        source: 'openalex',
        similarity: 0.84,
      },
    ],
    line_number: 5,
    text_snippet: 'deployment may improve operational outcomes',
    status: 'new',
  },
  {
    id: 'claim-salient-framework',
    claim_text: 'The manuscript claims that the framework can account for the key factors that warrant attention in successful deployment.',
    claim_type: 'methodological',
    section_location: 'Methods',
    section_type: 'methodology',
    importance_score: 0.84,
    confidence_score: 0.81,
    requires_citation: true,
    existing_citations: [],
    supporting_literature: [
      {
        display: 'Example Implementation Study A (2023)',
        source: 'manual_upload',
        similarity: 0.91,
      },
      {
        display: 'Example Implementation Framework Review (2017)',
        source: 'openalex',
        similarity: 0.77,
      },
    ],
    line_number: 28,
    text_snippet: 'the framework can account for the key factors that warrant attention in successful deployment',
    status: 'new',
  },
  {
    id: 'claim-improve-outcomes',
    claim_text: 'The manuscript argues that deployed models improve outcomes and resource use, but the available evidence is uneven and context-dependent.',
    claim_type: 'empirical',
    section_location: 'Results',
    section_type: 'results',
    importance_score: 0.88,
    confidence_score: 0.79,
    requires_citation: true,
    existing_citations: [],
    supporting_literature: [
      {
        display: 'Example Outcomes Review C (2020)',
        source: 'openalex',
        similarity: 0.74,
      },
      {
        display: 'Example Prospective Evaluation D (2025)',
        source: 'openalex',
        similarity: 0.7,
      },
    ],
    line_number: 37,
    text_snippet: 'deployed models improve outcomes and resource use',
    status: 'new',
  },
]

export const SHOWCASE_GAPS: ShowcaseGap[] = [
  {
    id: 'gap-framework-comparison',
    gap_type: 'missing_perspectives',
    description: 'No comparison to or extension of prior AI implementation frameworks, despite claiming the selected framework covers deployment factors comprehensively.',
    priority: 'high' as const,
    section_type: 'methodology',
    suggested_papers: [
      {
        title: 'Frameworks for evaluating, scaling, and sustaining health technology',
        authors: ['Example Author', 'Example Coauthor'],
        year: '2017',
        source: 'openalex',
        external: true,
      },
      {
        title: 'Implementation research framework overview',
        authors: ['Example Author', 'Example Coauthor'],
        year: '2009',
        source: 'openalex',
        external: true,
      },
    ],
    has_relevant_literature: true,
    line_number: 29,
    text_snippet: 'It does not yet compare the selected framework directly with competing implementation models.',
    status: 'new',
  },
  {
    id: 'gap-prospective-trials',
    gap_type: 'missing_evidence',
    description: 'Prospective or quasi-experimental deployment evidence remains thin relative to the strength of the manuscript’s outcome-oriented conclusions.',
    priority: 'high' as const,
    section_type: 'results',
    suggested_papers: [
      {
        title: 'Prospective evaluation design principles for clinical ML deployment',
        authors: ['Parikh', 'Zhou'],
        year: '2024',
        source: 'semantic_scholar',
        external: true,
      },
      {
        title: 'Early clinical deployment studies with stronger real-time evaluation',
        authors: ['Example Author', 'Example Coauthor'],
        year: '2023',
        source: 'openalex',
        external: true,
      },
    ],
    has_relevant_literature: true,
    line_number: 34,
    text_snippet: 'Only two studies provided evidence from stronger prospective or quasi-experimental deployment settings.',
    status: 'new',
  },
  {
    id: 'gap-non-icu-validation',
    gap_type: 'population_gap',
    description: 'External validation remains concentrated in ICU and emergency settings, leaving general inpatient and lower-resource care settings undercovered.',
    priority: 'medium' as const,
    section_type: 'discussion',
    suggested_papers: [
      {
        title: 'External validation of prediction tools outside specialized settings',
        authors: ['Example Author', 'Example Coauthor'],
        year: '2025',
        source: 'openalex',
        external: true,
      },
      {
        title: 'Transportability of clinical ML systems across hospitals',
        authors: ['Example Author', 'Example Coauthor'],
        year: '2026',
        source: 'openalex',
        external: true,
      },
    ],
    has_relevant_literature: true,
    line_number: 40,
    text_snippet: 'The evidence base for deployment is still narrow outside ICU and emergency department settings.',
    status: 'new',
  },
]

export const SHOWCASE_FEEDBACK: ShowcaseFeedbackItem[] = [
  {
    id: 'feedback-overclaim',
    feedback_type: 'weakness',
    severity: 'major',
    priority: 'high' as const,
    reviewer_persona: 'reviewer_1',
    section_type: 'abstract',
    feedback_text: 'The abstract still leans toward a causal outcome claim without clearly limiting the conclusion to a narrow and heterogeneous deployment evidence base.',
    suggestions: [
      'State explicitly that evidence for improved outcomes is mixed and design-dependent.',
      'Move the strongest caveat about implementation context into the first abstract paragraph.',
    ],
    section_reference: 'Abstract',
    line_number: 5,
    text_snippet: 'deployment may improve operational outcomes',
    status: 'new',
  },
  {
    id: 'feedback-framework-language',
    feedback_type: 'structural',
    severity: 'major',
    priority: 'medium' as const,
    reviewer_persona: 'reviewer_2',
    section_type: 'methodology',
    feedback_text: 'The framing around the selected framework is stronger than the comparative evidence supports. Readers need a clearer distinction between organizing a synthesis and validating a framework against alternatives.',
    suggestions: [
      'Replace “can account for” with narrower language such as “helps organize”.',
      'Add one short paragraph positioning the selected framework against alternatives rather than implying replacement.',
    ],
    section_reference: 'Methods',
    line_number: 28,
    text_snippet: 'the framework can account for the key factors that warrant attention in successful deployment',
    status: 'new',
  },
  {
    id: 'feedback-reviewer-question',
    feedback_type: 'question',
    severity: 'minor',
    priority: 'low' as const,
    reviewer_persona: 'reviewer_2',
    section_type: 'results',
    feedback_text: 'Can you specify how many of the included studies reported mortality as a primary outcome rather than a secondary endpoint, and whether any used stronger prospective designs?',
    suggestions: [
      'Add a short summary table breaking out mortality endpoints by design strength.',
    ],
    section_reference: 'Results',
    line_number: 33,
    text_snippet: 'Five studies reported significantly decreased mortality after implementation',
    status: 'new',
  },
]

export const SHOWCASE_REVISION_TASKS: ShowcaseRevisionTask[] = [
  {
    id: 'task-outcome-overclaim',
    source_type: 'reviewer_panel',
    task_type: 'causal_claim',
    severity: 'major',
    priority: 'high',
    section: 'Abstract',
    anchor_text: '"deployment may improve operational outcomes"',
    problem: 'The abstract makes the outcome claim sound stronger than the underlying deployment evidence supports.',
    why_it_matters: 'A reviewer may read this as a causal effectiveness claim, while the draft later describes a narrow and heterogeneous evidence base.',
    suggested_action: 'Qualify the abstract claim and state that outcome improvements are design-dependent and not yet consistently established.',
    source_ids: ['methodology', 'coverage'],
    line_number: 5,
    page_number: 1,
    text_snippet: 'deployment may improve operational outcomes',
    status: 'new',
  },
  {
    id: 'task-framework-positioning',
    source_type: 'reviewer_panel',
    task_type: 'literature_positioning',
    severity: 'major',
    priority: 'high',
    section: 'Methods',
    anchor_text: '"the framework can account for the key factors that warrant attention in successful deployment"',
    problem: 'The draft presents the selected framework as if it has been validated against competing implementation models.',
    why_it_matters: 'The contribution will look overstated unless the manuscript separates using a framework for synthesis from proving it is the best framework.',
    suggested_action: 'Add a short comparison paragraph that names adjacent implementation frameworks and narrows the claim to organizational usefulness.',
    source_ids: ['literature_positioning'],
    line_number: 28,
    page_number: 4,
    text_snippet: 'the framework can account for the key factors that warrant attention in successful deployment',
    suggested_sources: [
      {
        display: 'Example Implementation Framework Review (2017)',
        source: 'openalex',
        similarity: 0.77,
      },
    ],
    status: 'new',
  },
  {
    id: 'task-prospective-evidence',
    source_type: 'reviewer_panel',
    task_type: 'evaluation',
    severity: 'major',
    priority: 'medium',
    section: 'Results',
    anchor_text: '"Only two studies provided evidence from stronger prospective or quasi-experimental deployment settings."',
    problem: 'The evidence summary does not make the study-design limitation prominent enough before discussing positive outcomes.',
    why_it_matters: 'Reviewers are likely to ask whether observed gains come from deployment itself, site selection, or uncontrolled workflow differences.',
    suggested_action: 'Add a compact table or paragraph separating retrospective, prospective, and quasi-experimental evidence before the outcome conclusion.',
    source_ids: ['methodology'],
    line_number: 34,
    page_number: 6,
    text_snippet: 'Only two studies provided evidence from stronger prospective or quasi-experimental deployment settings.',
    status: 'new',
  },
]

export const SHOWCASE_REVIEWER_PANEL = [
  {
    reviewer_id: 'methodology',
    summary: 'The review question is useful, but the current evidence synthesis needs clearer separation between deployment association and causal effectiveness.',
    strengths: ['The manuscript identifies a practical implementation problem and organizes evidence around deployment barriers.'],
    weaknesses: ['Outcome language is stronger than the study designs can support.', 'Prospective and quasi-experimental evidence should be separated from retrospective reports.'],
    questions_to_authors: ['How many included studies used prospective or quasi-experimental designs?'],
    limitations_to_address: ['Generalizability beyond high-resource ICU and emergency settings remains underdeveloped.'],
    issues: [],
    rating: 6,
    confidence: 4,
    recommendation: 'major_revision',
  },
  {
    reviewer_id: 'literature_positioning',
    summary: 'The framing is promising, but the manuscript needs tighter positioning against adjacent implementation frameworks.',
    strengths: ['The draft makes the implementation lens explicit instead of treating model performance as sufficient.'],
    weaknesses: ['The selected framework is not compared with close alternatives before being used as the organizing structure.'],
    questions_to_authors: ['Why is this framework preferable to other implementation-science models for this review?'],
    limitations_to_address: [],
    issues: [],
    rating: 6,
    confidence: 4,
    recommendation: 'major_revision',
  },
]

export const SHOWCASE_META_REVIEW = {
  overall_recommendation: 'major_revision',
  decision_rationale: 'The manuscript is promising but needs tighter evidence calibration, clearer framework positioning, and more explicit limits around deployment generalizability before submission.',
  must_address: [
    'Qualify outcome claims in the abstract and discussion.',
    'Position the selected framework against adjacent implementation frameworks.',
    'Separate stronger prospective evidence from weaker retrospective deployment reports.',
  ],
  nice_to_address: ['Add a compact table summarizing study design and outcome endpoints.'],
  consensus_strengths: ['Relevant practical problem', 'Useful implementation framing'],
  consensus_weaknesses: ['Evidence strength is uneven', 'Framework novelty is under-positioned'],
  reviewer_agreement_level: 'high',
  score_summary: {
    methodology: 6,
    literature_positioning: 6,
  },
}

export const SHOWCASE_TAB_CATEGORY_MAP: Record<ShowcaseTabId, CategoryKey> = {
  analysis: 'all',
  feedback: 'weak_arguments',
  gaps: 'coverage_gaps',
}

export const SHOWCASE_TAB_FOCUS: Record<ShowcaseTabId, { type: 'claim' | 'gap' | 'feedback' | 'task'; id: string }> = {
  analysis: { type: 'task', id: 'task-outcome-overclaim' },
  feedback: { type: 'task', id: 'task-outcome-overclaim' },
  gaps: { type: 'task', id: 'task-framework-positioning' },
}
