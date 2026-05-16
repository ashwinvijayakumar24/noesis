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

})
