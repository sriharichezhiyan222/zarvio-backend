#!/usr/bin/env python
"""Run a simple end-to-end smoke test against the ZarvioAI backend.

Run with:
    python test_all_endpoints.py

This script uses only the `requests` library and prints a clear pass/fail report.
"""

import json
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "http://127.0.0.1:8000"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _fmt_pass(label: str, elapsed: float) -> str:
    return f"{GREEN}✅ PASS{RESET} — {label} — {elapsed:.2f}s"


def _fmt_fail(label: str, err: str) -> str:
    return f"{RED}❌ FAIL{RESET} — {label} — {err}"


def _print_section(title: str) -> None:
    print("\n" + "═" * 60)
    print(title)
    print("═" * 60)


def _req(method: str, path: str, **kwargs) -> Tuple[requests.Response, float]:
    url = BASE_URL.rstrip("/") + path
    start = time.perf_counter()
    resp = requests.request(method, url, timeout=30, **kwargs)
    elapsed = time.perf_counter() - start
    return resp, elapsed


def _safe_json(resp: requests.Response) -> Optional[Any]:
    try:
        return resp.json()
    except Exception:
        return None


def _expect_key(obj: Dict[str, Any], key: str) -> Any:
    if key not in obj:
        raise KeyError(f"Missing '{key}' in response")
    return obj[key]


def main() -> None:
    start_all = time.perf_counter()

    results: List[Tuple[bool, str]] = []
    errors: List[str] = []
    warnings: List[str] = []

    lead_id: Optional[str] = None

    _print_section("TEST EVERY ENDPOINT IN ORDER")

    # 1. HEALTH CHECK
    try:
        resp, elapsed = _req("GET", "/health")
        data = _safe_json(resp) or {}
        if resp.status_code == 200 and data.get("status") == "ok":
            integrations = data.get("integrations", {})
            active = [k for k, v in integrations.items() if v]
            print(_fmt_pass("HEALTH CHECK GET /health", elapsed))
            print("  Active integrations:", ", ".join(active) or "(none)")
            results.append((True, "HEALTH CHECK"))
        else:
            raise RuntimeError(f"unexpected response: {resp.status_code} {resp.text}")
    except Exception as e:
        err = str(e)
        print(_fmt_fail("HEALTH CHECK GET /health", err))
        results.append((False, "HEALTH CHECK"))
        errors.append(f"HEALTH CHECK: {err}")

    # 2. CREATE A TEST LEAD
    try:
        body = {
            "name": "Test User",
            "email": "test@techcorp.com",
            "company": "TechCorp",
            "title": "CTO",
        }
        resp, elapsed = _req("POST", "/leads", json=body)
        data = _safe_json(resp) or {}
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"HTTP {resp.status_code} - {resp.text}")
        lead_id = data.get("id") or data.get("lead_id")
        if not lead_id:
            lead = data.get("lead") or {}
            lead_id = lead.get("id") or lead.get("lead_id")
        if not lead_id:
            raise KeyError("Missing id field")
        print(_fmt_pass("CREATE A TEST LEAD POST /leads", elapsed))
        results.append((True, "CREATE LEAD"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("CREATE A TEST LEAD POST /leads", err))
        results.append((False, "CREATE LEAD"))
        errors.append(f"CREATE LEAD: {err}")

    # 3. GET ALL PROSPECTS
    try:
        resp, elapsed = _req("GET", "/prospects")
        data = _safe_json(resp)
        if resp.status_code != 200:
            raise RuntimeError(f"unexpected response: {resp.status_code} {resp.text}")
        prospects = data if isinstance(data, list) else data.get("prospects") if isinstance(data, dict) else None
        if prospects is None:
            raise RuntimeError(f"unexpected response shape: {resp.text}")
        print(_fmt_pass("GET ALL PROSPECTS GET /prospects", elapsed))
        print(f"  Prospects count: {len(prospects)}")
        results.append((True, "GET PROSPECTS"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("GET ALL PROSPECTS GET /prospects", err))
        results.append((False, "GET PROSPECTS"))
        errors.append(f"GET PROSPECTS: {err}")

    # 4. ANALYZE PROSPECT
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/analysis/prospect/{lead_id}")
        data = _safe_json(resp) or {}
        for key in ["signals", "decision_maker_likelihood", "recommended_action"]:
            if key not in data:
                raise KeyError(f"Missing '{key}'")
        print(_fmt_pass("ANALYZE PROSPECT POST /analysis/prospect/{lead_id}", elapsed))
        results.append((True, "ANALYZE PROSPECT"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("ANALYZE PROSPECT POST /analysis/prospect/{lead_id}", err))
        results.append((False, "ANALYZE PROSPECT"))
        errors.append(f"ANALYZE PROSPECT: {err}")

    # 5. NEGOTIATE
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/negotiate/{lead_id}")
        data = _safe_json(resp) or {}
        for key in ["first_offer", "walk_away", "health_score", "objections", "how_to_win"]:
            if key not in data:
                raise KeyError(f"Missing '{key}'")
        print(_fmt_pass("NEGOTIATE POST /negotiate/{lead_id}", elapsed))
        print("  Result:", json.dumps(data, indent=2))
        results.append((True, "NEGOTIATE"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("NEGOTIATE POST /negotiate/{lead_id}", err))
        results.append((False, "NEGOTIATE"))
        errors.append(f"NEGOTIATE: {err}")

    # 6. GENERATE OUTREACH
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/outreach/generate/{lead_id}")
        data = _safe_json(resp) or {}
        for key in ["cold_email", "linkedin_message", "follow_up"]:
            if key not in data:
                raise KeyError(f"Missing '{key}'")
        print(_fmt_pass("GENERATE OUTREACH POST /outreach/generate/{lead_id}", elapsed))
        cold_email = str(data.get("cold_email") or "")
        print(f"  cold_email (first 100 chars): {cold_email[:100]!r}")
        results.append((True, "GENERATE OUTREACH"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("GENERATE OUTREACH POST /outreach/generate/{lead_id}", err))
        results.append((False, "GENERATE OUTREACH"))
        errors.append(f"GENERATE OUTREACH: {err}")

    # 7. CSV UPLOAD
    try:
        csv_content = "First Name,Last Name,Email,Title,Company\n" + \
            "James,Wilson,james@saas.com,CTO,SaaSCo\n" + \
            "Sarah,Chen,sarah@fintech.io,CEO,FintechCo\n" + \
            "Mike,Patel,mike@startup.com,Founder,StartupX\n"
        files = {"file": ("test_upload.csv", csv_content, "text/csv")}
        resp, elapsed = _req("POST", "/leads/upload-csv", files=files)
        data = _safe_json(resp) or {}
        uploaded = data.get("total_uploaded") or data.get("uploaded") or data.get("count")
        if uploaded is None:
            raise KeyError("Missing total_uploaded")
        print(_fmt_pass("CSV UPLOAD POST /leads/upload-csv", elapsed))
        print(f"  total_uploaded: {uploaded}")
        results.append((True, "CSV UPLOAD"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("CSV UPLOAD POST /leads/upload-csv", err))
        results.append((False, "CSV UPLOAD"))
        errors.append(f"CSV UPLOAD: {err}")

    # 8. EXPLORIUM — FIND LEADS
    try:
        body = {"query": "CTOs at SaaS companies", "limit": 3}
        resp, elapsed = _req("POST", "/leads/find", json=body)
        data = _safe_json(resp)
        if resp.status_code != 200:
            raise RuntimeError(f"unexpected response: {resp.status_code} {resp.text}")
        leads = None
        if isinstance(data, list):
            leads = data
        elif isinstance(data, dict):
            leads = data.get("leads")
        if leads is None:
            raise RuntimeError(f"unexpected response shape: {resp.text}")
        print(_fmt_pass("EXPLORIUM FIND LEADS POST /leads/find", elapsed))
        print(f"  leads returned: {len(leads)}")
        results.append((True, "EXPLORIUM FIND"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("EXPLORIUM FIND LEADS POST /leads/find", err))
        results.append((False, "EXPLORIUM FIND"))
        errors.append(f"EXPLORIUM FIND: {err}")

    # 9. EXPLORIUM — ENRICH
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        # fetch before score if possible
        resp_before, _ = _req("GET", f"/leads/{lead_id}")
        before = _safe_json(resp_before) or {}
        score_before = before.get("enriched_score") or before.get("score")

        resp, elapsed = _req("POST", f"/enrich/{lead_id}")
        data = _safe_json(resp) or {}
        enriched_score = data.get("enriched_score") or data.get("score")
        if enriched_score is None:
            warnings.append("ENRICH: missing enriched_score/score")
        print(_fmt_pass("EXPLORIUM ENRICH POST /enrich/{lead_id}", elapsed))
        print(f"  score before: {score_before}, score after: {enriched_score}")
        results.append((True, "EXPLORIUM ENRICH"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("EXPLORIUM ENRICH POST /enrich/{lead_id}", err))
        results.append((False, "EXPLORIUM ENRICH"))
        errors.append(f"EXPLORIUM ENRICH: {err}")

    # 10. BUYING SIGNALS
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("GET", f"/signals/{lead_id}")
        data = _safe_json(resp) or {}
        signals = data.get("signals")
        if signals is None:
            raise KeyError("Missing signals")
        print(_fmt_pass("BUYING SIGNALS GET /signals/{lead_id}", elapsed))
        print(f"  signals count: {len(signals) if isinstance(signals, list) else 'N/A'}")
        results.append((True, "BUYING SIGNALS"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("BUYING SIGNALS GET /signals/{lead_id}", err))
        results.append((False, "BUYING SIGNALS"))
        errors.append(f"BUYING SIGNALS: {err}")

    # 11. TECH STACK
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("GET", f"/techstack/{lead_id}")
        data = _safe_json(resp) or {}
        techs = data.get("technologies") or data.get("tech_stack")
        if techs is None:
            warnings.append("TECH STACK: missing technologies/tech_stack")
        print(_fmt_pass("TECH STACK GET /techstack/{lead_id}", elapsed))
        print(f"  tech count: {len(techs) if isinstance(techs, list) else 'N/A'}")
        results.append((True, "TECH STACK"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("TECH STACK GET /techstack/{lead_id}", err))
        results.append((False, "TECH STACK"))
        errors.append(f"TECH STACK: {err}")

    # 12. EMAIL VERIFICATION
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/verify/{lead_id}")
        data = _safe_json(resp) or {}
        verified = data.get("verified")
        if verified is None:
            warnings.append("EMAIL VERIFICATION: missing verified")
        print(_fmt_pass("EMAIL VERIFICATION POST /verify/{lead_id}", elapsed))
        print(f"  verified: {verified}")
        results.append((True, "EMAIL VERIFICATION"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("EMAIL VERIFICATION POST /verify/{lead_id}", err))
        results.append((False, "EMAIL VERIFICATION"))
        errors.append(f"EMAIL VERIFICATION: {err}")

    # 13. FIND EMAILS
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("GET", f"/find-emails/{lead_id}")
        data = _safe_json(resp) or {}
        contacts = data.get("emails") or data.get("contacts")
        if contacts is None:
            warnings.append("FIND EMAILS: missing emails/contacts")
        print(_fmt_pass("FIND EMAILS GET /find-emails/{lead_id}", elapsed))
        print(f"  email count: {len(contacts) if isinstance(contacts, list) else 'N/A'}")
        results.append((True, "FIND EMAILS"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("FIND EMAILS GET /find-emails/{lead_id}", err))
        results.append((False, "FIND EMAILS"))
        errors.append(f"FIND EMAILS: {err}")

    # 14. HUBSPOT SYNC
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/hubspot/sync/{lead_id}")
        data = _safe_json(resp) or {}
        contact_id = data.get("hubspot_contact_id") or data.get("contact_id")
        if contact_id is None:
            warnings.append("HUBSPOT SYNC: missing hubspot_contact_id")
        print(_fmt_pass("HUBSPOT SYNC POST /hubspot/sync/{lead_id}", elapsed))
        print(f"  hubspot_contact_id: {contact_id}")
        results.append((True, "HUBSPOT SYNC"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("HUBSPOT SYNC POST /hubspot/sync/{lead_id}", err))
        results.append((False, "HUBSPOT SYNC"))
        errors.append(f"HUBSPOT SYNC: {err}")

    # 15. HUBSPOT DEAL
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/hubspot/deal/{lead_id}")
        data = _safe_json(resp) or {}
        deal_id = data.get("deal_id")
        if deal_id is None:
            warnings.append("HUBSPOT DEAL: missing deal_id")
        print(_fmt_pass("HUBSPOT DEAL POST /hubspot/deal/{lead_id}", elapsed))
        print(f"  deal_id: {deal_id}")
        results.append((True, "HUBSPOT DEAL"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("HUBSPOT DEAL POST /hubspot/deal/{lead_id}", err))
        results.append((False, "HUBSPOT DEAL"))
        errors.append(f"HUBSPOT DEAL: {err}")

    # 16. SEND EMAIL
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/email/send/{lead_id}")
        data = _safe_json(resp) or {}
        status = data.get("status")
        email_id = data.get("email_id") or data.get("id")
        if status is None:
            warnings.append("SEND EMAIL: missing status")
        print(_fmt_pass("SEND EMAIL POST /email/send/{lead_id}", elapsed))
        print(f"  status: {status}, email_id: {email_id}")
        results.append((True, "SEND EMAIL"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("SEND EMAIL POST /email/send/{lead_id}", err))
        results.append((False, "SEND EMAIL"))
        errors.append(f"SEND EMAIL: {err}")

    # 17. POWER ENRICH
    try:
        if not lead_id:
            raise RuntimeError("Missing lead_id from previous step")
        resp, elapsed = _req("POST", f"/power-enrich/{lead_id}")
        data = _safe_json(resp) or {}
        enriched_score = data.get("enriched_score")
        if enriched_score is None:
            warnings.append("POWER ENRICH: missing enriched_score")
        print(_fmt_pass("POWER ENRICH POST /power-enrich/{lead_id}", elapsed))
        print(f"  result: {json.dumps(data, indent=2)}")
        results.append((True, "POWER ENRICH"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("POWER ENRICH POST /power-enrich/{lead_id}", err))
        results.append((False, "POWER ENRICH"))
        errors.append(f"POWER ENRICH: {err}")

    # 18. GOOGLE AUTH URL
    try:
        resp, elapsed = _req("GET", "/auth/google")
        data = _safe_json(resp) or {}
        url = data.get("auth_url")
        if not url:
            raise KeyError("Missing auth_url")
        print(_fmt_pass("GOOGLE AUTH URL GET /auth/google", elapsed))
        print(f"  auth_url (first 50 chars): {url[:50]}")
        results.append((True, "GOOGLE AUTH URL"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("GOOGLE AUTH URL GET /auth/google", err))
        results.append((False, "GOOGLE AUTH URL"))
        errors.append(f"GOOGLE AUTH URL: {err}")

    # 19. BILLING ORDER — INR
    try:
        body = {"plan": "pro", "currency": "INR", "email": "test@test.com"}
        resp, elapsed = _req("POST", "/billing/create-order", json=body)
        data = _safe_json(resp) or {}
        gateway = data.get("gateway")
        order_id = data.get("order_id")
        if gateway != "razorpay" or not order_id:
            raise KeyError("Missing gateway=razorpay or order_id")
        print(_fmt_pass("BILLING ORDER INR POST /billing/create-order", elapsed))
        print(f"  gateway: {gateway}, order_id: {order_id}")
        results.append((True, "BILLING ORDER INR"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("BILLING ORDER INR POST /billing/create-order", err))
        results.append((False, "BILLING ORDER INR"))
        errors.append(f"BILLING ORDER INR: {err}")

    # 20. BILLING ORDER — USD
    try:
        body = {"plan": "pro", "currency": "USD", "email": "test@test.com"}
        resp, elapsed = _req("POST", "/billing/create-order", json=body)
        data = _safe_json(resp) or {}
        gateway = data.get("gateway")
        checkout_url = data.get("checkout_url")
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} - {resp.text}")
        if gateway != "stripe" or not checkout_url:
            warnings.append("BILLING ORDER USD: missing gateway=stripe or checkout_url")
        print(_fmt_pass("BILLING ORDER USD POST /billing/create-order", elapsed))
        print(f"  checkout_url start: {str(checkout_url)[:60]}")
        results.append((True, "BILLING ORDER USD"))
    except Exception as e:
        err = str(e)
        print(_fmt_fail("BILLING ORDER USD POST /billing/create-order", err))
        results.append((False, "BILLING ORDER USD"))
        errors.append(f"BILLING ORDER USD: {err}")

    # SUMMARY
    total_tests = len(results)
    passed = sum(1 for ok, _ in results if ok)
    failed = total_tests - passed
    pass_rate = (passed / total_tests * 100) if total_tests else 0
    total_time = time.perf_counter() - start_all

    print("\n" + "═" * 60)
    print(f"{BOLD}ZARVIOAI BACKEND TEST RESULTS{RESET}")
    print("═" * 60)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Pass rate: {pass_rate:.1f}%")

    if errors:
        print("\nFAILED ENDPOINTS:")
        for err in errors:
            print(f"- {err}")

    if warnings:
        print("\nWARNINGS:")
        for warning in warnings:
            print(f"- {warning}")

    # Integration status (best-effort from health call)
    try:
        resp, _ = _req("GET", "/health")
        data = _safe_json(resp) or {}
        integrations = data.get("integrations") or {}
        if integrations:
            print("\nINTEGRATION STATUS:")
            for name, ok in integrations.items():
                status = "✅" if ok else "❌"
                print(f"- {name}: {status}")
    except Exception:
        pass

    print(f"\nTime taken: {total_time:.2f}s")
    print("═" * 60)

    # Exit nonzero on failure
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
