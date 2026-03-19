-- Create a `users` table for authentication and billing.
-- Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  name text,
  picture text,
  google_id text UNIQUE,
  plan text DEFAULT 'free',
  created_at timestamptz DEFAULT now(),
  last_login timestamptz DEFAULT now()
);
