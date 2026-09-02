from __future__ import annotations
import asyncio
import logging
import random
from abc import ABC, abstractmethod
import httpx
from pydantic import BaseModel
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

logger = logging.getLogger(__name__)

# Per-chain semaphores: cap simultaneous RPC-heavy collectors on the same
# chain so we don't burst-hit a rate-limited public RPC (e.g. Base's
# mainnet.base.org caps ~100 req/s per IP and all 4 Morpho vaults share it).
_CHAIN_LIMITS = {"base": 1, "ethereum": 2, "solana": 2, "bsc": 2}
_chain_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_chain_semaphore(chain: Chain) -> asyncio.Semaphore:
    key = chain.value if hasattr(chain, "value") else str(chain)
    if key not in _chain_semaphores:
        _chain_semaphores[key] = asyncio.Semaphore(_CHAIN_LIMITS.get(key, 3))
    return _chain_semaphores[key]


def _looks_like_rate_limit(err: BaseException) -> bool:
    s = str(err).lower()
    return ("429" in s or "too many requests" in s or "rate limit" in s
             or "exceeded" in s and "limit" in s)


def _is_retryable(err: BaseException) -> bool:
    """Rate-limit-shaped errors and transient httpx network errors (timeouts,
    connection resets) are worth retrying; other failures (bad input, HTTP
    4xx/5xx status raised via raise_for_status(), parsing bugs) are not."""
    return _looks_like_rate_limit(err) or isinstance(err, httpx.TransportError)


class CollectResult(BaseModel):
    positions: list[Position] = []
    protocol_stats: ProtocolStats | None = None
    errors: list[str] = []

class BaseCollector(ABC):
    # Default: 3 tries with exponential-plus-jitter backoff on 429 / rate limit.
    _rate_limit_retries = 3
    _rate_limit_base_delay = 2.0  # seconds

    def __init__(self, chain: Chain, protocol: str):
        self.chain = chain
        self.protocol = protocol
        self.logger = logging.getLogger(f"collector.{protocol}")

    @abstractmethod
    async def collect_positions(self, wallet: str) -> list[Position]: ...

    @abstractmethod
    async def collect_protocol_stats(self) -> ProtocolStats: ...

    async def _with_rate_limit_retry(self, coro_factory, label: str):
        """Wrap a coroutine so that rate-limit failures back off + retry.

        `coro_factory` is a zero-arg callable that returns a fresh coroutine
        each attempt (a coroutine can only be awaited once).
        """
        last_exc = None
        for attempt in range(self._rate_limit_retries):
            try:
                return await coro_factory()
            except Exception as e:
                last_exc = e
                if not _is_retryable(e):
                    raise
                if attempt == self._rate_limit_retries - 1:
                    break
                delay = self._rate_limit_base_delay * (2 ** attempt) + random.uniform(0, 1)
                self.logger.warning(
                    f"{self.protocol}: {label} hit rate limit "
                    f"(attempt {attempt + 1}/{self._rate_limit_retries}), "
                    f"backing off {delay:.1f}s")
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def collect(self, wallet: str) -> CollectResult:
        errors: list[str] = []
        positions: list[Position] = []
        protocol_stats: ProtocolStats | None = None
        # Cap concurrent RPC pressure on the same chain.
        async with _get_chain_semaphore(self.chain):
            if wallet:
                try:
                    positions = await self._with_rate_limit_retry(
                        lambda: self.collect_positions(wallet), "positions collection")
                except Exception as e:
                    msg = f"{self.protocol}: positions collection failed: {e}"
                    self.logger.error(msg)
                    errors.append(msg)
            try:
                protocol_stats = await self._with_rate_limit_retry(
                    self.collect_protocol_stats, "stats collection")
            except Exception as e:
                msg = f"{self.protocol}: stats collection failed: {e}"
                self.logger.error(msg)
                errors.append(msg)
        return CollectResult(positions=positions, protocol_stats=protocol_stats, errors=errors)
