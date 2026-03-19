-- Create a `prospects` table used by scoring/enrichment processes.
-- Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS prospects (
  id bigserial PRIMARY KEY,
  lead_id bigint REFERENCES leads(id) ON DELETE CASCADE,
  score integer DEFAULT 0,
  category text,
  analysis jsonb,
  created_at timestamptz DEFAULT now(),
  first_offer numeric,
  walk_away numeric,
  objections jsonb,
  health_score integer,
  how_to_win text,
  recommended_deal_size text,
  cold_email text,
  linkedin_message text,
  follow_up text,
  tech_stack jsonb,
  news_signals jsonb,
  buying_signals jsonb,
  enriched_score integer,
  hubspot_contact_id text,
  hubspot_deal_id text,
  email_verified boolean DEFAULT false,
  enrichment_summary text
);
