-- Migration 020: Add anchor/QA fields to reviewer_feedback
-- These fields are populated by draft_anchor_qa.py during LangGraph analysis

ALTER TABLE reviewer_feedback
ADD COLUMN IF NOT EXISTS target_claim_id  TEXT,
ADD COLUMN IF NOT EXISTS target_gap_id    TEXT,
ADD COLUMN IF NOT EXISTS line_number      INTEGER,
ADD COLUMN IF NOT EXISTS text_snippet     TEXT,
ADD COLUMN IF NOT EXISTS char_start       INTEGER,
ADD COLUMN IF NOT EXISTS char_end         INTEGER,
ADD COLUMN IF NOT EXISTS match_confidence FLOAT,
ADD COLUMN IF NOT EXISTS qa_status        TEXT    DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS qa_notes         JSONB   DEFAULT '[]'::jsonb;

COMMENT ON COLUMN reviewer_feedback.target_claim_id  IS 'ID of the draft_claim this feedback targets';
COMMENT ON COLUMN reviewer_feedback.target_gap_id    IS 'ID of the coverage_gap this feedback targets';
COMMENT ON COLUMN reviewer_feedback.line_number      IS 'Line number in the draft where feedback anchors';
COMMENT ON COLUMN reviewer_feedback.text_snippet     IS 'Verbatim draft text span this feedback anchors to';
COMMENT ON COLUMN reviewer_feedback.char_start       IS 'Char offset from line start where snippet begins';
COMMENT ON COLUMN reviewer_feedback.char_end         IS 'Char offset from line start where snippet ends';
COMMENT ON COLUMN reviewer_feedback.match_confidence IS 'Anchor match confidence 0-1 from draft_anchor_qa';
COMMENT ON COLUMN reviewer_feedback.qa_status        IS 'QA gate result: passed | failed | skipped';
COMMENT ON COLUMN reviewer_feedback.qa_notes         IS 'List of failed check names from QA evaluation';

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_target_claim
    ON reviewer_feedback(draft_id, target_claim_id)
    WHERE target_claim_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_anchor_line
    ON reviewer_feedback(draft_id, line_number)
    WHERE line_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_qa_status
    ON reviewer_feedback(draft_id, qa_status);
