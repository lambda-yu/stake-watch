from __future__ import annotations
import asyncio
import logging
import random
from abc import ABC, abstractmethod
from stake_watch.models.cex import CexEarnRate, VenueRateSnapshot


_CEX_MAX_CONCURRENCY = 3
_venue_semaphore = asyncio.Semaphore(_CEX_MAX_CONCURRENCY)  # bounds thundering herd as venues grow


def _looks_like_rate_limit(err: BaseException) -> bool:
    s = str(err).lower()
    return "429" in s or "too many requests" in s or "rate limit" in s


class CexEarnCollector(ABC):
    venue: str = "unknown"
    _retries = 3
    _base_delay = 2.0

    def __init__(self, assets: list[str]):
        self.assets = [a.upper() for a in assets]
        self.logger = logging.getLogger(f"cex.{self.venue}")

    @abstractmethod
    async def fetch(self) -> list[CexEarnRate]: ...

    async def collect(self) -> VenueRateSnapshot:
        async with _venue_semaphore:
            try:
                rates = await self._with_retry(self.fetch)
                return VenueRateSnapshot(venue=self.venue, rates=rates)
            except Exception as e:
                # Some HTTP errors (e.g. httpx.ConnectError from a geo-blocked TLS
                # handshake) stringify to '', so include the exception type name.
                msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                self.logger.warning("%s: fetch failed: %s", self.venue, msg)
                return VenueRateSnapshot(venue=self.venue, rates=[], errors=[msg])

    async def _with_retry(self, fn):
        last: BaseException | None = None
        for attempt in range(self._retries):
            try:
                return await fn()
            except Exception as e:
                last = e
                if not _looks_like_rate_limit(e):
                    raise
                if attempt == self._retries - 1:
                    break
                delay = self._base_delay * (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning("%s: rate-limited, backing off %.1fs (%d/%d)",
                                    self.venue, delay, attempt + 1, self._retries)
                await asyncio.sleep(delay)
        assert last is not None
        raise last