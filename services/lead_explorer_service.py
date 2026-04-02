"""
Lead Explorer: normalized search, in-memory lead registry for drafts, and campaign membership (MVP).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from database.supabase import get_supabase, has_supabase_config

# --- MVP in-memory stores (replace with DB tables when ready) ---
_LEAD_REGISTRY: Dict[str, Dict[str, Any]] = {}
_CAMPAIGN_MEMBERS: Dict[str, set] = defaultdict(set)  # campaign_id -> set of lead_id strings

DEFAULT_CAMPAIGNS = [
    {"id": "cmp-1", "name": "Q2 Enterprise", "lead_count": 0},
    {"id": "cmp-2", "name": "SMB Sprint", "lead_count": 0},
    {"id": "cmp-3", "name": "Revival — Dormant", "lead_count": 0},
]


def _register_leads(leads: List[Dict[str, Any]]) -> None:
    for L in leads:
        lid = str(L.get("id") or "")
        if lid:
            _LEAD_REGISTRY[lid] = dict(L)


def get_registered_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    return _LEAD_REGISTRY.get(str(lead_id))


def add_lead_to_campaign(lead_id: str, campaign_id: str) -> None:
    _CAMPAIGN_MEMBERS[str(campaign_id)].add(str(lead_id))


def is_lead_in_campaign(lead_id: str, campaign_id: str) -> bool:
    return str(lead_id) in _CAMPAIGN_MEMBERS.get(str(campaign_id), set())


def list_campaigns_mvp() -> List[Dict[str, Any]]:
    out = []
    for c in DEFAULT_CAMPAIGNS:
        cid = c["id"]
        n = len(_CAMPAIGN_MEMBERS.get(cid, set()))
        out.append({"id": cid, "name": c["name"], "lead_count": n})
    return out


def _row_display_name(row: Dict[str, Any]) -> str:
    name = (row.get("name") or "").strip()
    if name:
        return name
    fn = (row.get("first_name") or "").strip()
    ln = (row.get("last_name") or "").strip()
    parts = [p for p in (fn, ln) if p]
    return " ".join(parts) if parts else (row.get("email") or "Unknown contact")


def _row_role(row: Dict[str, Any]) -> str:
    return (row.get("role") or row.get("title") or "").strip()


def _normalize_from_db_row(row: Dict[str, Any], match_rank: int) -> Dict[str, Any]:
    lid = str(row.get("id"))
    name = _row_display_name(row)
    company = (row.get("company") or "").strip()
    location = (row.get("location") or "").strip()
    needs = (row.get("needs") or "").strip()
    why: List[str] = []
    if location:
        why.append(f"Located in {location}")
    if company:
        why.append(f"Company profile: {company}")
    if needs:
        why.append(needs[:120] + ("…" if len(needs) > 120 else ""))
    if not why:
        why = ["Matches your search criteria", "In your lead database"]

    fit = min(99, 58 + min(5, match_rank) * 7)

    return {
        "id": lid,
        "name": name,
        "role": _row_role(row),
        "company": company or "—",
        "location": location or "—",
        "email": (row.get("email") or "") or "",
        "phone": (row.get("phone") or "") or "",
        "fit_score": fit,
        "why_this_lead": why[:4],
        "recommended_action": f"Add to an active sequence targeting {company or 'this account'}",
        "outreach_angle": f"Personalize around {name.split()[0] if name else 'the team'}'s goals at {company or 'their org'}",
    }


def _synthetic_leads_from_query(query: str, count: int = 5) -> List[Dict[str, Any]]:
    """Deterministic mock leads when DB is empty or has no matches (MVP)."""
    seed = re.sub(r"\s+", " ", (query or "").strip())[:80] or "your market"
    cities = ["Chennai", "Bangalore", "Mumbai", "Hyderabad", "Delhi NCR", "Pune"]
    industries = ["Fintech", "SaaS", "E‑commerce", "Healthtech", "Logistics"]
    base = abs(hash(seed)) % 10_000

    out: List[Dict[str, Any]] = []
    for i in range(count):
        city = cities[(base + i) % len(cities)]
        ind = industries[(base + i * 2) % len(industries)]
        company = f"{ind.split()[0]}Edge {i + 1}"
        lid = f"le_{uuid.uuid4().hex[:12]}"
        name = f"Founder {i + 1} Kumar" if i % 2 == 0 else f"Head of Growth {i + 1}"
        out.append(
            {
                "id": lid,
                "name": name,
                "role": "Founder & CEO" if i % 2 == 0 else "VP Growth",
                "company": company,
                "location": city,
                "email": f"contact{i + 1}@{company.lower().replace(' ', '')}.com",
                "phone": "+91-90000-{:05d}".format((base + i) % 100_000),
                "fit_score": max(65, 92 - i * 5),
                "why_this_lead": [
                    f"{ind} operator in {city}",
                    f"Aligned with: {seed[:50]}{'…' if len(seed) > 50 else ''}",
                    "Likely evaluating outbound / automation tooling",
                ],
                "recommended_action": f"Add to {city} or {ind} campaign",
                "outreach_angle": f"Short founder-style note on scaling {ind.lower()} GTM in {city}",
            }
        )
    return out


def _score_row_against_query(row: Dict[str, Any], query: str) -> int:
    q = query.lower()
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    blob = " ".join(
        str(row.get(k) or "")
        for k in ("name", "first_name", "last_name", "company", "role", "title", "location", "email", "needs")
    ).lower()
    if not tokens:
        return 1
    return sum(1 for t in tokens if t in blob)


async def search_leads(query: str, user_id: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Search DB first, rank, then fill with synthetic leads if needed.
    Returns (thread_id, message, normalized_leads).
    """
    thread_id = str(uuid.uuid4())
    query = (query or "").strip()
    if not query:
        return thread_id, "Ask what kind of leads you want to find.", []

    leads: List[Dict[str, Any]] = []

    if has_supabase_config():
        supabase = get_supabase()

        def _fetch():
            try:
                r = (
                    supabase.table("leads")
                    .select("*")
                    .eq("user_id", user_id)
                    .limit(120)
                    .execute()
                )
                data = getattr(r, "data", None) or []
                if not data:
                    r2 = supabase.table("leads").select("*").limit(120).execute()
                    data = getattr(r2, "data", None) or []
                return data
            except Exception:
                return []

        rows = await asyncio.to_thread(_fetch)

        scored: List[Tuple[int, Dict[str, Any]]] = []
        for row in rows:
            rank = _score_row_against_query(row, query)
            if rank > 0:
                scored.append((rank, row))
        scored.sort(key=lambda x: -x[0])
        if not scored and rows:
            for row in rows[:8]:
                scored.append((1, row))
        for rank, row in scored[:10]:
            leads.append(_normalize_from_db_row(row, min(5, rank)))

    if len(leads) < 3:
        need = max(5, 10 - len(leads))
        synthetic = _synthetic_leads_from_query(query, count=min(need, 10))
        existing_ids = {L["id"] for L in leads}
        for L in synthetic:
            if L["id"] not in existing_ids:
                leads.append(L)
                existing_ids.add(L["id"])
            if len(leads) >= 10:
                break

    _register_leads(leads)
    n = len(leads)
    msg = f"I found {n} lead{'s' if n != 1 else ''} matching your request."
    return thread_id, msg, leads[:10]
