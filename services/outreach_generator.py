import json
import os
from typing import Dict, Optional

from openai import OpenAI


client: Optional[OpenAI] = None
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)


def _is_openai_configured() -> bool:
    """Return True if an OpenAI client is available."""
    return client is not None


def _fallback_outreach(company: str, service: str) -> Dict[str, str]:
    """
    Deterministic outreach content used when OpenAI is not available.

    This keeps the endpoint fully functional in local development
    environments where an API key may not yet be configured.
    """
    email = (
        f"Subject: Exploring {service} opportunities with {company}\n\n"
        f"Hi there,\n\n"
        f"I've been looking at companies like {company} that could benefit from "
        f"stronger {service.lower()}. I'd be happy to share a few quick ideas "
        f"tailored to your current setup.\n\n"
        "Would you be open to a short call next week?\n\n"
        "Best regards,\n"
        "Your Name\n"
    )
    linkedin_message = (
        f"Hi! I work with teams on improving their {service.lower()}. "
        f"Given what {company} is building, I think there may be a few "
        "quick wins worth exploring. Open to connecting and sharing ideas?"
    )
    call_script = (
        f"Intro: Thanks for taking the time today. I work with companies like {company} "
        f"on {service.lower()}.\n\n"
        "Discovery: Ask about their current approach, pain points, and priorities.\n"
        "Pitch: Share 2–3 specific outcomes you could help them achieve.\n"
        "Close: Suggest a follow-up working session with the relevant stakeholders."
    )

    return {
        "email": email,
        "linkedin_message": linkedin_message,
        "call_script": call_script,
    }


def generate_outreach(company: str, service: str) -> Dict[str, str]:
    """
    Use OpenAI to generate multi-channel outreach content for a given
    company and service.
    """
    if not _is_openai_configured():
        return _fallback_outreach(company, service)

    try:
        if client is None:
            return _fallback_outreach(company, service)

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert SDR who writes concise, high-converting "
                        "outreach messages for B2B prospects."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Generate three outreach assets for the following:\n"
                        f"- Company: {company}\n"
                        f"- Service: {service}\n\n"
                        "1) Email body (no greeting name needed).\n"
                        "2) LinkedIn connection / InMail message.\n"
                        "3) Short discovery call script.\n\n"
                        "Respond only with JSON containing keys: email, "
                        "linkedin_message, call_script."
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        raw_content = completion.choices[0].message.content or "{}"
        data = json.loads(raw_content)

        email = data.get("email") or _fallback_outreach(company, service)["email"]
        linkedin_message = data.get("linkedin_message") or _fallback_outreach(
            company, service
        )["linkedin_message"]
        call_script = data.get("call_script") or _fallback_outreach(company, service)[
            "call_script"
        ]

        return {
            "email": email,
            "linkedin_message": linkedin_message,
            "call_script": call_script,
        }
    except Exception:
        # In a production deployment this should be logged.
        return _fallback_outreach(company, service)

