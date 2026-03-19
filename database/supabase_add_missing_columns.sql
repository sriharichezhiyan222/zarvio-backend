-- Add missing columns required for enrichment, tracking, and billing.
-- Run this in your Supabase SQL editor.

ALTER TABLE IF EXISTS prospects
  ADD COLUMN IF NOT EXISTS enriched_score integer,
  ADD COLUMN IF NOT EXISTS score_boost integer,
  ADD COLUMN IF NOT EXISTS enrichment_summary text,
  ADD COLUMN IF NOT EXISTS tech_stack jsonb,
  ADD COLUMN IF NOT EXISTS news_signals jsonb,
  ADD COLUMN IF NOT EXISTS buying_signals jsonb,
  ADD COLUMN IF NOT EXISTS email_verified boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS email_sent boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS follow_up_sent boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS hubspot_contact_id text,
  ADD COLUMN IF NOT EXISTS hubspot_deal_id text;

ALTER TABLE IF EXISTS leads
  ADD COLUMN IF NOT EXISTS company_domain text,
  ADD COLUMN IF NOT EXISTS company_size text,
  ADD COLUMN IF NOT EXISTS funding_stage text,
  ADD COLUMN IF NOT EXISTS plan text DEFAULT 'free',
  ADD COLUMN IF NOT EXISTS stripe_customer_id text;
