from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from pydantic import BaseModel
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

logger = logging.getLogger(__name__)

class CollectResult(BaseModel):
    positions: list[Position] = []
    protocol_stats: ProtocolStats | None = None
    errors: list[str] = []

class BaseCollector(ABC):
    def __init__(self, chain: Chain, protocol: str):
        self.chain = chain
        self.protocol = protocol
        self.logger = logging.getLogger(f"collector.{protocol}")

    @abstractmethod
    async def collect_positions(self, wallet: str) -> list[Position]: ...

    @abstractmethod
    async def collect_protocol_stats(self) -> ProtocolStats: ...

    async def collect(self, wallet: str) -> CollectResult:
        errors: list[str] = []
        positions: list[Position] = []
        protocol_stats: ProtocolStats | None = None
        try:
            positions = await self.collect_positions(wallet)
        except Exception as e:
            msg = f"{self.protocol}: positions collection failed: {e}"
            self.logger.error(msg)
            errors.append(msg)
        try:
            protocol_stats = await self.collect_protocol_stats()
        except Exception as e:
            msg = f"{self.protocol}: stats collection failed: {e}"
            self.logger.error(msg)
            errors.append(msg)
        return CollectResult(positions=positions, protocol_stats=protocol_stats, errors=errors)
