"""Observe existing buffered HTTP calls without replacing their response objects.

Workflow streaming queries retain their own bounded evidence implementation.
These observations describe transport, not successful biomedical answers.
"""

from base64 import b64encode
from copy import deepcopy
import json

from .execution import observation_target


def capture_request(request, /, url, **kwargs):
    target = observation_target()
    if target is None:
        return request(url, **kwargs)
    observation = {"kind": "service", "status": "pending"}
    target.setdefault("observations", []).append(observation)
    try:
        observation["request"] = {
            "method": getattr(request, "__name__", "unknown"),
            "url": url,
            "arguments": deepcopy(kwargs),
        }
    except Exception as error:
        target.setdefault("observation_errors", []).append(type(error).__name__)
    try:
        response = request(url, **kwargs)
    except BaseException as error:
        observation.update(status="transport_error", error_type=type(error).__name__)
        raise
    try:
        observation.update(status="received", status_code=response.status_code)
        # All call sites using this helper request buffered responses. Never
        # invoke json() again: decoding it twice can alter custom responses.
        body = response.content
        if not isinstance(body, bytes):
            raise TypeError("Response has no buffered byte body")
        observation["body_base64"] = b64encode(body).decode("ascii")
        try:
            observation["body_json"] = json.loads(body)
        except (ValueError, UnicodeError):
            observation["body_json_status"] = "not_json"
    except Exception as error:
        observation["capture_error"] = type(error).__name__
        target.setdefault("observation_errors", []).append(type(error).__name__)
    return response
