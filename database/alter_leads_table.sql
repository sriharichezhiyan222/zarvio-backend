-- Re-Sync Leads Table Columns
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS name text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS phone text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS company text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS role text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS linkedin_url text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS revenue_estimate numeric;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS needs text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS location text;
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- Ensure 'name' is NOT NULL if possible (optional but cleaner)
-- ALTER TABLE public.leads ALTER COLUMN name SET NOT NULL;
