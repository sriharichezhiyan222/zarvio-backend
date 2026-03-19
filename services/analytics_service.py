import os
from typing import Any, Dict, Optional

try:
    from posthog import Posthog
except ImportError:  # pragma: no cover
    Posthog = None  # type: ignore


_api_key = os.getenv("POSTHOG_API_KEY")
_posthog_host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")

_client: Optional[Posthog] = None
if _api_key and Posthog is not None:
    try:
        _client = Posthog(project_api_key=_api_key, host=_posthog_host)
    except Exception:
        _client = None


def track(user_id: str, event: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Track an event in PostHog.

    user_id: usually a user identifier; use "anonymous" when unavailable.
    event: event name (e.g. "lead_created").
    properties: additional metadata to send with the event.
    """

    if _client is None:
        return

    try:
        _client.capture(user_id=user_id or "anonymous", event=event, properties=properties or {})
    except Exception:
        # Don't surface PostHog failures to API consumers.
        pass
