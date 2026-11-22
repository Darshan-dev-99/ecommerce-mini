"""Shared API plumbing: error shape and CSRF handling."""

from django.http import JsonResponse
from django.views.decorators.csrf import requires_csrf_token
from rest_framework.views import exception_handler


def _collect_messages(data) -> list[str]:
    messages: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in {"detail", "message", "items"}:
                continue
            if isinstance(value, (list, tuple)):
                messages.extend(str(item) for item in value)
            elif isinstance(value, dict):
                messages.extend(_collect_messages(value))
            else:
                messages.append(str(value))
    elif isinstance(data, (list, tuple)):
        messages.extend(str(item) for item in data)
    else:
        messages.append(str(data))
    return messages


def api_exception_handler(exc, context):
    """Give every error response a single human readable `message`.

    The storefront shows `message` in a toast, so `{field: [errors]}` becomes a
    readable sentence while the structured data stays available.
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    detail = ""
    if isinstance(data, dict):
        raw_detail = data.get("detail") or data.get("message")
        if raw_detail and not isinstance(raw_detail, (list, tuple, dict)):
            detail = str(raw_detail)

    if not detail:
        messages = _collect_messages(data)
        detail = messages[0] if messages else "Something went wrong."

    if isinstance(data, list):
        response.data = {"message": detail, "errors": data}
    else:
        data.setdefault("message", detail)
    return response


@requires_csrf_token
def csrf_failure(request, reason=""):
    message = "Your session expired. Refresh the page and try again."
    return JsonResponse({"detail": message, "message": message, "reason": reason}, status=403)
