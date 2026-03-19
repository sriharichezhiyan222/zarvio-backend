-- Run these statements against your Supabase database to add the optional columns used by the new integrations.
-- Adjust types as needed (e.g. if you want jsonb columns with different defaults).

ALTER TABLE IF EXISTS prospects
  ADD COLUMN IF NOT EXISTS email_sent boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS follow_up_sent boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS email_verified boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS tech_stack jsonb,
  ADD COLUMN IF NOT EXISTS news_signals jsonb,
  ADD COLUMN IF NOT EXISTS buying_signals jsonb,
  ADD COLUMN IF NOT EXISTS enriched_score integer,
  ADD COLUMN IF NOT EXISTS hubspot_contact_id text,
  ADD COLUMN IF NOT EXISTS hubspot_deal_id text,
  ADD COLUMN IF NOT EXISTS enrichment_summary text;

ALTER TABLE IF EXISTS leads
  ADD COLUMN IF NOT EXISTS company_domain text,
  ADD COLUMN IF NOT EXISTS company_size text,
  ADD COLUMN IF NOT EXISTS industry text,
  ADD COLUMN IF NOT EXISTS linkedin_url text,
  ADD COLUMN IF NOT EXISTS funding_stage text,
  ADD COLUMN IF NOT EXISTS stripe_customer_id text,
  ADD COLUMN IF NOT EXISTS stripe_subscription_id text,
  ADD COLUMN IF NOT EXISTS plan text DEFAULT 'free';
