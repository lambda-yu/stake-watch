from __future__ import annotations
import time
from decimal import Decimal
from stake_watch.collectors.morpho.models import BaseNetworkStatus

STALE_THRESHOLD = 60

async def check_base_network(w3) -> BaseNetworkStatus:
    block = await w3.eth.get_block("latest")
    age = time.time() - block["timestamp"]
    gas = float(Decimal(block.get("baseFeePerGas", 0)) / Decimal(10**9))
    return BaseNetworkStatus(latest_block=block["number"], block_age_seconds=age,
        gas_price_gwei=gas, is_healthy=age < STALE_THRESHOLD)
