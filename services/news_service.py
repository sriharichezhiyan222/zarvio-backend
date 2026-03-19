import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx

from database.supabase import get_supabase, has_supabase_config
from services.analytics_service import track

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2/everything"


def _detect_signal_type(title: str, description: str) -> Optional[str]:
    text = f"{title} {description}".lower()
    if "fund" in text or "raised" in text or "series" in text:
        return "funding"
    if "hire" in text or "hiring" in text or "recruit" in text:
        return "hiring"
    if "launch" in text or "release" in text or "product" in text:
        return "product"
    if "expand" in text or "opening" in text or "office" in text:
        return "expansion"
    return None


async def get_news_signals(lead_id: int) -> Dict[str, Any]:
    """Fetch news articles for a lead's company and detect buying signals."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    supabase = get_supabase()

    def _fetch_lead():
        return (
            supabase.table("leads")
            .select("id, company")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )

    lead_res = await asyncio.to_thread(_fetch_lead)
    if getattr(lead_res, "error", None):
        raise RuntimeError(f"Failed to fetch lead: {lead_res.error}")

    lead_rows = getattr(lead_res, "data", []) or []
    if not lead_rows:
        raise ValueError(f"Lead not found for id={lead_id}")

    company = lead_rows[0].get("company")
    if not company:
        return {"lead_id": lead_id, "articles": [], "signals": []}

    articles: List[Dict[str, Any]] = []
    signals: List[Dict[str, Any]] = []

    if NEWS_API_KEY:
        async def _fetch_articles(search_query: str) -> List[Dict[str, Any]]:
            params = {
                "apiKey": NEWS_API_KEY,
                "q": search_query,
                "pageSize": 5,
                "sortBy": "publishedAt",
            }
            try:
                print(f"NewsAPI query: {search_query}")
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(NEWS_API_URL, params=params)
                    print(f"NewsAPI status: {resp.status_code}")
                    data = resp.json() or {}
                    print(f"NewsAPI response: {data}")
                    resp.raise_for_status()
                    return data.get("articles") or []
            except Exception as exc:
                print(f"NewsAPI request failed: {exc}")
                return []

        raw_articles = await _fetch_articles(company)
        if not raw_articles:
            # Try a broader search with common keywords
            for alt in [f"{company} funding", f"{company} hiring", f"{company} product"]:
                raw_articles = _fetch_articles(alt)
                if raw_articles:
                    break

        for art in raw_articles[:3]:
            title = art.get("title") or ""
            description = art.get("description") or ""
            signal_type = _detect_signal_type(title, description)
            article = {
                "title": title,
                "url": art.get("url"),
                "source": (art.get("source") or {}).get("name"),
                "published_at": art.get("publishedAt"),
                "signal_type": signal_type,
            }
            articles.append(article)
            if signal_type:
                signals.append(article)

    # Boost score for funding/hiring signals
    boost = 0
    if any(s.get("signal_type") in {"funding", "hiring"} for s in signals):
        boost = 10
        try:
            def _update():
                return (
                    supabase.table("prospects")
                    .upsert({"lead_id": lead_id, "news_signals": signals}, on_conflict="lead_id")
                    .execute()
                )

            await asyncio.to_thread(_update)
        except Exception as exc:
            print(f"Error saving news signals for lead_id={lead_id}: {exc}")

        try:
            def _fetch_prospect():
                return (
                    supabase.table("prospects")
                    .select("score")
                    .eq("lead_id", lead_id)
                    .limit(1)
                    .execute()
                )

            prospect_res = await asyncio.to_thread(_fetch_prospect)
            prospect_rows = getattr(prospect_res, "data", []) or []
            if prospect_rows:
                old_score = prospect_rows[0].get("score") or 0
                new_score = min(100, old_score + boost)
                def _update_score():
                    return (
                        supabase.table("prospects")
                        .update({"score": new_score})
                        .eq("lead_id", lead_id)
                        .execute()
                    )

                await asyncio.to_thread(_update_score)
        except Exception as exc:
            print(f"Error boosting score for lead_id={lead_id}: {exc}")

    track("anonymous", "news_signals", {"lead_id": lead_id, "signals": [s.get("signal_type") for s in signals]})

    return {"lead_id": lead_id, "articles": articles[:3], "signals": signals}
