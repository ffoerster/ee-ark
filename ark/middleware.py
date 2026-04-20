import logging
import time

logger = logging.getLogger("ark.request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        t0 = time.monotonic()
        response = self.get_response(request)
        logger.info(
            "%s %s %s %.0fms",
            request.method,
            request.path,
            response.status_code,
            (time.monotonic() - t0) * 1000,
        )
        return response
