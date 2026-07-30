"""Polite HTTP fetching: rate limit, retry with backoff, loud failure modes.

NotFound means skip the page; Blocked means stop the run, don't hammer.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Transient errors exhausted retries."""


class NotFound(FetchError):
    """404/410 — the page is gone; skip it, don't retry."""


class Blocked(FetchError):
    """401/403 — the site is refusing us; abort the run."""


class Fetcher:
    def __init__(
        self,
        min_interval: float = 3.0,
        max_retries: int = 5,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_UA,
    ):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "ja,en;q=0.8"})

    def _throttle(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> requests.Response:
        backoff = 5.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                log.warning("attempt %d/%d %s: %s", attempt, self.max_retries, url, e)
                if attempt == self.max_retries:
                    raise FetchError(f"{url}: {e}") from e
                time.sleep(backoff)
                backoff = min(backoff * 2, 300.0)
                continue

            if resp.status_code == 200:
                return resp
            if resp.status_code in (404, 410):
                raise NotFound(f"{url}: HTTP {resp.status_code}")
            if resp.status_code in (401, 403):
                raise Blocked(f"{url}: HTTP {resp.status_code}")
            if resp.status_code in RETRYABLE_STATUS:
                retry_after = resp.headers.get("Retry-After")
                delay = backoff
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))
                log.warning(
                    "attempt %d/%d %s: HTTP %d, sleeping %.0fs",
                    attempt,
                    self.max_retries,
                    url,
                    resp.status_code,
                    delay,
                )
                if attempt == self.max_retries:
                    raise FetchError(f"{url}: HTTP {resp.status_code}")
                time.sleep(delay)
                backoff = min(backoff * 2, 300.0)
                continue
            raise FetchError(f"{url}: unexpected HTTP {resp.status_code}")
        raise FetchError(f"{url}: retries exhausted")  # unreachable
