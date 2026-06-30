-- Migration 026: Stripe webhook idempotency table
-- Prevents duplicate event processing when Stripe retries delivery.
-- Primary key on event_id is the dedup mechanism; INSERT ... ON CONFLICT DO NOTHING
-- in the handler returns early without re-running business logic.

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
    event_id        TEXT        PRIMARY KEY,
    type            TEXT        NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for monitoring queries (e.g. "how many of event type X in last 24h")
CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_type
    ON stripe_webhook_events (type);

CREATE INDEX IF NOT EXISTS idx_stripe_webhook_events_processed_at
    ON stripe_webhook_events (processed_at DESC);

-- Row-level security: this table is only accessed by the service role.
-- Anon and authenticated roles have no access.
ALTER TABLE stripe_webhook_events ENABLE ROW LEVEL SECURITY;

-- No RLS policies = no access for non-service roles (service role bypasses RLS).
