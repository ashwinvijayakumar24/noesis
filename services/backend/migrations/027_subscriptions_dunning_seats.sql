-- Migration 027: Dunning and seat-count columns on subscriptions
--
-- seats: stores the paid seat count for team plans, synced from
--   items.data[0].quantity on every customer.subscription.updated event.
--   NULL for pro/free plans where seat count is not meaningful.
--
-- last_payment_failed_at: set when invoice.payment_failed fires, cleared
--   (set to NULL) when invoice.payment_succeeded fires.  Allows the app to
--   show a payment-failure banner without querying Stripe directly.

ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS seats               INTEGER     DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS last_payment_failed_at TIMESTAMPTZ DEFAULT NULL;

-- past_due subscriptions keep their current plan access per the enforced_tier
-- logic in stripe_service.py (active | trialing | past_due -> keep plan tier).
-- This decision is documented here so it is visible alongside the schema.
COMMENT ON COLUMN subscriptions.last_payment_failed_at IS
    'Timestamp of most recent invoice.payment_failed event. NULL means no '
    'outstanding payment failure. Cleared on invoice.payment_succeeded.';

COMMENT ON COLUMN subscriptions.seats IS
    'Paid seat count for team plan subscriptions. Synced from '
    'items.data[0].quantity on customer.subscription.updated. NULL for pro/free.';
