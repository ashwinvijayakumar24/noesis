import { beforeAll, describe, expect, it } from 'vitest'

const storage = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
  clear: () => undefined,
}

beforeAll(() => {
  Object.defineProperty(globalThis, 'sessionStorage', {
    value: storage,
    configurable: true,
  })
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage,
    configurable: true,
  })
})

describe('DraftAnalysis helpers', () => {
  it('extracts editing feedback from the new analysis payload', async () => {
    const { extractEditingFeedbackPayload } = await import('./DraftAnalysis')

    const result = extractEditingFeedbackPayload({
      analysis: {
        analysis: {
          editing_feedback: {
            grammar_issues: [{ text: 'teh', issue: 'Spelling', suggestion: 'the' }],
            citation_issues: [{ text: '(Smith)', issue: 'Incomplete citation', suggestion: 'Add year' }],
            formatting_issues: [],
            structural_notes: [{ note: 'Abstract is too long', severity: 'minor' }],
          },
        },
      },
    })

    expect(result.grammar_issues).toHaveLength(1)
    expect(result.citation_issues).toHaveLength(1)
    expect(result.structural_notes[0].note).toBe('Abstract is too long')
  })

  it('falls back to legacy editing feedback locations', async () => {
    const { extractEditingFeedbackPayload } = await import('./DraftAnalysis')

    const result = extractEditingFeedbackPayload({
      analysis: {
        analysis_metadata: {
          editing_feedback: {
            grammar_issues: [{ text: 'its', issue: 'Grammar', suggestion: "it's" }],
          },
        },
      },
    })

    expect(result.grammar_issues[0].suggestion).toBe("it's")
    expect(result.citation_issues).toEqual([])
  })

  it('marks still-pending and partially-addressed feedback as carryover badges', async () => {
    const { buildCarryoverBadgeMap } = await import('./DraftAnalysis')

    const badges = buildCarryoverBadgeMap(
      [
        { id: 'f-1', feedback_text: 'The methodology section does not justify sample selection.' },
        { id: 'f-2', feedback_text: 'Results overclaim statistical significance.' },
        { id: 'f-3', feedback_text: 'Novel framing is clearer in this version.' },
      ] as any,
      {
        feedback_tracked: [
          {
            feedback_text: 'methodology section does not justify sample selection',
            resolution_status: 'still_pending',
          },
          {
            feedback_text: 'results overclaim statistical significance',
            resolution_status: 'partially_addressed',
          },
          {
            feedback_text: 'novel framing is clearer in this version',
            resolution_status: 'resolved',
          },
        ],
      },
    )

    expect(badges['f-1']).toEqual({
      label: 'Carryover from previous version',
      tone: 'warning',
    })
    expect(badges['f-2']).toEqual({
      label: 'Partially addressed in revision',
      tone: 'accent',
    })
    expect(badges['f-3']).toBeUndefined()
  })
})
