import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from database.supabase import has_supabase_config

# Load environment variables before importing route modules.
# Ensures `.env` / `.env.local` are loaded even if the working directory is not the repo root.
repo_root = Path(__file__).resolve().parent
load_dotenv(repo_root / ".env")
# Support per-machine overrides (e.g. `.env.local`).
load_dotenv(repo_root / ".env.local", override=True)

from routes.leads import router as leads_router
from routes.prospects import router as prospects_router
from routes.scoring import router as scoring_router
from routes.analysis import router as analysis_router
from routes.negotiate import router as negotiate_router
from routes.outreach import router as outreach_router
from routes.apollo import router as apollo_router
from routes.auth import router as auth_router
from routes.integrations import router as integrations_router

app = FastAPI(
    title="ZarvioAI Backend",
    description="AI-powered business development agent for B2B lead generation and outreach.",
    version="0.2.0",
)

frontend_url = os.getenv("FRONTEND_URL")

cors_origins = [frontend_url] if frontend_url else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint returning integration status."""

    integrations = {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "supabase": has_supabase_config(),
        "hubspot": bool(os.getenv("HUBSPOT_API_KEY")),
        "resend": bool(os.getenv("RESEND_API_KEY")),
        "newsapi": bool(os.getenv("NEWS_API_KEY")),
        "builtwith": bool(os.getenv("BUILTWITH_API_KEY")),
        "snovio": bool(os.getenv("SNOVIO_CLIENT_ID") and os.getenv("SNOVIO_CLIENT_SECRET")),
        "explorium": bool(os.getenv("EXPLORIUM_API_KEY")),
        "posthog": bool(os.getenv("POSTHOG_API_KEY")),
        "stripe": bool(os.getenv("STRIPE_SECRET_KEY")),
    }

    return {"status": "ok", "version": "1.0.0", "integrations": integrations}


# Attach feature routers
app.include_router(leads_router)
app.include_router(prospects_router, prefix="/prospects")
app.include_router(scoring_router)
app.include_router(analysis_router, prefix="/analysis")
app.include_router(negotiate_router)
app.include_router(outreach_router)
app.include_router(apollo_router)
app.include_router(auth_router)
app.include_router(integrations_router)

