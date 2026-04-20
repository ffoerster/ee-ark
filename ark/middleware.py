import logging
import time
import uuid

logger = logging.getLogger("ark.request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        t0 = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        logger.info(
            "%s %s %s %.0fms request_id=%s",
            request.method,
            request.path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
            request.request_id,
        )
        return response
