import asyncio
import csv
import io
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import UploadFile

from database.supabase import get_supabase, has_supabase_config
from services.scoring_service import score_prospect_with_openai

# Ensure environment variables are loaded when this module is imported.
load_dotenv()


async def upload_leads_from_csv(file: UploadFile) -> Dict[str, Any]:
    """Process an uploaded CSV file of leads and persist scored prospects."""

    content = await file.read()
    return await upload_leads_from_bytes(content)


async def upload_leads_from_bytes(content: bytes) -> Dict[str, Any]:
    """Process raw CSV bytes and persist scored prospects."""

    if not has_supabase_config():
        raise RuntimeError("Missing Supabase configuration (SUPABASE_URL / SUPABASE_KEY).")

    try:
        text = content.decode("utf-8")
    except Exception:
        text = content.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))

    # Normalize headers for flexible CSV formats.
    # We allow:
    # - name / full_name / full name
    # - first_name / firstname / first name
    # - last_name / lastname / last name
    # - email / Email
    # - company / organization
    # - title / job_title
    # For this CSV format, we expect these exact headers:
    # "First Name", "Last Name", "Email", "Title", "Company",
    # "Company Domain", "Industry", "Company Size", "City", "Country", "LinkedIn URL"
    fieldnames = reader.fieldnames or []
    normalized: Dict[str, str] = {}
    for original in fieldnames:
        key = original.strip().lower()
        normalized[key] = original

    def has_key(*keys: str) -> bool:
        return any(k.lower() in normalized for k in keys)

    def get_key(*keys: str) -> Optional[str]:
        for k in keys:
            k_lower = k.lower()
            if k_lower in normalized:
                return normalized[k_lower]
        return None

    # Required columns for import
    if not has_key("first name") or not has_key("last name"):
        raise ValueError("CSV must include 'First Name' and 'Last Name' columns.")

    required_fields = ["email", "title", "company"]
    missing = [f for f in required_fields if not has_key(f, "email address")]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

    name_key = get_key("first name")
    last_name_key = get_key("last name")
    email_key = get_key("email", "email address")
    company_key = get_key("company")
    title_key = get_key("title")
    linkedin_key = get_key("linkedin url")
    industry_key = get_key("industry")
    city_key = get_key("city")
    country_key = get_key("country")
    company_size_key = get_key("company size")

    supabase = get_supabase()

    # We don't have reliable schema introspection over the Supabase / PostgREST API,
    # so we attempt to upsert with the expected fields and gracefully remove
    # unsupported fields if the insert fails.
    results: List[Dict[str, Any]] = []
    total_rows = 0
    skipped_no_email = 0
    skipped_no_lead_id = 0

    for row in reader:
        total_rows += 1

        # Normalize/clean input
        first_name = (row.get(name_key) or "").strip() if name_key else ""
        last_name = (row.get(last_name_key) or "").strip() if last_name_key else ""
        email = (row.get(email_key) or "").strip() if email_key else ""
        email = email.lower()
        company = (row.get(company_key) or "").strip() if company_key else ""
        title = (row.get(title_key) or "").strip() if title_key else ""

        # Extra fields
        linkedin_url = (row.get(linkedin_key) or "").strip() if linkedin_key else ""
        industry = (row.get(industry_key) or "").strip() if industry_key else ""
        city = (row.get(city_key) or "").strip() if city_key else ""
        country = (row.get(country_key) or "").strip() if country_key else ""
        company_size = (row.get(company_size_key) or "").strip() if company_size_key else ""

        if not email:
            skipped_no_email += 1
            continue

        name = f"{first_name} {last_name}".strip()

        lead_data: Dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "company": company,
            "title": title,
        }

        # Optional fields (only include if present).
        if linkedin_url:
            lead_data["linkedin_url"] = linkedin_url
        if industry:
            lead_data["industry"] = industry
        if city:
            lead_data["city"] = city
        if country:
            lead_data["country"] = country
        if company_size:
            lead_data["company_size"] = company_size

        # Upsert the lead by email (idempotent for repeat uploads). Supabase upsert does not return
        # the row id reliably in all cases, so we will query it separately after the upsert.
        lead_id = None
        lead_result = None

        def _make_upsert(data: Dict[str, Any]):
            # supabase-py does not support chaining .select() after .upsert(),
            # so we just perform an upsert and query the row separately.
            return (
                supabase.table("leads")
                .upsert(data, on_conflict="email")
                .execute()
            )

        def _insert_lead(data: Dict[str, Any]):
            # If the leads table doesn't have a unique constraint on email, we can't
            # upsert by email; fall back to a plain insert.
            return supabase.table("leads").insert(data).execute()

        # Try to upsert, removing unsupported columns if the schema doesn't include them.
        attempt_data = dict(lead_data)
        max_attempts = max(3, len(attempt_data) + 1)
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            try:
                lead_result = await asyncio.to_thread(_make_upsert, attempt_data)
            except Exception as exc:
                # If the leads table does not have a unique constraint on email, the
                # upsert will raise a 42P10 APIError. In that case, fallback to a plain insert.
                raw_err = None
                if getattr(exc, "args", None):
                    raw_err = exc.args[0]

                if isinstance(raw_err, str):
                    # postgrest raises APIError with a stringified dict in args[0].
                    import ast

                    try:
                        raw_err = ast.literal_eval(raw_err)
                    except Exception:
                        raw_err = None

                error_code = None
                if isinstance(raw_err, dict):
                    error_code = raw_err.get("code")

                if error_code == "42P10":
                    lead_result = await asyncio.to_thread(_insert_lead, attempt_data)
                else:
                    # Handle the PostgREST schema cache message for missing columns.
                    if error_code == "PGRST204" and isinstance(raw_err.get("message"), str):
                        import re

                        # Example: "Could not find the 'city' column of 'leads' in the schema cache"
                        m = re.search(
                            r"Could not find the '(.+?)' column of '.+?' in the schema cache",
                            raw_err["message"],
                        )
                        if m:
                            bad_col = m.group(1)
                            attempt_data.pop(bad_col, None)
                            continue

                    msg = str(exc)
                    # Detect missing column errors in other formats and remove for retry.
                    if "column" in msg and "does not exist" in msg:
                        # Example: "column \"linkedin_url\" does not exist"
                        import re

                        m = re.search(r"column \\\"(.*?)\\\" does not exist", msg)
                        if m:
                            bad_col = m.group(1)
                            attempt_data.pop(bad_col, None)
                            continue

                    print(f"Error upserting lead {email}: {exc}")
                    lead_result = None
                    break

            # If we got here, we successfully executed a request.
            if lead_result is None:
                continue

            error = getattr(lead_result, "error", None)
            if error:
                raise RuntimeError(str(error))

            data = getattr(lead_result, "data", None)
            if isinstance(data, list) and data:
                lead_id = data[0].get("id")
            elif isinstance(data, dict):
                lead_id = data.get("id")

            if lead_id:
                break

            # If the upsert returned no ID, but the request succeeded, we'll try once more
            # in case the schema cache was stale (PostgREST can sometimes return empty data). 
            # This avoids dropping the row if it was inserted.
            if attempt == max_attempts and attempt_data:
                break

        # If we still don't have an id, try fetching by email as a final fallback.
        if not lead_id:
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
                    else:
                        print(
                            f"No rows found when querying by email={email}; upsert data: {attempt_data}"
                        )
            except Exception as exc:
                print(f"Error fetching lead_id for {email}: {exc}")

        if not lead_id:
            skipped_no_lead_id += 1
            continue

        lead_for_scoring = {
            "first_name": first_name,
            "last_name": last_name,
            "title": title,
            "company": company,
            "email": email,
        }

        scoring = await score_prospect_with_openai(lead_for_scoring)

        # Persist scoring result, attempting upsert if supported.
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
                # Detect missing unique constraint on lead_id (42P10) and fallback to insert.
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
                "name": name,
                "email": email,
                "company": company,
                "title": title,
                "score": scoring.get("score"),
                "category": scoring.get("category"),
                "analysis": scoring.get("analysis"),
            }
        )

    # Sort by score desc
    results.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))

    # Track upload in analytics
    try:
        from services.analytics_service import track

        track("anonymous", "csv_uploaded", {"lead_count": len(results)})
    except Exception:
        pass

    return {
        "total_uploaded": len(results),
        "total_rows": total_rows,
        "skipped_no_email": skipped_no_email,
        "skipped_no_lead_id": skipped_no_lead_id,
        "headers": fieldnames,
        "leads": results,
    }


def _split_name(name: str) -> (str, str):
    """Split a full name into first and last name (best effort)."""
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])
