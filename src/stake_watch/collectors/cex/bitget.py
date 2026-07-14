"""Bitget Savings — STUB.

`/api/v2/earn/savings/product` requires signed auth even for read access.
Shipped disabled in seed; see spec appendix.
"""
from __future__ import annotations
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexEarnRate


class BitgetEarnCollector(CexEarnCollector):
    venue = "bitget"

    async def fetch(self) -> list[CexEarnRate]:
        raise NotImplementedError("public endpoint unavailable — see spec appendix")