from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Load environment variables before importing route modules.
# Ensures `.env` is loaded even if the working directory is not the repo root.
repo_root = Path(__file__).resolve().parent
load_dotenv(repo_root / ".env")

from routes.leads import router as leads_router
from routes.prospects import router as prospects_router
from routes.scoring import router as scoring_router

app = FastAPI(
    title="ZarvioAI Backend",
    description="AI-powered business development agent for B2B lead generation and outreach.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Simple health-check endpoint used for uptime monitoring."""
    return {"status": "ok"}


# Attach feature routers
app.include_router(leads_router)
app.include_router(prospects_router, prefix="/prospects")
app.include_router(scoring_router)

