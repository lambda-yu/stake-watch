"""Binance Simple Earn — STUB.

Public `bapi/earn/v2/friendly/finance-earn/simple/all` endpoint 404s from
data-center IPs and public /sapi paths require authenticated keys.
Shipped disabled in seed; see spec appendix.
"""
from __future__ import annotations
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate


class BinanceEarnCollector(CexEarnCollector):
    venue = "binance"

    async def fetch(self) -> list[CexEarnRate]:
        raise NotImplementedError("public endpoint unavailable — see spec appendix")