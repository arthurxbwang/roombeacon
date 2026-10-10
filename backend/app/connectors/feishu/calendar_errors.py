"""Sanitized calendar failures: never retain response bodies, URLs or credentials."""
import httpx


class CalendarEvidenceError(Exception):
    def __init__(self, reason, *, http_status=None, code=None, retry_after=0):
        self.reason = reason
        self.http_status = http_status
        self.code = code
        self.retry_after = retry_after
        super().__init__(reason)


def response_error(status, code, retry_after=0):
    if status == 429 or code in {99991400, 99991403}:
        reason = 'rate_limited'
    elif status >= 500:
        reason = 'upstream_unavailable'
    elif code == 193001:
        reason = 'event_not_found'
    elif code == 191001:
        reason = 'source_unresolved'
    elif status in {401, 403} or code in {191002, 193002, 99991663, 99991664, 99991672}:
        reason = 'access_denied'
    elif status == 404:
        reason = 'event_not_found'
    else:
        reason = 'invalid_response'
    return CalendarEvidenceError(reason, http_status=status, code=code, retry_after=retry_after)


def evidence_error(exc):
    if isinstance(exc, CalendarEvidenceError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        # Compatibility with existing transports; do not preserve private request paths.
        try:
            payload = exc.response.json()
            code = payload.get('code') if isinstance(payload, dict) else None
        except ValueError:
            code = None
        return response_error(exc.response.status_code, code if type(code) is int else None)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return CalendarEvidenceError('read_timeout')
    if isinstance(exc, httpx.NetworkError):
        return CalendarEvidenceError('network_error')
    if isinstance(exc, PermissionError):
        return CalendarEvidenceError('access_denied')
    return CalendarEvidenceError('invalid_response')
