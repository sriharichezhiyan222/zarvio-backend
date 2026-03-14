from dotenv import load_dotenv
from supabase import Client, create_client
import os
from pathlib import Path

# Ensure environment is loaded even when running from a different working directory.
# Load `.env` (if present) first, then fill missing keys from `.env.example`.
repo_root = Path(__file__).resolve().parent.parent
env_path = repo_root / ".env"
example_path = repo_root / ".env.example"

# Always try to load `.env` first (this is the standard expectation).
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)

# If `.env` is missing keys or doesn't exist, fall back to `.env.example` for defaults.
# Distinguish between explicit empty values (e.g. "SUPABASE_KEY=") and missing keys by
# filling in only when the current value is empty.

def _fill_missing_from_file(file_path: Path, keys: set[str]) -> None:
    if not file_path.exists():
        return

    for raw_line in file_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        if k in keys and (os.getenv(k) is None or os.getenv(k) == ""):
            os.environ[k] = v

if example_path.exists():
    _fill_missing_from_file(example_path, {"SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY"})

# If neither file is present, allow dotenv to behave normally.
if not env_path.exists() and not example_path.exists():
    load_dotenv()

def _get_supabase_env() -> tuple[str | None, str | None]:
    """Return the current SUPABASE_URL and SUPABASE_KEY (or anon key) from env."""

    url = (os.getenv("SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    return url or None, key or None


def has_supabase_config() -> bool:
    """Return True if the required Supabase env vars are present."""

    url, key = _get_supabase_env()
    return bool(url and key)


def get_supabase() -> Client:
    """Return a Supabase client.

    This is lazy to avoid failing on import when env vars are missing.
    """

    url, key = _get_supabase_env()
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_KEY (or SUPABASE_ANON_KEY) in environment. "
            "Set these in your .env file."
        )

    return create_client(url, key)
