"""Middleware that records per-request latency and error counts."""
from time import time

from starlette.middleware.base import BaseHTTPMiddleware

from core.metrics import record_request


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time()
        response = await call_next(request)
        latency = (time() - start) * 1000
        record_request(latency, error=response.status_code >= 500)
        return response
