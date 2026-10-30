"""HTTP security headers and admin-login brute-force protection."""
import time
from collections import defaultdict, deque

from flask import request

# No inline <script>/<style> or style="" attributes anywhere, so the policy can be strict.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",           # blob: = local previews of images being uploaded
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])


def register_security_headers(app):
    @app.after_request
    def set_headers(response):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("HSTS"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/admin"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class LoginThrottle:
    """Locks a client out after too many failed attempts within a time window.
    In-memory and per-process: enough for a single small deployment."""

    def __init__(self):
        self._failures = defaultdict(deque)

    def _prune(self, key, window):
        attempts = self._failures[key]
        cutoff = time.monotonic() - window
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts

    def seconds_locked(self, key, max_attempts, window) -> int:
        attempts = self._prune(key, window)
        if len(attempts) < max_attempts:
            return 0
        return max(1, int(attempts[0] + window - time.monotonic()))

    def record_failure(self, key):
        self._failures[key].append(time.monotonic())

    def reset(self, key):
        self._failures.pop(key, None)


login_throttle = LoginThrottle()
