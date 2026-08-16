import asyncio

import httpx

# Временные проблемы (сеть, таймаут, сайт перегружен/отдал 429 или 5xx) - не
# требуют вмешательства, следующая проверка через POLL_INTERVAL_MINUTES сама
# сработает как повтор.
TRANSIENT_EXCEPTIONS = (httpx.RequestError, asyncio.TimeoutError)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, TRANSIENT_EXCEPTIONS):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in TRANSIENT_STATUS_CODES:
        return True
    return False
