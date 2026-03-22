import asyncio
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from services.scoring_service import score_prospect_with_openai
from database.supabase import get_supabase, has_supabase_config


APOLLO_API_URL = "https://api.apollo.io/api/v1/mixed_people/search"

async def _generate_mock_leads_with_openai(prompt: str) -> List[Dict[str, Any]]:
    # Attempt to load OpenAI client from scoring service
    try:
        from services.scoring_service import client, _deterministic_score
    except ImportError:
        client = None

    if client is None:
        return [
            {"name": "Sarah Chen", "email": "s.chen@stripe.com", "company": "Stripe", "title": "VP of Engineering", "score": 92, "category": "high", "analysis": "High intent decision maker."},
            {"name": "Marcus Williams", "email": "m.williams@notion.so", "company": "Notion", "title": "Head of Partnerships", "score": 87, "category": "high", "analysis": "Strong signal from company."},
            {"name": "Tom Nakamura", "email": "tom@supabase.io", "company": "Supabase", "title": "CTO", "score": 85, "category": "high", "analysis": "Technical decision maker."}
        ]

    prompt_used = prompt or "Find me 5 random B2B SaaS leads in tech."
    system_prompt = (
        "You are an expert sales lead generation AI for Zarvio. The user will ask for leads. "
        "Respond ONLY with a raw JSON array containing exactly 5 highly realistic mock leads matching their criteria. "
        "Each object must have the exact keys: 'name', 'email', 'company', 'title'."
    )
    try:
        import json
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_used}
            ]
        )
        raw = completion.choices[0].message.content or "[]"
        if raw.strip().startswith("```json"):
            raw = raw.strip()[7:-3]
        elif raw.strip().startswith("```"):
            raw = raw.strip()[3:-3]
            
        mock_leads = json.loads(raw)
        
        results = []
        for lead in mock_leads:
            score_res = _deterministic_score(lead)
            results.append({
                "name": lead.get("name", "Unknown"),
                "email": lead.get("email", "no@email.com"),
                "company": lead.get("company", "Unknown"),
                "title": lead.get("title", "Unknown"),
                "score": score_res.get("score", 70),
                "category": score_res.get("category", "high"),
                "analysis": "AI fallback generated: " + score_res.get("analysis", ""),
            })
        return results
        return results
    except Exception as e:
        print(f"OpenAI fallback failed: {e}")
        # Just return the hardcoded list directly instead of recursing
        return [
            {"name": "Sarah Chen", "email": "s.chen@stripe.com", "company": "Stripe", "title": "VP of Engineering", "score": 92, "category": "high", "analysis": "High intent decision maker."},
            {"name": "Marcus Williams", "email": "m.williams@notion.so", "company": "Notion", "title": "Head of Partnerships", "score": 87, "category": "high", "analysis": "Strong signal from company."},
            {"name": "Tom Nakamura", "email": "tom@supabase.io", "company": "Supabase", "title": "CTO", "score": 85, "category": "high", "analysis": "Technical decision maker."}
        ]

def _parse_prompt(prompt: str) -> Dict[str, Optional[str]]:
    """Extract titles, location, and industry keywords from a prompt."""

    prompt_str = (prompt or "").strip()

    # Location: look for "in <location>" at end or middle.
    location = None
    location_match = re.search(r"\bin\s+([A-Za-z0-9 ,&]+)$", prompt_str, re.IGNORECASE)
    if location_match:
        location = location_match.group(1).strip()

    # Titles: look for common job title keywords (e.g. CTO, VP, Director, Head of Sales)
    titles = []
    title_patterns = [
        r"\bCTO\b",
        r"\bC[EO]O\b",
        r"\bCFO\b",
        r"\bCIO\b",
        r"\bCTO\b",
        r"\bVP\b",
        r"\bDirector\b",
        r"\bHead of [A-Za-z]+\b",
        r"\bChief [A-Za-z]+\b",
    ]
    for pat in title_patterns:
        m = re.search(pat, prompt_str, re.IGNORECASE)
        if m:
            titles.append(m.group(0))

    # Industry: try to capture terms like SaaS, e-commerce, fintech, healthcare.
    industry = None
    industry_match = re.search(r"\b(SaaS|fintech|healthcare|e[- ]?commerce|enterprise|software)\b", prompt_str, re.IGNORECASE)
    if industry_match:
        industry = industry_match.group(1)

    return {
        "titles": titles or None,
        "location": location,
        "industry": industry,
    }


async def find_leads(prompt: str) -> List[Dict[str, Any]]:
    """Search Apollo for leads, upsert them into Supabase, and score them."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    # Pull leads from HubSpot instead of Apollo.io due to Free Tier limits
    from services.hubspot_service import list_contacts
    
    supabase = get_supabase()
    people = []

    try:
        print(f"User requested leads via HubSpot: {prompt}")
        hs_contacts = await list_contacts(limit=15)
        for c in hs_contacts:
            if c.get("email"):
                people.append({
                    "first_name": c.get("firstname") or "",
                    "last_name": c.get("lastname") or "",
                    "email": c.get("email"),
                    "title": c.get("jobtitle") or "Unknown",
                    "organization": c.get("company") or "Unknown"
                })
        
        if not people:
            print("No HubSpot contacts found. Falling back to OpenAI mocks.")
            return await _generate_mock_leads_with_openai(prompt)

    except Exception as exc:
        print(f"HubSpot pull failed: {exc}. Falling back to OpenAI generation.")
        return await _generate_mock_leads_with_openai(prompt)

    results: List[Dict[str, Any]] = []

    for person in people[:10]:
        first_name = (person.get("first_name") or "").strip()
        last_name = (person.get("last_name") or "").strip()
        email = (person.get("email") or "").strip()
        title = (person.get("title") or "").strip()
        company = (person.get("organization") or person.get("company") or "").strip()

        if not email:
            # Skip entries with no email address.
            continue

        lead_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "company": company,
            "title": title,
        }

        # Upsert the lead. Use email as conflict key if available.
        try:
            def _upsert_lead():
                return (
                    supabase.table("leads")
                    .upsert(lead_data, on_conflict="email")
                    .execute()
                )

            def _insert_lead():
                return supabase.table("leads").insert(lead_data).execute()

            try:
                lead_result = await asyncio.to_thread(_upsert_lead)
            except Exception as exc:
                # Handle missing unique constraint on email (42P10).
                raw_err = exc.args[0] if getattr(exc, "args", None) else None
                if isinstance(raw_err, str):
                    import ast

                    try:
                        raw_err = ast.literal_eval(raw_err)
                    except Exception:
                        raw_err = None

                if isinstance(raw_err, dict) and raw_err.get("code") == "42P10":
                    lead_result = await asyncio.to_thread(_insert_lead)
                else:
                    raise

            if getattr(lead_result, "error", None):
                print(f"Failed to upsert lead {email}: {lead_result.error}")
        except Exception as exc:
            print(f"Error upserting lead {email}: {exc}")

        # Ensure we have the lead_id to link to prospects.
        lead_id = None
        try:
            def _fetch_lead():
                return (
                    supabase.table("leads")
                    .select("id")
                    .eq("email", email)
                    .limit(1)
                    .execute()
                )

            lead_fetch = await asyncio.to_thread(_fetch_lead)
            if getattr(lead_fetch, "error", None):
                print(f"Failed to fetch lead_id for {email}: {lead_fetch.error}")
            else:
                rows = getattr(lead_fetch, "data", []) or []
                if rows:
                    lead_id = rows[0].get("id")
        except Exception as exc:
            print(f"Error fetching lead_id for {email}: {exc}")

        if not lead_id:
            continue

        # Score prospect using OpenAI GPT-3.5-turbo.
        scoring = await score_prospect_with_openai(
            {
                "id": lead_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "company": company,
                "title": title,
            }
        )

        # Persist scoring result in prospects table.
        try:
            def _upsert_prospect():
                return (
                    supabase.table("prospects")
                    .upsert({"lead_id": lead_id, **scoring}, on_conflict="lead_id")
                    .execute()
                )

            def _insert_prospect():
                return supabase.table("prospects").insert({"lead_id": lead_id, **scoring}).execute()

            try:
                prospect_result = await asyncio.to_thread(_upsert_prospect)
            except Exception as exc:
                # Handle missing unique constraint on lead_id (42P10).
                raw_err = exc.args[0] if getattr(exc, "args", None) else None
                if isinstance(raw_err, str):
                    import ast

                    try:
                        raw_err = ast.literal_eval(raw_err)
                    except Exception:
                        raw_err = None

                if isinstance(raw_err, dict) and raw_err.get("code") == "42P10":
                    prospect_result = await asyncio.to_thread(_insert_prospect)
                else:
                    raise

            if getattr(prospect_result, "error", None):
                print(f"Failed to upsert prospect for lead_id={lead_id}: {prospect_result.error}")
        except Exception as exc:
            print(f"Error upserting prospect for lead_id={lead_id}: {exc}")

        results.append(
            {
                "name": f"{first_name} {last_name}".strip(),
                "email": email,
                "company": company,
                "title": title,
                "score": scoring.get("score"),
                "category": scoring.get("category"),
                "analysis": scoring.get("analysis"),
            }
        )

    # Sort by score descending, placing missing scores last.
    results.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))

    return results
